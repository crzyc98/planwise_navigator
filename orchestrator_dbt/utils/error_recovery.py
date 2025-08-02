"""
Error recovery and resilience utilities for orchestrator_dbt.

Provides retry strategies, circuit breaker patterns, graceful degradation,
and comprehensive error handling for dbt workflow operations.
"""

from __future__ import annotations

import time
import logging
import random
from typing import Dict, Any, List, Optional, Callable, TypeVar, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
import traceback


logger = logging.getLogger(__name__)

T = TypeVar('T')


class ErrorType(Enum):
    """Classification of error types for recovery strategies."""
    NETWORK = "network"
    DATABASE = "database"
    COMMAND_EXECUTION = "command_execution"
    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class RetryStrategy(Enum):
    """Available retry strategies."""
    FIXED_INTERVAL = "fixed"
    EXPONENTIAL_BACKOFF = "exponential"
    LINEAR_BACKOFF = "linear"
    RANDOM_JITTER = "random"


@dataclass
class RetryConfig:
    """Configuration for retry operations."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_exceptions: List[type] = field(default_factory=lambda: [Exception])

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (1-based)

        Returns:
            Delay in seconds
        """
        if self.strategy == RetryStrategy.FIXED_INTERVAL:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.base_delay * attempt
        elif self.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.base_delay * (self.backoff_multiplier ** (attempt - 1))
        elif self.strategy == RetryStrategy.RANDOM_JITTER:
            delay = random.uniform(self.base_delay, self.base_delay * 2)
        else:
            delay = self.base_delay

        # Apply jitter if enabled
        if self.jitter and self.strategy != RetryStrategy.RANDOM_JITTER:
            jitter_factor = random.uniform(0.8, 1.2)
            delay *= jitter_factor

        # Clamp to max delay
        return min(delay, self.max_delay)


@dataclass
class ErrorInfo:
    """Information about an error occurrence."""
    error_type: ErrorType
    exception: Exception
    timestamp: datetime
    operation_name: str
    attempt_number: int
    context: Dict[str, Any] = field(default_factory=dict)
    recoverable: bool = True

    @property
    def error_message(self) -> str:
        """Get formatted error message."""
        return f"{self.exception.__class__.__name__}: {str(self.exception)}"


@dataclass
class CircuitBreakerState:
    """State of a circuit breaker."""
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    success_count: int = 0

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        return self.state == "OPEN"

    def is_half_open(self) -> bool:
        """Check if circuit breaker is half open."""
        return self.state == "HALF_OPEN"


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for preventing cascading failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        success_threshold: int = 3
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Time to wait before attempting to close circuit (seconds)
            success_threshold: Number of successes needed to close circuit from half-open
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.state = CircuitBreakerState()
        self._lock = None  # Would use threading.Lock() in production

    def can_execute(self) -> bool:
        """
        Check if operation can be executed.

        Returns:
            True if operation can proceed
        """
        if self.state.state == "CLOSED":
            return True

        if self.state.state == "OPEN":
            if self.state.last_failure_time:
                time_since_failure = datetime.now() - self.state.last_failure_time
                if time_since_failure.total_seconds() >= self.timeout:
                    self.state.state = "HALF_OPEN"
                    self.state.success_count = 0
                    logger.info(f"Circuit breaker transitioning to HALF_OPEN state")
                    return True
            return False

        # HALF_OPEN state
        return True

    def record_success(self):
        """Record a successful operation."""
        if self.state.state == "HALF_OPEN":
            self.state.success_count += 1
            if self.state.success_count >= self.success_threshold:
                self.state.state = "CLOSED"
                self.state.failure_count = 0
                logger.info(f"Circuit breaker closed after {self.state.success_count} successes")
        elif self.state.state == "CLOSED":
            self.state.failure_count = 0

    def record_failure(self):
        """Record a failed operation."""
        self.state.failure_count += 1
        self.state.last_failure_time = datetime.now()

        if self.state.state == "CLOSED" and self.state.failure_count >= self.failure_threshold:
            self.state.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.state.failure_count} failures")
        elif self.state.state == "HALF_OPEN":
            self.state.state = "OPEN"
            logger.warning(f"Circuit breaker re-opened during half-open state")


