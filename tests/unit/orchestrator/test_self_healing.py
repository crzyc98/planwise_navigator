"""
Unit tests for Self-Healing dbt Initialization.

Tests for:
- TableExistenceChecker: Table detection and validation
- AutoInitializer: Automatic database initialization
- InitializationState: State management and transitions
- Error handling and recovery

Per Constitution Principle III: Write tests FIRST, ensure they FAIL before implementation.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import duckdb

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
from planalign_orchestrator.exceptions import (
    InitializationError,
    InitializationTimeoutError,
    ConcurrentInitializationError,
)


# ============================================================================
# T011: Unit test TableExistenceChecker.is_initialized() returns False for empty DB
# ============================================================================

@pytest.mark.fast
@pytest.mark.unit
class TestTableExistenceChecker:
    """Tests for TableExistenceChecker class."""

    def test_is_initialized_returns_false_for_empty_database(self, tmp_path):
        """T011: Empty database should report not initialized."""
        # Setup: Create empty database
        db_path = tmp_path / "empty.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Test
        checker = TableExistenceChecker(db_manager)
        assert checker.is_initialized() is False

    def test_is_initialized_returns_true_when_all_tables_exist(self, tmp_path):
        """Database with all required tables should report initialized."""
        # Setup: Create database with all required tables
        db_path = tmp_path / "full.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")

        # Create all required tables
        for table in REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")

        conn.close()

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Test
        checker = TableExistenceChecker(db_manager)
        assert checker.is_initialized() is True

    # ============================================================================
    # T012: Unit test TableExistenceChecker.get_missing_tables() returns all required
    # ============================================================================

    def test_get_missing_tables_returns_all_for_empty_database(self, tmp_path):
        """T012: Empty database should return all required tables as missing."""
        # Setup: Create empty database
        db_path = tmp_path / "empty.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Test
        checker = TableExistenceChecker(db_manager)
        missing = checker.get_missing_tables()

        assert len(missing) == len(REQUIRED_TABLES)
        assert all(isinstance(t, RequiredTable) for t in missing)

    def test_get_missing_tables_returns_empty_when_all_exist(self, tmp_path):
        """Fully initialized database should return no missing tables."""
        # Setup: Create database with all required tables
        db_path = tmp_path / "full.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")

        for table in REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")

        conn.close()

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Test
        checker = TableExistenceChecker(db_manager)
        missing = checker.get_missing_tables()

        assert len(missing) == 0

    def test_get_missing_by_tier_groups_correctly(self, tmp_path):
        """Missing tables should be grouped by tier."""
        # Setup: Create empty database
        db_path = tmp_path / "empty.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Test
        checker = TableExistenceChecker(db_manager)
        missing_by_tier = checker.get_missing_by_tier()

        # Should have both SEED and FOUNDATION tiers
        assert TableTier.SEED in missing_by_tier
        assert TableTier.FOUNDATION in missing_by_tier

        # All tables in each tier should have matching tier
        for tier, tables in missing_by_tier.items():
            for table in tables:
                assert table.tier == tier


# ============================================================================
# T013: Unit test AutoInitializer.ensure_initialized() triggers dbt commands
# ============================================================================

@pytest.mark.fast
@pytest.mark.unit
class TestAutoInitializer:
    """Tests for AutoInitializer class."""

    def test_ensure_initialized_skips_when_already_initialized(self, tmp_path):
        """T013: When database is initialized, should skip initialization."""
        # This test will fail until AutoInitializer is implemented
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer

        # Setup: Create database with all required tables
        db_path = tmp_path / "full.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        for table in REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")
        conn.close()

        # Create mocks
        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        dbt_runner = MagicMock()

        # Test
        initializer = AutoInitializer(db_manager, dbt_runner)
        result = initializer.ensure_initialized()

        # Should return success without calling dbt
        assert result.success is True
        assert result.state == InitializationState.COMPLETED
        dbt_runner.run_seed.assert_not_called()
        dbt_runner.run_models.assert_not_called()

    def test_ensure_initialized_triggers_dbt_when_tables_missing(self, tmp_path):
        """T013: When tables missing, should trigger dbt seed and dbt run."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer

        # Setup: Create empty database
        db_path = tmp_path / "empty.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Create mock db_manager that returns empty tables initially,
        # then all tables after dbt runs
        call_count = [0]
        def mock_execute(fn):
            call_count[0] += 1
            conn = duckdb.connect(str(db_path))
            # After first call, simulate that tables were created
            if call_count[0] > 1:
                for table in REQUIRED_TABLES:
                    conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")
            result = fn(conn)
            conn.close()
            return result

        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = mock_execute

        # Create mock dbt_runner
        dbt_runner = MagicMock()
        dbt_runner.run_seed.return_value = MagicMock(success=True)
        dbt_runner.run_models.return_value = MagicMock(success=True)

        # Test
        initializer = AutoInitializer(db_manager, dbt_runner)
        result = initializer.ensure_initialized()

        # Should trigger dbt commands
        assert dbt_runner.run_seed.called or dbt_runner.execute_command.called
        assert result.state in [InitializationState.COMPLETED, InitializationState.IN_PROGRESS]

    def test_ensure_initialized_records_step_timing(self, tmp_path):
        """T025: Initialization steps should include timing information."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer

        # Setup: Create database with all required tables (fast path)
        db_path = tmp_path / "full.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        for table in REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")
        conn.close()

        # Create mocks
        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))
        dbt_runner = MagicMock()

        # Test
        initializer = AutoInitializer(db_manager, dbt_runner)
        result = initializer.ensure_initialized()

        # Verify step timing is recorded
        assert result.success is True
        assert len(result.steps) > 0, "Should have at least one step recorded"

        # First step should be check_tables and should have timing
        check_step = result.steps[0]
        assert check_step.name == "check_tables"
        assert check_step.started_at is not None
        assert check_step.completed_at is not None
        assert check_step.duration_seconds is not None
        assert check_step.duration_seconds >= 0


# ============================================================================
# T024: Unit test InitializationStep.status property returns correct values
# ============================================================================

@pytest.mark.fast
@pytest.mark.unit
class TestInitializationStep:
    """Tests for InitializationStep model."""

    def test_status_pending_when_not_started(self):
        """T024: Step with no timestamps should be 'pending'."""
        step = InitializationStep(
            name="test_step",
            display_name="Test Step"
        )
        assert step.status == "pending"

    def test_status_running_when_started_not_completed(self):
        """T024: Step with started_at but no completed_at should be 'running'."""
        step = InitializationStep(
            name="test_step",
            display_name="Test Step",
            started_at=datetime.now()
        )
        assert step.status == "running"

    def test_status_completed_when_success_true(self):
        """T024: Completed step with success=True should be 'completed'."""
        step = InitializationStep(
            name="test_step",
            display_name="Test Step",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=True
        )
        assert step.status == "completed"

    def test_status_failed_when_success_false(self):
        """T024: Completed step with success=False should be 'failed'."""
        step = InitializationStep(
            name="test_step",
            display_name="Test Step",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            success=False,
            error_message="Something went wrong"
        )
        assert step.status == "failed"

    def test_duration_seconds_calculated_correctly(self):
        """Duration should be calculated from timestamps."""
        start = datetime(2025, 1, 1, 12, 0, 0)
        end = datetime(2025, 1, 1, 12, 0, 15)  # 15 seconds later

        step = InitializationStep(
            name="test_step",
            display_name="Test Step",
            started_at=start,
            completed_at=end,
            success=True
        )
        assert step.duration_seconds == 15.0


# ============================================================================
# T030: Unit test InitializationError includes step and missing_tables context
# ============================================================================

@pytest.mark.fast
@pytest.mark.unit
class TestInitializationErrors:
    """Tests for initialization exception classes."""

    def test_initialization_error_includes_step_context(self):
        """T030: InitializationError should include step in metadata."""
        error = InitializationError(
            "Initialization failed",
            step="load_seeds"
        )
        assert "failed_step" in error.additional_data.get("metadata", {})
        assert error.additional_data["metadata"]["failed_step"] == "load_seeds"

    def test_initialization_error_includes_missing_tables(self):
        """T030: InitializationError should include missing_tables in metadata."""
        error = InitializationError(
            "Initialization failed",
            missing_tables=["table1", "table2"]
        )
        assert "missing_tables" in error.additional_data.get("metadata", {})
        assert error.additional_data["metadata"]["missing_tables"] == ["table1", "table2"]

    def test_timeout_error_includes_timing_info(self):
        """InitializationTimeoutError should include timeout and elapsed time."""
        error = InitializationTimeoutError(
            timeout_seconds=60.0,
            elapsed_seconds=75.5
        )
        assert "60" in str(error) or "60.0" in str(error)
        assert "75" in str(error) or "75.5" in str(error)

    def test_concurrent_initialization_error_includes_lock_file(self):
        """ConcurrentInitializationError should include lock file path."""
        error = ConcurrentInitializationError(
            lock_file="/tmp/.planalign_init.lock"
        )
        assert "lock" in str(error).lower()
        assert ".planalign_init.lock" in str(error)

    def test_retry_succeeds_after_previous_failure(self, tmp_path):
        """T032: Retry should succeed after previous failure (clean state)."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer
        from planalign_orchestrator.dbt_runner import DbtResult

        # Setup: Create empty database
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Track call count to simulate failure then success
        call_count = [0]

        def mock_execute_command(command, *args, **kwargs):
            call_count[0] += 1
            # First call fails, subsequent calls succeed
            if call_count[0] == 1:
                return DbtResult(
                    success=False,
                    stdout="",
                    stderr="Simulated failure",
                    execution_time=0.1,
                    return_code=1,
                    command=command,
                )
            else:
                # Create tables on success
                conn = duckdb.connect(str(db_path))
                for table in REQUIRED_TABLES:
                    conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")
                conn.close()
                return DbtResult(
                    success=True,
                    stdout="",
                    stderr="",
                    execution_time=0.1,
                    return_code=0,
                    command=command,
                )

        # Create mocks
        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))
        dbt_runner = MagicMock()
        dbt_runner.execute_command = mock_execute_command

        # First attempt should fail (disable lock for cleaner test)
        initializer = AutoInitializer(db_manager, dbt_runner, use_lock=False)
        result1 = initializer.ensure_initialized()
        assert result1.success is False, "First attempt should fail"

        # Reset state and retry
        call_count[0] = 1  # Skip the failing call
        initializer2 = AutoInitializer(db_manager, dbt_runner, use_lock=False)
        result2 = initializer2.ensure_initialized()
        assert result2.success is True, "Retry should succeed"

    def test_concurrent_initialization_raises_error(self, tmp_path):
        """T031: Concurrent initialization should raise ConcurrentInitializationError."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer, INIT_LOCK_NAME
        from planalign_orchestrator.utils import ExecutionMutex
        from pathlib import Path

        # Setup: Create empty database
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Create mocks
        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))
        dbt_runner = MagicMock()

        # Pre-acquire the lock to simulate another process
        lock = ExecutionMutex(INIT_LOCK_NAME)
        lock.acquire(timeout=5)

        try:
            # Attempt initialization - should fail due to locked
            initializer = AutoInitializer(db_manager, dbt_runner, use_lock=True)

            with pytest.raises(ConcurrentInitializationError) as exc_info:
                initializer.ensure_initialized()

            assert "lock" in str(exc_info.value).lower()
        finally:
            lock.release()


# ============================================================================
# Standard Steps Tests
# ============================================================================

@pytest.mark.fast
@pytest.mark.unit
class TestStandardSteps:
    """Tests for create_standard_steps function."""

    def test_create_standard_steps_returns_four_steps(self):
        """Should return exactly 4 standard initialization steps."""
        steps = create_standard_steps()
        assert len(steps) == 4

    def test_standard_steps_are_in_correct_order(self):
        """Steps should be in expected execution order."""
        steps = create_standard_steps()
        expected_names = ["check_tables", "load_seeds", "build_foundation", "verify"]
        actual_names = [s.name for s in steps]
        assert actual_names == expected_names

    def test_all_standard_steps_start_pending(self):
        """All standard steps should start in 'pending' status."""
        steps = create_standard_steps()
        for step in steps:
            assert step.status == "pending"
            assert step.started_at is None
            assert step.completed_at is None


# ============================================================================
# InitializationResult Tests
# ============================================================================

@pytest.mark.fast
@pytest.mark.unit
class TestInitializationResult:
    """Tests for InitializationResult model."""

    def test_success_true_when_completed(self):
        """Result with COMPLETED state should report success=True."""
        result = InitializationResult(
            state=InitializationState.COMPLETED,
            started_at=datetime.now()
        )
        assert result.success is True

    def test_success_false_when_failed(self):
        """Result with FAILED state should report success=False."""
        result = InitializationResult(
            state=InitializationState.FAILED,
            started_at=datetime.now(),
            error="Something went wrong"
        )
        assert result.success is False

    def test_duration_none_when_not_completed(self):
        """Duration should be None when not completed."""
        result = InitializationResult(
            state=InitializationState.IN_PROGRESS,
            started_at=datetime.now()
        )
        assert result.duration_seconds is None

    def test_duration_calculated_when_completed(self):
        """Duration should be calculated when completed."""
        start = datetime(2025, 1, 1, 12, 0, 0)
        end = datetime(2025, 1, 1, 12, 0, 30)

        result = InitializationResult(
            state=InitializationState.COMPLETED,
            started_at=start,
            completed_at=end
        )
        assert result.duration_seconds == 30.0
