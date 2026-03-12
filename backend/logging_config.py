"""
Structured JSON logging configuration for SupportLens backend.
Provides enterprise-grade request logging with correlation IDs.
"""

import json
import logging
import sys
import uuid
from collections import deque
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable for request correlation
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
request_start_time_ctx: ContextVar[float] = ContextVar("request_start_time", default=0.0)

# In-memory log buffer for recent logs (max 500 entries)
log_buffer: deque = deque(maxlen=500)


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    Outputs logs in a format suitable for log aggregation systems.
    """

    EXCLUDED_ATTRS = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName"
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request correlation ID if available
        request_id = request_id_ctx.get()
        if request_id:
            log_entry["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the record
        for key, value in record.__dict__.items():
            if key not in self.EXCLUDED_ATTRS and not key.startswith("_"):
                try:
                    # Ensure value is JSON serializable
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        # Store in buffer for API access
        log_buffer.append(log_entry)

        return json.dumps(log_entry, default=str)


class HealthCheckFilter(logging.Filter):
    """
    Filter to exclude health check requests from logs.
    Prevents log flooding from orchestrator health probes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to exclude health check logs."""
        message = record.getMessage()
        # Exclude health endpoint requests
        if "/health" in message and "GET" in message:
            return False
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structured JSON logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create stdout handler with JSON formatter
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JSONFormatter())
    stdout_handler.addFilter(HealthCheckFilter())

    root_logger.addHandler(stdout_handler)

    # Configure uvicorn access logger to use our format
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.addHandler(stdout_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def generate_request_id() -> str:
    """Generate a unique request ID for correlation."""
    return str(uuid.uuid4())[:8]


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: str,
    extra: dict[str, Any] | None = None
) -> None:
    """
    Log an HTTP request with structured data.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP response status code
        duration_ms: Request duration in milliseconds
        client_ip: Client IP address
        extra: Additional context to include in log
    """
    logger = logging.getLogger("supportlens.request")

    log_data = {
        "type": "request",
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "client_ip": client_ip,
    }

    if extra:
        log_data.update(extra)

    # Determine log level based on status code
    if status_code >= 500:
        logger.error("Request completed", extra=log_data)
    elif status_code >= 400:
        logger.warning("Request completed", extra=log_data)
    else:
        logger.info("Request completed", extra=log_data)


def get_recent_logs(limit: int = 100, level: str | None = None) -> list[dict]:
    """
    Get recent logs from the in-memory buffer.

    Args:
        limit: Maximum number of logs to return
        level: Optional filter by log level (INFO, WARNING, ERROR, etc.)

    Returns:
        List of log entries (newest first)
    """
    logs = list(log_buffer)

    # Filter by level if specified
    if level:
        level_upper = level.upper()
        logs = [log for log in logs if log.get("level") == level_upper]

    # Return newest first, limited
    return list(reversed(logs))[:limit]
