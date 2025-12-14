"""
Auto Initializer for Self-Healing dbt Initialization.

Orchestrates automatic database initialization by detecting missing tables
and running dbt commands to create them. This eliminates "table does not exist"
errors for first-time simulations in new workspaces.

Usage:
    from planalign_orchestrator.self_healing import AutoInitializer

    initializer = AutoInitializer(db_manager, dbt_runner, verbose=True)
    result = initializer.ensure_initialized()

    if result.success:
        print("Database ready for simulation")
    else:
        print(f"Initialization failed: {result.error}")
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from planalign_orchestrator.dbt_runner import DbtRunner, DbtResult
from planalign_orchestrator.exceptions import (
    InitializationError,
    InitializationTimeoutError,
    ConcurrentInitializationError,
    DatabaseCorruptionError,
)
from planalign_orchestrator.self_healing.initialization_state import (
    InitializationState,
    InitializationStep,
    InitializationResult,
    TableTier,
    RequiredTable,
    REQUIRED_TABLES,
    create_standard_steps,
)
from planalign_orchestrator.self_healing.table_checker import TableExistenceChecker
from planalign_orchestrator.utils import DatabaseConnectionManager, ExecutionMutex

logger = logging.getLogger(__name__)

# Lock name for initialization mutex
INIT_LOCK_NAME = "planalign_init"


class AutoInitializer:
    """Orchestrates automatic database initialization.

    Detects missing required tables and runs dbt commands to create them.
    Provides progress feedback and structured logging for enterprise
    transparency (NFR-001, NFR-002).

    Attributes:
        db_manager: Database connection manager
        dbt_runner: dbt command runner
        verbose: Enable verbose progress output
        timeout_seconds: Maximum time for initialization (default: 60s per SC-003)

    Example:
        >>> initializer = AutoInitializer(db_manager, dbt_runner, verbose=True)
        >>> result = initializer.ensure_initialized()
        >>> if result.success:
        ...     print(f"Initialized in {result.duration_seconds:.1f}s")
    """

    DEFAULT_TIMEOUT_SECONDS = 60.0

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        dbt_runner: DbtRunner,
        *,
        verbose: bool = False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        use_lock: bool = True,
    ) -> None:
        """Initialize auto-initializer with dependencies.

        Args:
            db_manager: Connection manager for database access
            dbt_runner: Runner for executing dbt commands
            verbose: Enable verbose progress output
            timeout_seconds: Maximum time for initialization (default: 60s per SC-003)
            use_lock: Use file-based mutex to prevent concurrent initialization
        """
        self.db_manager = db_manager
        self.dbt_runner = dbt_runner
        self.verbose = verbose
        self.timeout_seconds = timeout_seconds
        self.use_lock = use_lock
        self._checker = TableExistenceChecker(db_manager)
        self._start_time: Optional[float] = None
        self._lock: Optional[ExecutionMutex] = None

    def ensure_initialized(self) -> InitializationResult:
        """Ensure database is fully initialized, running initialization if needed.

        This is the main entry point, designed to be called as a pre-simulation hook.

        Returns:
            InitializationResult with state=COMPLETED if successful

        Raises:
            InitializationError: If initialization fails
            InitializationTimeoutError: If initialization exceeds timeout
            ConcurrentInitializationError: If another initialization is in progress

        Behavior:
            1. Checks for missing tables
            2. If all tables exist, returns immediately with COMPLETED
            3. If tables missing, runs full initialization sequence
            4. Verifies all tables exist after initialization
        """
        self._start_time = time.time()
        started_at = datetime.now()
        steps = create_standard_steps()

        # Step 1: Check tables
        check_step = steps[0]
        check_step = self._execute_step(
            check_step,
            lambda: None  # Just timing, actual check follows
        )
        steps[0] = check_step

        # Check if already initialized
        if self._checker.is_initialized():
            if self.verbose:
                print("✅ Database already initialized - skipping initialization")

            logger.info("Database already initialized, skipping initialization")
            return InitializationResult(
                state=InitializationState.COMPLETED,
                started_at=started_at,
                completed_at=datetime.now(),
                steps=steps,
                missing_tables_found=[],
                tables_created=[],
            )

        # Get missing tables
        missing_tables = self._checker.get_missing_tables()
        missing_names = [t.name for t in missing_tables]

        if self.verbose:
            print(f"⚠️  Missing {len(missing_tables)} required tables")
            for t in missing_tables:
                print(f"   - {t.name} ({t.tier.value})")

        logger.info(
            "Database needs initialization",
            extra={
                "missing_count": len(missing_tables),
                "missing_tables": missing_names,
            }
        )

        # Acquire initialization lock if enabled
        if self.use_lock:
            self._lock = ExecutionMutex(INIT_LOCK_NAME)
            lock_file = str(self._lock.lock_file)
            if not self._lock.acquire(timeout=5):
                # Another initialization is in progress
                raise ConcurrentInitializationError(lock_file=lock_file)
            if self.verbose:
                print(f"🔒 Acquired initialization lock: {lock_file}")

        try:
            # Run full initialization
            return self.run_initialization(missing_tables, started_at, steps)
        finally:
            # Release lock
            if self._lock:
                self._lock.release()
                if self.verbose:
                    print("🔓 Released initialization lock")

    def run_initialization(
        self,
        missing_tables: List[RequiredTable],
        started_at: datetime,
        steps: List[InitializationStep],
    ) -> InitializationResult:
        """Run full initialization sequence for missing tables.

        Args:
            missing_tables: List of tables that need to be created
            started_at: When initialization started
            steps: List of initialization steps to update

        Returns:
            InitializationResult with detailed step information

        Raises:
            InitializationError: If any step fails

        Steps:
            1. Load seed data (dbt seed --full-refresh)
            2. Build foundation models (dbt run --select tag:FOUNDATION)
            3. Verify all tables exist
        """
        missing_names = [t.name for t in missing_tables]
        tables_created: List[str] = []

        try:
            # Step 2: Load seeds
            load_seeds_step = steps[1]
            load_seeds_step = self._execute_step(
                load_seeds_step,
                lambda: self._run_dbt_seed()
            )
            steps[1] = load_seeds_step

            if not load_seeds_step.success:
                return self._create_failed_result(
                    started_at, steps, missing_names, tables_created,
                    load_seeds_step.error_message or "Seed loading failed"
                )

            # Track created seed tables
            for t in missing_tables:
                if t.tier == TableTier.SEED:
                    tables_created.append(t.name)

            self._check_timeout()

            # Step 3: Build foundation models
            build_step = steps[2]
            build_step = self._execute_step(
                build_step,
                lambda: self._run_dbt_foundation()
            )
            steps[2] = build_step

            if not build_step.success:
                return self._create_failed_result(
                    started_at, steps, missing_names, tables_created,
                    build_step.error_message or "Foundation model build failed"
                )

            # Track created foundation tables
            for t in missing_tables:
                if t.tier == TableTier.FOUNDATION:
                    tables_created.append(t.name)

            self._check_timeout()

            # Step 4: Verify initialization
            verify_step = steps[3]
            verify_step = self._execute_step(
                verify_step,
                lambda: self._verify_initialization()
            )
            steps[3] = verify_step

            if not verify_step.success:
                return self._create_failed_result(
                    started_at, steps, missing_names, tables_created,
                    verify_step.error_message or "Verification failed"
                )

            # Success!
            completed_at = datetime.now()

            if self.verbose:
                duration = (completed_at - started_at).total_seconds()
                print(f"✅ Initialization complete ({duration:.1f}s)")

            logger.info(
                "Initialization completed successfully",
                extra={
                    "duration_seconds": (completed_at - started_at).total_seconds(),
                    "tables_created": tables_created,
                }
            )

            return InitializationResult(
                state=InitializationState.COMPLETED,
                started_at=started_at,
                completed_at=completed_at,
                steps=steps,
                missing_tables_found=missing_names,
                tables_created=tables_created,
            )

        except InitializationTimeoutError:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Initialization failed: {error_msg}")
            return self._create_failed_result(
                started_at, steps, missing_names, tables_created, error_msg
            )

    def _execute_step(
        self,
        step: InitializationStep,
        action: Callable[[], None],
    ) -> InitializationStep:
        """Execute a single initialization step with timing and error handling.

        Args:
            step: Step definition to execute
            action: Callable that performs the step

        Returns:
            Updated InitializationStep with timing and result
        """
        started_at = datetime.now()

        if self.verbose:
            print(f"🔄 {step.display_name}...")

        logger.info(
            "initialization_step_start",
            extra={
                "step_name": step.name,
                "started_at": started_at.isoformat(),
            }
        )

        try:
            action()
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            # Log structured step completion per NFR-001/NFR-002
            logger.info(
                "initialization_step_complete",
                extra={
                    "event": "initialization_step_complete",
                    "step_name": step.name,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": duration,
                    "success": True,
                }
            )

            if self.verbose:
                print(f"   ✓ {step.display_name} ({duration:.1f}s)")

            return InitializationStep(
                name=step.name,
                display_name=step.display_name,
                started_at=started_at,
                completed_at=completed_at,
                success=True,
            )

        except Exception as e:
            completed_at = datetime.now()
            error_msg = str(e)

            logger.error(
                "initialization_step_complete",
                extra={
                    "event": "initialization_step_complete",
                    "step_name": step.name,
                    "started_at": started_at.isoformat(),
                    "completed_at": completed_at.isoformat(),
                    "duration_seconds": (completed_at - started_at).total_seconds(),
                    "success": False,
                    "error": error_msg,
                }
            )

            if self.verbose:
                print(f"   ✗ {step.display_name} failed: {error_msg}")

            return InitializationStep(
                name=step.name,
                display_name=step.display_name,
                started_at=started_at,
                completed_at=completed_at,
                success=False,
                error_message=error_msg,
            )

    def _run_dbt_seed(self) -> None:
        """Run dbt seed to load configuration data."""
        result = self.dbt_runner.execute_command(
            ["seed", "--full-refresh", "--threads", "1"],
            stream_output=self.verbose,
        )
        if not result.success:
            raise InitializationError(
                f"dbt seed failed: {result.stderr or result.stdout}",
                step="load_seeds",
            )

    def _run_dbt_foundation(self) -> None:
        """Run dbt to build foundation models."""
        result = self.dbt_runner.execute_command(
            ["run", "--select", "tag:FOUNDATION", "--threads", "1"],
            stream_output=self.verbose,
        )
        if not result.success:
            raise InitializationError(
                f"dbt run failed: {result.stderr or result.stdout}",
                step="build_foundation",
            )

    def _verify_initialization(self) -> None:
        """Verify all required tables now exist."""
        if not self._checker.is_initialized():
            missing = self._checker.get_missing_tables()
            raise InitializationError(
                f"Verification failed: {len(missing)} tables still missing",
                step="verify",
                missing_tables=[t.name for t in missing],
            )

    def _check_timeout(self) -> None:
        """Check if initialization has exceeded timeout."""
        if self._start_time is None:
            return

        elapsed = time.time() - self._start_time
        if elapsed > self.timeout_seconds:
            raise InitializationTimeoutError(
                timeout_seconds=self.timeout_seconds,
                elapsed_seconds=elapsed,
            )

    def _create_failed_result(
        self,
        started_at: datetime,
        steps: List[InitializationStep],
        missing_names: List[str],
        tables_created: List[str],
        error: str,
    ) -> InitializationResult:
        """Create a failed InitializationResult."""
        return InitializationResult(
            state=InitializationState.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            steps=steps,
            missing_tables_found=missing_names,
            tables_created=tables_created,
            error=error,
        )
