"""
FastAPI application for SupportLens backend.
Provides REST API endpoints for trace management, chat, and analytics.
"""

import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config import get_db, get_engine, Base, get_settings
from backend.gemini_client import GeminiClient
from backend.health import get_health_status, HealthResponse
from backend.logging_config import setup_logging, request_id_ctx, get_recent_logs
from backend.middleware import RequestLoggingMiddleware, ErrorHandlingMiddleware
from backend.models import Category, TraceDB
from backend.seed_data import load_seed_data
from backend.schemas import (
    AnalyticsResponse,
    CategoryBreakdown,
    ChatRequest,
    ChatResponse,
    TraceCreate,
    TraceResponse,
    PaginatedTracesResponse,
)

# Initialize structured logging
setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 30  # requests per window
RATE_LIMIT_WINDOW = 60  # seconds
rate_limit_store: dict[str, list[float]] = defaultdict(list)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    """Check if client has exceeded rate limit."""
    client_ip = get_client_ip(request)
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW
    
    # Clean old entries
    rate_limit_store[client_ip] = [
        t for t in rate_limit_store[client_ip] if t > window_start
    ]
    
    if len(rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        logger.warning(
            "Rate limit exceeded",
            extra={
                "type": "rate_limit",
                "client_ip": client_ip,
                "request_count": len(rate_limit_store[client_ip])
            }
        )
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )
    
    rate_limit_store[client_ip].append(current_time)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting SupportLens API", extra={"type": "startup", "version": "1.0.0"})
    
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized", extra={"type": "startup"})
    
    # Load seed data if database is empty
    db = next(get_db())
    try:
        loaded_count = load_seed_data(db)
        if loaded_count > 0:
            logger.info(
                f"Loaded seed data",
                extra={"type": "startup", "seed_traces_loaded": loaded_count}
            )
    except Exception as e:
        logger.error(
            "Failed to load seed data",
            extra={"type": "startup", "error": str(e)}
        )
    finally:
        db.close()
    
    # Check LLM configuration
    settings = get_settings()
    if not settings.gemini_api_key:
        logger.warning(
            "No Gemini API key configured - LLM features will use fallback behavior",
            extra={"type": "startup", "llm_configured": False}
        )
    else:
        logger.info(
            "Gemini API key configured",
            extra={"type": "startup", "llm_configured": True}
        )
    
    yield
    
    # Shutdown
    logger.info("Shutting down SupportLens API", extra={"type": "shutdown"})


