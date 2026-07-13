"""Tests for SimulationService class."""

import asyncio
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from planalign_api.services.simulation.service import (
    SimulationService,
    _active_process_registry,
)
from planalign_api.services.simulation import (
    SimulationService as PackageSimulationService,
)


@pytest.mark.fast
class TestSimulationServiceInit:
    """Test SimulationService initialization."""

    def test_init_with_storage(self):
        """Should initialize with storage."""
        mock_storage = MagicMock()
        service = SimulationService(storage=mock_storage)

        assert service.storage is mock_storage
        assert service._cancelled_runs == set()
        assert service._active_runs == {}
        assert service._active_processes == {}

    def test_init_with_db_resolver(self):
        """Should accept optional db_resolver."""
        mock_storage = MagicMock()
        mock_resolver = MagicMock()
        service = SimulationService(storage=mock_storage, db_resolver=mock_resolver)

        assert service.db_resolver is mock_resolver

    def test_init_creates_default_resolver(self):
        """Should create default resolver if not provided."""
        mock_storage = MagicMock()

        with patch(
            "planalign_api.services.simulation.service.create_api_database_path_resolver"
        ) as mock_resolver_factory:
            SimulationService(storage=mock_storage)
            mock_resolver_factory.assert_called_once_with(mock_storage)


@pytest.mark.fast
class TestSimulationServiceCancelSimulation:
    """Test cancel_simulation method."""

    @pytest.fixture(autouse=True)
    def clear_process_registry(self):
        """Isolate module-scoped process ownership between tests."""
        _active_process_registry.processes.clear()
        _active_process_registry.cancelled_runs.clear()
        yield
        _active_process_registry.processes.clear()
        _active_process_registry.cancelled_runs.clear()

    def test_cancel_from_different_service_terminates_registered_process(self):
        """A request-scoped service can cancel another instance's process."""
        mock_storage = MagicMock()
        first_service = SimulationService(storage=mock_storage)
        second_service = SimulationService(storage=mock_storage)
        mock_process = MagicMock()

        async def wait():
            return -15

        mock_process.wait.side_effect = wait
        first_service._process_registry.register("run-123", mock_process)

        result = asyncio.run(second_service.cancel_simulation("run-123"))

        assert result is True
        mock_process.terminate.assert_called_once()
        assert "run-123" not in first_service._active_processes
        assert "run-123" in second_service._cancelled_runs

    def test_cancel_unknown_run_returns_false(self):
        """An unregistered process cannot be safely marked cancelled."""
        mock_storage = MagicMock()
        service = SimulationService(storage=mock_storage)

        result = asyncio.run(service.cancel_simulation("run-123"))

        assert result is False
        assert "run-123" not in service._cancelled_runs

    def test_cancel_kills_process_after_grace_period(self):
        """A process that ignores terminate is killed before cancellation succeeds."""

        class SlowProcess:
            def __init__(self):
                self.actions = []
                self.killed = False

            def terminate(self):
                self.actions.append("terminate")

            def kill(self):
                self.actions.append("kill")
                self.killed = True

            async def wait(self):
                if not self.killed:
                    await asyncio.Event().wait()
                return -9

        service = SimulationService(storage=MagicMock())
        process = SlowProcess()
        service._process_registry.register("run-123", process)

        with patch(
            "planalign_api.services.simulation.service.CANCEL_GRACE_SECONDS", 0.01
        ):
            result = asyncio.run(service.cancel_simulation("run-123"))

        assert result is True
        assert process.actions == ["terminate", "kill"]
        assert "run-123" not in service._active_processes


@pytest.mark.fast
class TestSimulationServiceGetTelemetry:
    """Test get_telemetry method."""

    def test_returns_none_for_unknown_run(self):
        """Should return None for unknown run_id."""
        mock_storage = MagicMock()
        service = SimulationService(storage=mock_storage)

        result = service.get_telemetry("unknown-run")

        assert result is None

    def test_returns_telemetry_for_active_run(self):
        """Should return telemetry for active run."""
        mock_storage = MagicMock()
        service = SimulationService(storage=mock_storage)

        # Create a mock run with required attributes
        mock_run = MagicMock()
        mock_run.progress = 50
        mock_run.current_stage = "EVENT_GENERATION"
        mock_run.current_year = 2026
        mock_run.total_years = 3
        service._active_runs["run-123"] = mock_run

        result = service.get_telemetry("run-123")

        assert result is not None
        assert result.run_id == "run-123"
        assert result.progress == 50
        assert result.current_stage == "EVENT_GENERATION"
        assert result.current_year == 2026


@pytest.mark.fast
class TestSimulationServiceBackwardCompatibility:
    """Test backward compatibility imports."""

    def test_import_from_old_path(self):
        """Should be able to import from simulation_service.py."""
        from planalign_api.services.simulation_service import (
            SimulationService as OldSimulationService,
        )

        assert OldSimulationService is SimulationService

    def test_import_from_new_path(self):
        """Should be able to import from simulation package."""
        assert PackageSimulationService is SimulationService

    def test_both_paths_same_class(self):
        """Both import paths should return the same class."""
        from planalign_api.services.simulation_service import (
            SimulationService as OldSimulationService,
        )
        from planalign_api.services.simulation import (
            SimulationService as NewSimulationService,
        )

        assert OldSimulationService is NewSimulationService


@pytest.mark.fast
class TestScenarioSeedIsolation:
    """Regression coverage for Studio's scenario-local dbt seed project."""

    @staticmethod
    def _age_bands(label: str) -> dict:
        return {
            "age_bands": [
                {
                    "band_id": "custom",
                    "band_label": label,
                    "min_value": 18,
                    "max_value": 65,
                    "display_order": 1,
                }
            ]
        }

    def test_seed_overrides_are_private_to_each_scenario(self, tmp_path):
        """Neither scenario's overrides may mutate or leak through dbt/seeds."""
        repo_seed = Path(__file__).parents[3] / "dbt" / "seeds" / "config_age_bands.csv"
        original_global_seed = repo_seed.read_bytes()
        scenario_a = tmp_path / "scenario-a"
        scenario_b = tmp_path / "scenario-b"

        SimulationService._write_seeds(self._age_bands("Scenario A"), scenario_a)
        SimulationService._write_seeds({}, scenario_b)
        project_a = SimulationService._prepare_dbt_project(scenario_a)
        project_b = SimulationService._prepare_dbt_project(scenario_b)

        assert repo_seed.read_bytes() == original_global_seed
        assert "Scenario A" in (scenario_a / "seeds" / repo_seed.name).read_text()
        assert (
            scenario_b / "seeds" / repo_seed.name
        ).read_bytes() == original_global_seed
        assert (project_a / "seeds").resolve() == (scenario_a / "seeds").resolve()
        assert (project_b / "seeds").resolve() == (scenario_b / "seeds").resolve()

        command = SimulationService._build_command(
            scenario_a / "config.yaml",
            scenario_a / "simulation.duckdb",
            2025,
            2025,
            project_a,
        )
        assert command[command.index("--dbt-project-dir") + 1] == str(project_a)

    def test_subprocess_environment_carries_authoritative_run_id(self, tmp_path):
        run_id = "12345678-1234-5678-9234-567812345678"
        env = SimulationService._build_env(tmp_path, run_id)
        assert env["PLANALIGN_RUN_ID"] == run_id
