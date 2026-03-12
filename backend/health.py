"""
Health check module for SupportLens backend.
Provides comprehensive health status with dependency checks.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Application start time for uptime calculation
_start_time: float = time.time()


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DependencyStatus(BaseModel):
    """Status of a single dependency."""
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """
    Comprehensive health check response.
    
    Design decisions:
    - 'status' reflects overall application health for load balancer decisions
    - 'can_serve_traffic' is the key field for orchestrators to check
    - Individual dependency statuses allow operators to diagnose issues
    - 'uptime_seconds' helps identify recent restarts
    """
    status: HealthStatus
    can_serve_traffic: bool = Field(
        description="Whether the application can meaningfully serve requests"
    )
    timestamp: str
    version: str
    uptime_seconds: float
    dependencies: dict[str, DependencyStatus]
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "can_serve_traffic": True,
                "timestamp": "2024-01-15T10:30:00Z",
                "version": "1.0.0",
                "uptime_seconds": 3600.5,
                "dependencies": {
                    "database": {
                        "status": "healthy",
                        "latency_ms": 5.2,
                        "message": None
                    },
                    "llm": {
                        "status": "healthy",
                        "latency_ms": None,
                        "message": "API key configured"
                    }
                }
            }
        }


def get_uptime_seconds() -> float:
    """Get application uptime in seconds."""
    return round(time.time() - _start_time, 2)


def check_database_health(db: Session) -> DependencyStatus:
    """
    Check database connectivity and responsiveness.
    
    Returns:
        DependencyStatus with connection status and latency
    """
    start = time.time()
    try:
        # Execute a simple query to verify connectivity
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        latency_ms = (time.time() - start) * 1000
        
        return DependencyStatus(
            status=HealthStatus.HEALTHY,
            latency_ms=round(latency_ms, 2),
            message=None
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        logger.error(f"Database health check failed: {e}", extra={
            "dependency": "database",
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        return DependencyStatus(
            status=HealthStatus.UNHEALTHY,
            latency_ms=round(latency_ms, 2),
            message=f"Connection failed: {type(e).__name__}",
            details={"error": str(e)}
        )


def check_llm_health() -> DependencyStatus:
    """
    Check LLM provider availability.
    
    Design decision: We check if the API key is configured, not if the API is reachable.
    
    Rationale:
    - Making actual API calls on every health check would be expensive and slow
    - The app gracefully degrades without LLM (fallback classification, error responses)
    - A missing API key is a configuration issue, not a runtime failure
    - We report 'degraded' (not 'unhealthy') because core functionality still works
    
    Returns:
        DependencyStatus indicating LLM configuration status
    """
    settings = get_settings()
    api_key = settings.gemini_api_key
    
    if api_key and len(api_key) > 10:  # Basic validation
        return DependencyStatus(
            status=HealthStatus.HEALTHY,
            latency_ms=None,
            message="API key configured",
            details={"key_length": len(api_key)}
        )
    elif api_key:
        # Key exists but looks invalid (too short)
        return DependencyStatus(
            status=HealthStatus.DEGRADED,
            latency_ms=None,
            message="API key configured but may be invalid (too short)",
            details={"key_length": len(api_key)}
        )
    else:
        # No API key - app will use fallback behavior
        return DependencyStatus(
            status=HealthStatus.DEGRADED,
            latency_ms=None,
            message="No API key configured - using fallback classification",
            details={
                "fallback_behavior": "Classification defaults to General_Inquiry",
                "chat_behavior": "Chat endpoint will return 503 errors"
            }
        )


def get_health_status(db: Session) -> HealthResponse:
    """
    Perform comprehensive health check.
    
    Health status logic:
    - HEALTHY: All dependencies operational
    - DEGRADED: Some dependencies unavailable but app can serve traffic
    - UNHEALTHY: Critical dependencies down, cannot serve traffic
    
    The 'can_serve_traffic' field is the key decision point:
    - True if database is healthy (we can read/write traces)
    - False if database is down (core functionality broken)
    
    LLM being unavailable does NOT make us unhealthy because:
    - Traces can still be created with fallback classification
    - Analytics and trace retrieval still work
    - Only chat generation fails (returns 503)
    
    Returns:
        HealthResponse with complete system status
    """
    # Check all dependencies
    db_status = check_database_health(db)
    llm_status = check_llm_health()
    
    dependencies = {
        "database": db_status,
        "llm": llm_status
    }
    
    # Determine overall status
    # Database is critical - if it's down, we're unhealthy
    if db_status.status == HealthStatus.UNHEALTHY:
        overall_status = HealthStatus.UNHEALTHY
        can_serve = False
    # LLM degraded but database healthy = degraded but can serve
    elif llm_status.status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY):
        overall_status = HealthStatus.DEGRADED
        can_serve = True  # Core functionality still works
    else:
        overall_status = HealthStatus.HEALTHY
        can_serve = True
    
    return HealthResponse(
        status=overall_status,
        can_serve_traffic=can_serve,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        uptime_seconds=get_uptime_seconds(),
        dependencies=dependencies
    )