# Create FastAPI application
app = FastAPI(
    title="SupportLens API",
    description="Customer support chatbot observability platform API. "
                "Provides endpoints for chat interactions, trace management, and analytics.",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware (order matters - first added is outermost)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Configure CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],  # Expose correlation ID to clients
)


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
async def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check endpoint.
    
    Returns detailed status of all dependencies:
    - Database connectivity and latency
    - LLM provider configuration status
    - Application uptime
    
    Health status meanings:
    - healthy: All systems operational
    - degraded: Some features unavailable but core functionality works
    - unhealthy: Critical systems down, cannot serve traffic
    
    The 'can_serve_traffic' field indicates whether the application
    should receive traffic from load balancers.
    
    Note: LLM being unavailable results in 'degraded' status, not 'unhealthy',
    because the application gracefully degrades (fallback classification,
    error responses for chat) rather than failing completely.
    """
    return get_health_status(db)


@app.get("/logs", tags=["Operations"])
async def get_logs(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of logs to return"),
    level: str | None = Query(None, description="Filter by log level (INFO, WARNING, ERROR)")
):
    """
    Get recent application logs.
    
    Returns logs from the in-memory buffer (max 500 entries stored).
    Logs are returned newest first.
    """
    logs = get_recent_logs(limit=limit, level=level)
    return {"logs": logs, "count": len(logs)}


def check_database_health(db: Session) -> bool:
    """Quick check if database is accessible."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest, req: Request, db: Session = Depends(get_db)):
    """
    Process a chat message and return a support response.
    
    This endpoint:
    1. Accepts a user message and optional conversation history
    2. Generates a support response using Gemini API with context
    3. Measures response time in milliseconds
    4. Classifies the conversation into a category
    5. Stores the trace in the database (if available)
    6. Returns the response and trace ID
    
    Graceful Degradation:
    - If database is unavailable but LLM works, chat still functions
    - Response includes 'trace_stored: false' to indicate degraded mode
    - Traces are not persisted but user can still chat
    """
    check_rate_limit(req)
    
    request_id = request_id_ctx.get()
    settings = get_settings()
    
    # Check if LLM is configured
    if not settings.gemini_api_key:
        logger.warning(
            "Chat request without LLM API key",
            extra={
                "type": "chat",
                "request_id": request_id,
                "error": "no_api_key"
            }
        )
        raise HTTPException(
            status_code=503,
            detail="Chat service unavailable - LLM not configured. "
                   "Please configure GEMINI_API_KEY environment variable."
        )
    
    # Check database health for graceful degradation
    db_available = check_database_health(db)
    if not db_available:
        logger.warning(
            "Database unavailable - operating in degraded mode",
            extra={
                "type": "chat",
                "request_id": request_id,
                "degraded_mode": True
            }
        )
    
    gemini_client = GeminiClient()
    start_time = time.time()
    
    # Convert history to dict format for Gemini client
    history = [{"role": msg.role, "content": msg.content} for msg in request.history] if request.history else None
    
    try:
        bot_response = gemini_client.generate_response(request.message, history=history)
    except Exception as e:
        logger.error(
            "Chat generation failed",
            extra={
                "type": "chat",
                "request_id": request_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "user_message_length": len(request.message)
            }
        )
        raise HTTPException(
            status_code=503,
            detail="Support service temporarily unavailable. Please try again."
        )
    
    response_time_ms = int((time.time() - start_time) * 1000)
    
    trace_id = str(uuid.uuid4())
    # Use provided session_id or generate new one
    session_id = request.session_id or str(uuid.uuid4())
    trace_stored = False
    
    # Only attempt to store trace if database is available
    if db_available:
        # Classify with detailed logging
        try:
            category = gemini_client.classify_trace(request.message)
            classification_method = "llm"
        except Exception as e:
            logger.warning(
                "Classification failed, using fallback",
                extra={
                    "type": "classification",
                    "request_id": request_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "fallback_category": "General_Inquiry"
                }
            )
            category = Category.General_Inquiry
            classification_method = "fallback"
        
        trace = TraceDB(
            id=trace_id,
            session_id=session_id,
            user_message=request.message,
            bot_response=bot_response,
            category=category,
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms
        )
        
        try:
            db.add(trace)
            db.commit()
            trace_stored = True
            logger.info(
                "Chat completed successfully",
                extra={
                    "type": "chat",
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "category": category.value,
                    "classification_method": classification_method,
                    "response_time_ms": response_time_ms,
                    "user_message_length": len(request.message),
                    "bot_response_length": len(bot_response),
                    "trace_stored": True
                }
            )
        except Exception as e:
            logger.error(
                "Database error saving trace",
                extra={
                    "type": "chat",
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            db.rollback()
    else:
        logger.info(
            "Chat completed in degraded mode (no trace storage)",
            extra={
                "type": "chat",
                "request_id": request_id,
                "trace_id": trace_id,
                "session_id": session_id,
                "response_time_ms": response_time_ms,
                "user_message_length": len(request.message),
                "bot_response_length": len(bot_response),
                "trace_stored": False,
                "degraded_mode": True
            }
        )
    
    return ChatResponse(response=bot_response, trace_id=trace_id, session_id=session_id, trace_stored=trace_stored)


@app.post("/traces", response_model=TraceResponse, tags=["Traces"])
async def create_trace(request: TraceCreate, db: Session = Depends(get_db)):
    """
    Create a new trace record from an external source.
    
    This endpoint:
    1. Accepts user_message, bot_response, and response_time_ms
    2. Generates a unique UUID for the trace id
    3. Records the current timestamp
    4. Classifies the trace using the Classification Engine
    5. Persists the trace to the database
    6. Returns the complete trace object with category
    """
    request_id = request_id_ctx.get()
    settings = get_settings()
    
    # Generate unique trace ID
    trace_id = str(uuid.uuid4())
    timestamp = datetime.utcnow()
    
    # Classify the trace - use fallback if LLM not configured
    classification_method = "fallback"
    if settings.gemini_api_key:
        try:
            gemini_client = GeminiClient()
            category = gemini_client.classify_trace(request.user_message)
            classification_method = "llm"
        except Exception as e:
            logger.warning(
                "Classification failed, using fallback",
                extra={
                    "type": "classification",
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "fallback_category": "General_Inquiry"
                }
            )
            category = Category.General_Inquiry
    else:
        category = Category.General_Inquiry
        logger.info(
            "Using fallback classification (no API key)",
            extra={
                "type": "classification",
                "request_id": request_id,
                "trace_id": trace_id,
                "fallback_category": "General_Inquiry"
            }
        )
    
    # Create trace record
    trace = TraceDB(
        id=trace_id,
        user_message=request.user_message,
        bot_response=request.bot_response,
        category=category,
        timestamp=timestamp,
        response_time_ms=request.response_time_ms
    )
    
    # Persist trace to database
    db.add(trace)
    db.commit()
    db.refresh(trace)
    
    logger.info(
        "Trace created",
        extra={
            "type": "trace_created",
            "request_id": request_id,
            "trace_id": trace_id,
            "category": category.value,
            "classification_method": classification_method,
            "response_time_ms": request.response_time_ms
        }
    )
    
    return TraceResponse(
        id=trace.id,
        session_id=trace.session_id,
        user_message=trace.user_message,
        bot_response=trace.bot_response,
        category=trace.category,
        timestamp=trace.timestamp,
        response_time_ms=trace.response_time_ms
    )


@app.get("/traces", response_model=PaginatedTracesResponse, tags=["Traces"])
async def get_traces(
    category: Category | None = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    Retrieve traces with pagination, optionally filtered by category.
    """
    # Build base query
    query = db.query(TraceDB).order_by(TraceDB.timestamp.desc())
    
    # Apply category filter if provided
    if category is not None:
        query = query.filter(TraceDB.category == category)
    
    # Get total count
    total = query.count()
    
    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    offset = (page - 1) * page_size
    
    # Execute query with pagination
    traces = query.offset(offset).limit(page_size).all()
    
    return PaginatedTracesResponse(
        traces=[
            TraceResponse(
                id=trace.id,
                session_id=trace.session_id,
                user_message=trace.user_message,
                bot_response=trace.bot_response,
                category=trace.category,
                timestamp=trace.timestamp,
                response_time_ms=trace.response_time_ms
            )
            for trace in traces
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/analytics", response_model=AnalyticsResponse, tags=["Analytics"])
async def get_analytics(db: Session = Depends(get_db)):
    """
    Get aggregate analytics for all traces.
    """
    # Get all traces from database
    traces = db.query(TraceDB).all()

    # Calculate total count
    total_count = len(traces)

    # Handle empty database case
    if total_count == 0:
        return AnalyticsResponse(
            total_count=0,
            category_breakdown=[],
            average_response_time_ms=0.0
        )

    # Calculate category breakdown
    category_counts: dict[Category, int] = {}
    total_response_time = 0

    for trace in traces:
        category_counts[trace.category] = category_counts.get(trace.category, 0) + 1
        total_response_time += trace.response_time_ms

    # Build category breakdown with percentages
    category_breakdown = [
        CategoryBreakdown(
            category=category,
            count=count,
            percentage=(count / total_count) * 100
        )
        for category, count in category_counts.items()
    ]

    # Calculate average response time
    average_response_time_ms = total_response_time / total_count

    return AnalyticsResponse(
        total_count=total_count,
        category_breakdown=category_breakdown,
        average_response_time_ms=average_response_time_ms
    )
