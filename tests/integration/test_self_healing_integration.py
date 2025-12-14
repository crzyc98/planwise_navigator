"""
Integration tests for Self-Healing dbt Initialization.

Tests the full initialization flow with mock dbt runner to verify
the complete orchestration process works end-to-end.

Per Constitution Principle III: Write tests FIRST, ensure they FAIL before implementation.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import duckdb

from planalign_orchestrator.self_healing.initialization_state import (
    InitializationState,
    InitializationResult,
    REQUIRED_TABLES,
)


# ============================================================================
# T014: Integration test full initialization flow with mock dbt runner
# ============================================================================

@pytest.mark.integration
class TestSelfHealingIntegration:
    """Integration tests for self-healing initialization."""

    def test_full_initialization_flow_creates_all_tables(self, tmp_path):
        """T014: Full initialization should create all required tables."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer
        from planalign_orchestrator.self_healing.table_checker import TableExistenceChecker
        from planalign_orchestrator.dbt_runner import DbtResult

        # Setup: Create empty database
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        conn.close()

        # Track whether dbt was called
        commands_called = []

        def mock_execute_command(command, *args, **kwargs):
            commands_called.append(command)
            # Simulate dbt commands by creating tables
            conn = duckdb.connect(str(db_path))
            if "seed" in command:
                # Simulate dbt seed
                for table in REQUIRED_TABLES:
                    if table.tier.value == "seed":
                        conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")
            elif "run" in command:
                # Simulate dbt run
                for table in REQUIRED_TABLES:
                    if table.tier.value == "foundation":
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

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Create mock dbt_runner
        dbt_runner = MagicMock()
        dbt_runner.execute_command = mock_execute_command

        # Verify database starts empty
        checker = TableExistenceChecker(db_manager)
        assert not checker.is_initialized(), "Database should start empty"
        missing_before = len(checker.get_missing_tables())
        assert missing_before == len(REQUIRED_TABLES), "All tables should be missing initially"

        # Run initialization
        initializer = AutoInitializer(db_manager, dbt_runner, verbose=True)
        result = initializer.ensure_initialized()

        # Verify initialization completed
        assert result.success, f"Initialization should succeed: {result.error}"
        assert result.state == InitializationState.COMPLETED

        # Verify dbt commands were called
        assert len(commands_called) >= 2, "Should have called dbt seed and dbt run"

        # Verify all tables now exist
        checker = TableExistenceChecker(db_manager)
        assert checker.is_initialized(), "Database should be initialized after"
        missing_after = checker.get_missing_tables()
        assert len(missing_after) == 0, f"No tables should be missing, but found: {[t.name for t in missing_after]}"

    def test_initialization_skipped_when_database_ready(self, tmp_path):
        """Already initialized database should skip initialization."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer
        from planalign_orchestrator.self_healing.table_checker import TableExistenceChecker

        # Setup: Create database with all tables
        db_path = tmp_path / "test.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute("CREATE SCHEMA IF NOT EXISTS main")
        for table in REQUIRED_TABLES:
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table.name} (id INTEGER)")
        conn.close()

        # Create mock db_manager
        db_manager = MagicMock()
        db_manager.db_path = db_path
        db_manager.execute_with_retry = lambda fn: fn(duckdb.connect(str(db_path)))

        # Create mock dbt_runner
        dbt_runner = MagicMock()

        # Verify database is already initialized
        checker = TableExistenceChecker(db_manager)
        assert checker.is_initialized(), "Database should start initialized"

        # Run initialization
        initializer = AutoInitializer(db_manager, dbt_runner)
        result = initializer.ensure_initialized()

        # Verify success without calling dbt
        assert result.success
        assert result.state == InitializationState.COMPLETED
        assert len(result.missing_tables_found) == 0

        # dbt should not have been called
        dbt_runner.run_seed.assert_not_called()
        dbt_runner.run_models.assert_not_called()

    def test_initialization_result_includes_timing_info(self, tmp_path):
        """Initialization result should include timing information."""
        from planalign_orchestrator.self_healing.auto_initializer import AutoInitializer

        # Setup: Create database with all tables (fast path)
        db_path = tmp_path / "test.duckdb"
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

        # Run initialization
        initializer = AutoInitializer(db_manager, dbt_runner)
        result = initializer.ensure_initialized()

        # Verify timing info
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_hook_integration_with_orchestrator(self, tmp_path):
        """AutoInitializer should integrate with HookManager."""
        from planalign_orchestrator.pipeline.hooks import HookManager, Hook, HookType

        # Track hook execution
        hook_executed = [False]

        def test_hook(context):
            hook_executed[0] = True

        # Create hook manager and register pre-simulation hook
        manager = HookManager(verbose=True)

        # Create a pre-simulation hook
        hook = Hook(
            hook_type=HookType.PRE_SIMULATION,
            callback=test_hook,
            name="test_init_hook"
        )
        manager.register_hook(hook)

        # Execute hooks
        manager.execute_hooks(HookType.PRE_SIMULATION, {})

        # Verify hook was called
        assert hook_executed[0], "Pre-simulation hook should have been called"

    def test_create_orchestrator_registers_self_healing_hook(self, tmp_path):
        """T022: create_orchestrator should register self-healing hook when auto_initialize=True."""
        from planalign_orchestrator.factory import create_orchestrator
        from planalign_orchestrator.pipeline.hooks import HookType
        from planalign_orchestrator.config import load_simulation_config

        # Load a real config
        config = load_simulation_config("config/simulation_config.yaml")

        # Create database
        db_path = tmp_path / "test.duckdb"

        # Create orchestrator with auto_initialize=True (default)
        orchestrator = create_orchestrator(
            config,
            db_path=db_path,
            auto_initialize=True,
        )

        # Verify self-healing hook is registered
        hooks = orchestrator.hook_manager.list_hooks()
        assert "pre_simulation" in hooks, "PRE_SIMULATION hooks should be registered"
        assert "self_healing_initializer" in hooks["pre_simulation"], \
            "self_healing_initializer hook should be registered"

    def test_create_orchestrator_skips_hook_when_disabled(self, tmp_path):
        """create_orchestrator should NOT register hook when auto_initialize=False."""
        from planalign_orchestrator.factory import create_orchestrator
        from planalign_orchestrator.config import load_simulation_config

        # Load a real config
        config = load_simulation_config("config/simulation_config.yaml")

        # Create database
        db_path = tmp_path / "test.duckdb"

        # Create orchestrator with auto_initialize=False
        orchestrator = create_orchestrator(
            config,
            db_path=db_path,
            auto_initialize=False,
        )

        # Verify no hooks are registered
        hooks = orchestrator.hook_manager.list_hooks()
        assert "pre_simulation" not in hooks or "self_healing_initializer" not in hooks.get("pre_simulation", []), \
            "self_healing_initializer hook should NOT be registered when auto_initialize=False"
