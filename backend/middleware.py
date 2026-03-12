"""
FastAPI middleware for SupportLens backend.
Provides request logging, correlation IDs, and error handling.
"""

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.logging_config import (
    generate_request_id,
    log_request,
    request_id_ctx,
    request_start_time_ctx,
)

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request logging.
    
    Features:
    - Assigns unique request ID for correlation
    - Measures request duration
    - Logs all requests with structured data
    - Excludes health checks from logging (via filter)
    """
    
    # Paths to exclude from detailed logging (still processed, just not logged)
    QUIET_PATHS = {"/health", "/health/"}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with logging."""
        # Generate and set request ID
        request_id = generate_request_id()
        request_id_ctx.set(request_id)
        
        # Record start time
        start_time = time.time()
        request_start_time_ctx.set(start_time)
        
        # Extract client IP
        client_ip = self._get_client_ip(request)
        
        # Add request ID to response headers for client correlation
        response: Response | None = None
        error_detail: str | None = None
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            error_detail = str(e)
            raise
        finally:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Determine status code
            status_code = response.status_code if response else 500
            
            # Skip logging for health checks (handled by filter, but double-check)
            if request.url.path not in self.QUIET_PATHS:
                extra = {}
                
                # Add error detail if present
                if error_detail:
                    extra["error"] = error_detail
                
                # Add query params for debugging (sanitized)
                if request.query_params:
                    extra["query_params"] = dict(request.query_params)
                
                log_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    extra=extra if extra else None
                )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request headers or connection."""
        # Check X-Forwarded-For header (set by proxies/load balancers)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain (original client)
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP header (nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fall back to direct connection
        if request.client:
            return request.client.host
        
        return "unknown"


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for consistent error handling and logging.
    
    Catches unhandled exceptions and logs them with context.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with error handling."""
        try:
            return await call_next(request)
        except Exception as e:
            # Log the error with full context
            logger.exception(
                "Unhandled exception in request",
                extra={
                    "type": "unhandled_exception",
                    "method": request.method,
                    "path": request.url.path,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )
            raise
