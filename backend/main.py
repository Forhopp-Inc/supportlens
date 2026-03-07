"""
FastAPI application for SupportLens backend.
Provides REST API endpoints for trace management, chat, and analytics.
"""

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from backend.config import get_db, get_engine, Base
from backend.gemini_client import GeminiClient
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
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )
    
    rate_limit_store[client_ip].append(current_time)


# Create FastAPI application
app = FastAPI(
    title="SupportLens API",
    description="Customer support chatbot observability platform API. "
                "Provides endpoints for chat interactions, trace management, and analytics.",
    version="1.0.0",
)

# Configure CORS middleware for frontend access
# Allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)


@app.on_event("startup")
async def startup_event():
    """Initialize database tables and load seed data on application startup."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    
    # Load seed data if database is empty
    db = next(get_db())
    try:
        loaded_count = load_seed_data(db)
        if loaded_count > 0:
            print(f"Loaded {loaded_count} seed traces into database")
    finally:
        db.close()


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint with database connectivity status.
    
    Returns:
        Health status including database connectivity
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "version": "1.0.0"
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request, db: Session = Depends(get_db)):
    """
    Process a chat message and return a support response.
    
    This endpoint:
    1. Accepts a user message and optional conversation history
    2. Generates a support response using Gemini API with context
    3. Measures response time in milliseconds
    4. Classifies the conversation into a category
    5. Stores the trace in the database
    6. Returns the response and trace ID
    
    Args:
        request: ChatRequest containing the user's message and optional history
        req: FastAPI Request object for rate limiting
        db: Database session dependency
        
    Returns:
        ChatResponse with the bot response and trace ID
        
    Raises:
        HTTPException: 429 if rate limited, 503 if LLM service is unavailable
    """
    check_rate_limit(req)
    
    gemini_client = GeminiClient()
    start_time = time.time()
    
    # Convert history to dict format for Gemini client
    history = [{"role": msg.role, "content": msg.content} for msg in request.history] if request.history else None
    
    try:
        bot_response = gemini_client.generate_response(request.message, history=history)
    except Exception as e:
        logger.error(f"Chat generation failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Support service temporarily unavailable. Please try again."
        )
    
    response_time_ms = int((time.time() - start_time) * 1000)
    category = gemini_client.classify_trace_safe(request.message)
    trace_id = str(uuid.uuid4())
    
    trace = TraceDB(
        id=trace_id,
        user_message=request.message,
        bot_response=bot_response,
        category=category,
        timestamp=datetime.utcnow(),
        response_time_ms=response_time_ms
    )
    
    try:
        db.add(trace)
        db.commit()
    except Exception as e:
        logger.error(f"Database error saving trace: {e}")
        db.rollback()
        # Still return the response even if trace storage fails
    
    return ChatResponse(response=bot_response, trace_id=trace_id)


@app.post("/traces", response_model=TraceResponse)
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
    
    Args:
        request: TraceCreate containing user_message, bot_response, response_time_ms
        db: Database session dependency
        
    Returns:
        TraceResponse with all fields including the assigned category
    """
    # Initialize Gemini client
    gemini_client = GeminiClient()
    
    # Generate unique trace ID
    trace_id = str(uuid.uuid4())
    
    # Record current timestamp
    timestamp = datetime.utcnow()
    
    # Classify the trace using Classification Engine (with fallback to General_Inquiry)
    category = gemini_client.classify_trace_safe(request.user_message)
    
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
    
    # Return complete trace object
    return TraceResponse(
        id=trace.id,
        user_message=trace.user_message,
        bot_response=trace.bot_response,
        category=trace.category,
        timestamp=trace.timestamp,
        response_time_ms=trace.response_time_ms
    )


@app.get("/traces", response_model=PaginatedTracesResponse)
async def get_traces(
    category: Category | None = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    Retrieve traces with pagination, optionally filtered by category.
    
    This endpoint:
    1. Returns traces ordered by timestamp descending (most recent first)
    2. Supports optional category query parameter for filtering
    3. Supports pagination with page and page_size parameters
    4. Returns paginated response with total count and page info
    
    Args:
        category: Optional category filter
        page: Page number (1-indexed)
        page_size: Number of items per page (max 100)
        db: Database session dependency
        
    Returns:
        PaginatedTracesResponse with traces, total count, and pagination info
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

@app.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(db: Session = Depends(get_db)):
    """
    Get aggregate analytics for all traces.

    This endpoint:
    1. Calculates total count of all traces
    2. Calculates category breakdown with count and percentage for each category
    3. Calculates average response_time_ms across all traces
    4. Returns zeros and empty breakdown when no traces exist

    Args:
        db: Database session dependency

    Returns:
        AnalyticsResponse with total_count, category_breakdown, and average_response_time_ms
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
        # Count by category
        category_counts[trace.category] = category_counts.get(trace.category, 0) + 1
        # Sum response times
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