class ErrorRecoveryManager:
    """
    Comprehensive error recovery and resilience manager.

    Provides retry mechanisms, circuit breakers, error classification,
    and recovery strategies for robust workflow execution.
    """

    def __init__(self):
        """Initialize error recovery manager."""
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.error_history: List[ErrorInfo] = []
        self.recovery_strategies: Dict[ErrorType, RetryConfig] = self._init_default_strategies()

    def _init_default_strategies(self) -> Dict[ErrorType, RetryConfig]:
        """Initialize default recovery strategies for different error types."""
        return {
            ErrorType.NETWORK: RetryConfig(
                max_attempts=5,
                base_delay=2.0,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                backoff_multiplier=2.0
            ),
            ErrorType.DATABASE: RetryConfig(
                max_attempts=3,
                base_delay=1.0,
                strategy=RetryStrategy.LINEAR_BACKOFF
            ),
            ErrorType.COMMAND_EXECUTION: RetryConfig(
                max_attempts=2,
                base_delay=0.5,
                strategy=RetryStrategy.FIXED_INTERVAL
            ),
            ErrorType.RESOURCE: RetryConfig(
                max_attempts=4,
                base_delay=3.0,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                max_delay=30.0
            ),
            ErrorType.CONFIGURATION: RetryConfig(
                max_attempts=1,  # Don't retry config errors
                base_delay=0.0
            ),
            ErrorType.UNKNOWN: RetryConfig(
                max_attempts=2,
                base_delay=1.0,
                strategy=RetryStrategy.FIXED_INTERVAL
            )
        }

    def classify_error(self, exception: Exception, context: Dict[str, Any] = None) -> ErrorType:
        """
        Classify an error to determine appropriate recovery strategy.

        Args:
            exception: Exception to classify
            context: Additional context information

        Returns:
            ErrorType classification
        """
        error_message = str(exception).lower()

        # Network-related errors
        if any(keyword in error_message for keyword in ['connection', 'timeout', 'network', 'dns']):
            return ErrorType.NETWORK

        # Database-related errors
        if any(keyword in error_message for keyword in ['database', 'sql', 'duckdb', 'table', 'schema']):
            return ErrorType.DATABASE

        # Command execution errors
        if any(keyword in error_message for keyword in ['command', 'dbt', 'executable', 'process']):
            return ErrorType.COMMAND_EXECUTION

        # Resource errors
        if any(keyword in error_message for keyword in ['memory', 'disk', 'space', 'resource', 'permission']):
            return ErrorType.RESOURCE

        # Configuration errors
        if any(keyword in error_message for keyword in ['config', 'setting', 'parameter', 'variable']):
            return ErrorType.CONFIGURATION

        return ErrorType.UNKNOWN

    def is_retryable(self, exception: Exception, error_type: ErrorType) -> bool:
        """
        Determine if an error is retryable.

        Args:
            exception: Exception to check
            error_type: Classified error type

        Returns:
            True if error should be retried
        """
        # Configuration errors are typically not retryable
        if error_type == ErrorType.CONFIGURATION:
            return False

        # Check specific exceptions that should not be retried
        non_retryable_messages = [
            'file not found',
            'permission denied',
            'invalid syntax',
            'parse error',
            'schema mismatch'
        ]

        error_message = str(exception).lower()
        for message in non_retryable_messages:
            if message in error_message:
                return False

        return True

    def get_circuit_breaker(self, operation_name: str) -> CircuitBreaker:
        """
        Get or create circuit breaker for an operation.

        Args:
            operation_name: Name of the operation

        Returns:
            CircuitBreaker instance
        """
        if operation_name not in self.circuit_breakers:
            self.circuit_breakers[operation_name] = CircuitBreaker()
        return self.circuit_breakers[operation_name]

    def retry_with_recovery(
        self,
        func: Callable[..., T],
        operation_name: str,
        *args,
        retry_config: Optional[RetryConfig] = None,
        use_circuit_breaker: bool = True,
        **kwargs
    ) -> T:
        """
        Execute function with retry and recovery logic.

        Args:
            func: Function to execute
            operation_name: Name of the operation for tracking
            *args: Arguments to pass to function
            retry_config: Custom retry configuration
            use_circuit_breaker: Whether to use circuit breaker
            **kwargs: Keyword arguments to pass to function

        Returns:
            Function result

        Raises:
            Exception: If all retry attempts fail
        """
        circuit_breaker = self.get_circuit_breaker(operation_name) if use_circuit_breaker else None
        last_exception = None

        # Check circuit breaker
        if circuit_breaker and not circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker is open for operation: {operation_name}")

        for attempt in range(1, (retry_config.max_attempts if retry_config else 3) + 1):
            try:
                logger.debug(f"Attempting {operation_name} (attempt {attempt})")
                result = func(*args, **kwargs)

                # Record success
                if circuit_breaker:
                    circuit_breaker.record_success()

                if attempt > 1:
                    logger.info(f"Operation {operation_name} succeeded on attempt {attempt}")

                return result

            except Exception as e:
                last_exception = e
                error_type = self.classify_error(e)

                # Record error
                error_info = ErrorInfo(
                    error_type=error_type,
                    exception=e,
                    timestamp=datetime.now(),
                    operation_name=operation_name,
                    attempt_number=attempt,
                    recoverable=self.is_retryable(e, error_type)
                )\n                self.error_history.append(error_info)

                # Record failure in circuit breaker
                if circuit_breaker:
                    circuit_breaker.record_failure()

                # Check if error is retryable
                if not error_info.recoverable:
                    logger.error(f"Non-retryable error in {operation_name}: {e}")
                    raise e

                # Check if we should retry
                config = retry_config or self.recovery_strategies.get(error_type, self.recovery_strategies[ErrorType.UNKNOWN])

                if attempt >= config.max_attempts:
                    logger.error(f"Operation {operation_name} failed after {attempt} attempts")
                    raise e

                # Calculate and apply delay
                delay = config.calculate_delay(attempt)
                logger.warning(f"Operation {operation_name} failed (attempt {attempt}), retrying in {delay:.2f}s: {e}")
                time.sleep(delay)

        # This should not be reached, but just in case
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError(f"Operation {operation_name} failed with unknown error")

    def with_recovery(
        self,
        operation_name: str,
        retry_config: Optional[RetryConfig] = None,
        use_circuit_breaker: bool = True
    ):
        """
        Decorator for adding recovery logic to functions.

        Args:
            operation_name: Name of the operation
            retry_config: Custom retry configuration
            use_circuit_breaker: Whether to use circuit breaker

        Returns:
            Decorated function
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                return self.retry_with_recovery(
                    func,
                    operation_name,
                    *args,
                    retry_config=retry_config,
                    use_circuit_breaker=use_circuit_breaker,
                    **kwargs
                )
            return wrapper
        return decorator

    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get summary of error history and circuit breaker states.

        Returns:
            Dictionary with error summary
        """
        if not self.error_history:
            return {
                "total_errors": 0,
                "error_types": {},
                "circuit_breakers": {},
                "recent_errors": []
            }

        # Error type distribution
        error_types = {}
        for error in self.error_history:
            error_type = error.error_type.value
            error_types[error_type] = error_types.get(error_type, 0) + 1

        # Circuit breaker states
        circuit_breaker_states = {
            name: {
                "state": cb.state.state,
                "failure_count": cb.state.failure_count,
                "success_count": cb.state.success_count,
                "last_failure": cb.state.last_failure_time.isoformat() if cb.state.last_failure_time else None
            }
            for name, cb in self.circuit_breakers.items()
        }

        # Recent errors (last 10)
        recent_errors = [
            {
                "operation": error.operation_name,
                "error_type": error.error_type.value,
                "message": error.error_message,
                "timestamp": error.timestamp.isoformat(),
                "attempt": error.attempt_number,
                "recoverable": error.recoverable
            }
            for error in self.error_history[-10:]
        ]

        return {
            "total_errors": len(self.error_history),
            "error_types": error_types,
            "circuit_breakers": circuit_breaker_states,
            "recent_errors": recent_errors
        }

    def clear_history(self):
        """Clear error history and reset circuit breakers."""
        self.error_history.clear()
        for circuit_breaker in self.circuit_breakers.values():
            circuit_breaker.state = CircuitBreakerState()
        logger.info("Error history and circuit breakers cleared")


# Global error recovery manager instance
error_recovery = ErrorRecoveryManager()


def with_retry(
    operation_name: str,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
):
    """
    Simplified decorator for adding retry logic.

    Args:
        operation_name: Name of the operation
        max_attempts: Maximum retry attempts
        base_delay: Base delay between retries
        strategy: Retry strategy to use

    Returns:
        Decorated function
    """
    retry_config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        strategy=strategy
    )

    return error_recovery.with_recovery(
        operation_name=operation_name,
        retry_config=retry_config,
        use_circuit_breaker=True
    )


class ErrorRecoveryError(Exception):
    """Exception raised for error recovery system errors."""
    pass
