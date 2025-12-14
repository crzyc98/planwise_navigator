# Internal API Contracts: Self-Healing dbt Initialization

**Feature Branch**: `006-self-healing-dbt-init`
**Date**: 2025-12-12

This document defines the internal Python API contracts for the self-healing initialization module. These are not REST APIs but Python class interfaces.

## TableExistenceChecker

**Module**: `planalign_orchestrator.self_healing.table_checker`

```python
class TableExistenceChecker:
    """Checks for existence of required database tables."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """
        Initialize checker with database connection manager.

        Args:
            db_manager: Connection manager for database access
        """

    def get_existing_tables(self) -> set[str]:
        """
        Query database for all existing table names.

        Returns:
            Set of table names in the 'main' schema

        Raises:
            DatabaseError: If database query fails
        """

    def get_missing_tables(self) -> list[RequiredTable]:
        """
        Compare required tables against existing tables.

        Returns:
            List of RequiredTable objects that don't exist in database

        Note:
            Uses REQUIRED_TABLES constant for comparison
        """

    def is_initialized(self) -> bool:
        """
        Check if all required tables exist.

        Returns:
            True if all REQUIRED_TABLES exist, False otherwise
        """

    def get_missing_by_tier(self) -> dict[TableTier, list[RequiredTable]]:
        """
        Group missing tables by their initialization tier.

        Returns:
            Dict mapping TableTier to list of missing RequiredTable objects
            Empty dict if no tables missing
        """
```

## AutoInitializer

**Module**: `planalign_orchestrator.self_healing.auto_initializer`

```python
class AutoInitializer:
    """Orchestrates automatic database initialization."""

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        dbt_runner: DbtRunner,
        *,
        verbose: bool = False,
        timeout_seconds: float = 60.0,
    ) -> None:
        """
        Initialize auto-initializer with dependencies.

        Args:
            db_manager: Connection manager for database access
            dbt_runner: Runner for executing dbt commands
            verbose: Enable verbose progress output
            timeout_seconds: Maximum time for initialization (default: 60s per SC-003)
        """

    def ensure_initialized(self) -> InitializationResult:
        """
        Ensure database is fully initialized, running initialization if needed.

        This is the main entry point, designed to be called as a pre-simulation hook.

        Returns:
            InitializationResult with state=COMPLETED if successful

        Raises:
            InitializationError: If initialization fails
            InitializationTimeoutError: If initialization exceeds timeout
            ConcurrentInitializationError: If another initialization is in progress

        Behavior:
            1. Acquires mutex lock (fails fast if already held)
            2. Checks for missing tables
            3. If all tables exist, returns immediately with COMPLETED
            4. If tables missing, runs full initialization sequence
            5. Verifies all tables exist after initialization
            6. Releases mutex lock

        Thread Safety:
            Uses file-based mutex to prevent concurrent initialization
        """

    def run_initialization(self, missing_tables: list[RequiredTable]) -> InitializationResult:
        """
        Run full initialization sequence for missing tables.

        Args:
            missing_tables: List of tables that need to be created

        Returns:
            InitializationResult with detailed step information

        Raises:
            InitializationError: If any step fails

        Steps:
            1. Load seed data (dbt seed --full-refresh)
            2. Build foundation models (dbt run --select tag:foundation)
            3. Verify all tables exist
        """

    def _execute_step(
        self,
        step: InitializationStep,
        action: Callable[[], None],
    ) -> InitializationStep:
        """
        Execute a single initialization step with timing and error handling.

        Args:
            step: Step definition to execute
            action: Callable that performs the step

        Returns:
            Updated InitializationStep with timing and result

        Note:
            Internal method, not part of public API
        """
```

## HookManager Extensions

**Module**: `planalign_orchestrator.pipeline.hooks` (existing, to be extended)

```python
# Add to existing HookManager class

class HookManager:
    # ... existing methods ...

    def register_pre_simulation_hook(
        self,
        hook: Callable[[], None],
        *,
        name: str = "unnamed",
        priority: int = 0,
    ) -> None:
        """
        Register a hook to run before simulation starts.

        Args:
            hook: Callable to execute before simulation
            name: Descriptive name for logging
            priority: Execution order (lower = earlier, default 0)

        Note:
            Pre-simulation hooks run once per execute_multi_year_simulation() call,
            not once per year.
        """

    def run_pre_simulation_hooks(self) -> None:
        """
        Execute all registered pre-simulation hooks in priority order.

        Raises:
            HookError: If any hook raises an exception (stops execution)

        Note:
            Called automatically at the start of execute_multi_year_simulation()
        """
```

## Exception Classes

**Module**: `planalign_orchestrator.exceptions` (existing, to be extended)

```python
class InitializationError(NavigatorError):
    """Base exception for initialization failures."""

    def __init__(
        self,
        message: str,
        *,
        step: str | None = None,
        missing_tables: list[str] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """
        Create initialization error with context.

        Args:
            message: Human-readable error description
            step: Which initialization step failed
            missing_tables: Tables that couldn't be created
            original_error: Underlying exception if any
        """


class InitializationTimeoutError(InitializationError):
    """Raised when initialization exceeds timeout."""

    def __init__(
        self,
        timeout_seconds: float,
        elapsed_seconds: float,
    ) -> None:
        """
        Create timeout error.

        Args:
            timeout_seconds: Configured timeout
            elapsed_seconds: Actual elapsed time
        """


class ConcurrentInitializationError(InitializationError):
    """Raised when another initialization is already in progress."""

    def __init__(self, lock_file: Path) -> None:
        """
        Create concurrency error.

        Args:
            lock_file: Path to the held lock file
        """


class DatabaseCorruptionError(InitializationError):
    """Raised when database file is corrupted."""

    def __init__(
        self,
        db_path: Path,
        *,
        original_error: Exception | None = None,
    ) -> None:
        """
        Create corruption error.

        Args:
            db_path: Path to corrupted database
            original_error: DuckDB exception with details
        """
```

## Factory Integration

**Module**: `planalign_orchestrator.factory` (existing, to be modified)

```python
def create_orchestrator(
    config_or_path: SimulationConfig | Path | str,
    db_manager: DatabaseConnectionManager | None = None,
    *,
    threads: int = 1,
    db_path: Path | str | None = None,
    dbt_executable: str = "dbt",
    auto_initialize: bool = True,  # NEW PARAMETER
) -> PipelineOrchestrator:
    """
    Create a PipelineOrchestrator with optional auto-initialization.

    Args:
        config_or_path: Configuration or path to config file
        db_manager: Optional database manager
        threads: dbt thread count
        db_path: Database path (if db_manager not provided)
        dbt_executable: Path to dbt executable
        auto_initialize: Enable automatic database initialization (default: True)

    Returns:
        Configured PipelineOrchestrator

    Note:
        When auto_initialize=True, the orchestrator's HookManager will have
        AutoInitializer.ensure_initialized registered as a pre-simulation hook.
    """
```

## Usage Example

```python
from planalign_orchestrator.factory import create_orchestrator

# Auto-initialization enabled by default
orchestrator = create_orchestrator("config/simulation_config.yaml")

# First simulation in new workspace - initializes automatically
summary = orchestrator.execute_multi_year_simulation(
    start_year=2025,
    end_year=2027
)

# Subsequent runs skip initialization (tables already exist)
summary = orchestrator.execute_multi_year_simulation(
    start_year=2025,
    end_year=2027
)
```
