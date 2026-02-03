"""Tests for SimulationService class."""

from unittest.mock import MagicMock, patch
import pytest

from planalign_api.services.simulation.service import SimulationService
from planalign_api.services.simulation import SimulationService as PackageSimulationService


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
            "planalign_api.services.simulation.service.DatabasePathResolver"
        ) as MockResolver:
            service = SimulationService(storage=mock_storage)
            MockResolver.assert_called_once_with(mock_storage)


@pytest.mark.fast
class TestSimulationServiceCancelSimulation:
    """Test cancel_simulation method."""

    def test_cancel_adds_to_cancelled_set(self):
        """Should add run_id to cancelled set."""
        mock_storage = MagicMock()
        service = SimulationService(storage=mock_storage)

        result = service.cancel_simulation("run-123")

        assert result is True
        assert "run-123" in service._cancelled_runs

    def test_cancel_terminates_active_process(self):
        """Should terminate active process if running."""
        mock_storage = MagicMock()
        mock_process = MagicMock()
        service = SimulationService(storage=mock_storage)
        service._active_processes["run-123"] = mock_process

        result = service.cancel_simulation("run-123")

        assert result is True
        mock_process.terminate.assert_called_once()
        assert "run-123" not in service._active_processes

    def test_cancel_handles_missing_process(self):
        """Should handle gracefully if process already exited."""
        mock_storage = MagicMock()
        mock_process = MagicMock()
        mock_process.terminate.side_effect = ProcessLookupError()
        service = SimulationService(storage=mock_storage)
        service._active_processes["run-123"] = mock_process

        result = service.cancel_simulation("run-123")

        assert result is True
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
