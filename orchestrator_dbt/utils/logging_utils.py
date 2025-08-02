"""
Logging utilities for orchestrator_dbt.

Provides standardized logging configuration and setup for the orchestration system.
"""

import logging
import sys
from typing import Optional
from pathlib import Path
from datetime import datetime


def setup_orchestrator_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    include_timestamp: bool = True,
    include_module: bool = True
) -> logging.Logger:
    """
    Setup standardized logging for orchestrator_dbt.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        include_timestamp: Whether to include timestamp in log format
        include_module: Whether to include module name in log format

    Returns:
        Configured logger instance
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    format_parts = []

    if include_timestamp:
        format_parts.append("%(asctime)s")

    if include_module:
        format_parts.append("%(name)s")

    format_parts.extend(["%(levelname)s", "%(message)s"])

    format_string = " - ".join(format_parts)
    formatter = logging.Formatter(
        format_string,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Add file handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Create orchestrator-specific logger
    orchestrator_logger = logging.getLogger("orchestrator_dbt")
    orchestrator_logger.info(f"Logging initialized at {level} level")

    if log_file:
        orchestrator_logger.info(f"Logging to file: {log_file}")

    return orchestrator_logger


def get_default_log_file() -> Path:
    """
    Get default log file path.

    Returns:
        Path to default log file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"logs/orchestrator_dbt_{timestamp}.log")


def setup_simple_logging(verbose: bool = False) -> None:
    """
    Setup simple logging configuration.

    Args:
        verbose: Enable verbose (DEBUG) logging
    """
    level = "DEBUG" if verbose else "INFO"
    setup_orchestrator_logging(level=level)
