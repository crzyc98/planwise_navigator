"""
Structured JSON Logging System for PlanWise Navigator

Provides enterprise-grade logging with JSON structure, run correlation,
and performance monitoring capabilities for production observability.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional
import sys


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs"""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "run_id": self.run_id,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.thread,
            "process": record.process,
        }

        # Add exception information if present
        if record.exc_info:
            # Ensure exc_info is a tuple; logger.makeRecord may receive True if misused
            exc_info = (
                record.exc_info if isinstance(record.exc_info, tuple) else sys.exc_info()
            )
            if exc_info and isinstance(exc_info, tuple):
                log_data["exception"] = {
                    "type": exc_info[0].__name__ if exc_info[0] else None,
                    "message": str(exc_info[1]) if exc_info[1] else None,
                    "traceback": self.formatException(exc_info),
                }

        # Add any extra data attached to the record
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data, ensure_ascii=False)


class ProductionLogger:
    """
    Enterprise production logger with structured JSON output, run correlation,
    and automatic log rotation.

    Features:
    - Structured JSON logging for machine parsing
    - Run ID correlation for tracing simulation executions
    - Dual output: JSON to file, human-readable to console
    - Automatic log rotation to prevent disk exhaustion
    - Context-aware logging with custom fields
    """

    def __init__(self, run_id: Optional[str] = None, log_level: str = "INFO"):
        """
        Initialize production logger

        Args:
            run_id: Unique identifier for this simulation run. Generated if not provided.
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.run_id = run_id or self._generate_run_id()
        self.log_level = getattr(logging, log_level.upper())
        self._setup_logging()

    def _generate_run_id(self) -> str:
        """Generate unique run ID with timestamp and UUID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_suffix = str(uuid.uuid4())[:8]
        return f"{timestamp}-{unique_suffix}"

    def _setup_logging(self) -> None:
        """Setup dual console + file logging with rotation"""
        # Ensure logs directory exists
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # Create logger instance
        self.logger = logging.getLogger(f"navigator.{self.run_id}")
        self.logger.setLevel(self.log_level)

        # Prevent duplicate handlers if logger already exists
        if self.logger.handlers:
            return

        # JSON file handler with rotation (10MB, keep 10 files)
        json_handler = RotatingFileHandler(
            logs_dir / "navigator.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
        )
        json_handler.setFormatter(JSONFormatter(self.run_id))
        json_handler.setLevel(self.log_level)

        # Console handler for human-readable output
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(self.log_level)

        # Add handlers to logger
        self.logger.addHandler(json_handler)
        self.logger.addHandler(console_handler)

        # Prevent propagation to root logger
        self.logger.propagate = False

    def log_event(self, level: str, message: str, **kwargs) -> None:
        """
        Log structured event with additional context

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Human-readable log message
            **kwargs: Additional structured data to include in JSON
        """
        # Create custom log record with extra data
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=getattr(logging, level.upper()),
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        record.extra_data = kwargs

        # Handle the record
        self.logger.handle(record)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self.log_event("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self.log_event("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self.log_event("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        self.log_event("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message"""
        self.log_event("CRITICAL", message, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback"""
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=logging.ERROR,
            fn="",
            lno=0,
            msg=message,
            args=(),
            # Capture current exception info tuple explicitly
            exc_info=sys.exc_info(),
        )
        record.extra_data = kwargs
        self.logger.handle(record)

    def get_run_id(self) -> str:
        """Get the run ID for this logger instance"""
        return self.run_id

    def close(self) -> None:
        """Close all handlers and cleanup"""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


def get_logger(
    run_id: Optional[str] = None, log_level: str = "INFO"
) -> ProductionLogger:
    """
    Factory function to get a configured production logger

    Args:
        run_id: Optional run ID. Generated if not provided.
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured ProductionLogger instance
    """
    return ProductionLogger(run_id=run_id, log_level=log_level)
