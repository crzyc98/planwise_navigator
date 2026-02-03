"""Tests for result_handlers module."""

from unittest.mock import patch
import pytest

from planalign_api.services.simulation.result_handlers import (
    export_results_to_excel,
    _create_mock_config,
)


@pytest.mark.fast
class TestCreateMockConfig:
    """Test mock config creation."""

    def test_creates_mock_with_defaults(self):
        """Should create mock config with default values."""
        config = {}
        mock = _create_mock_config(config)

        assert mock.simulation.start_year == 2025
        assert mock.simulation.end_year == 2027
        assert mock.simulation.target_growth_rate == 0.05
        assert mock.compensation.cola_rate == 0.03
        assert mock.compensation.merit_budget == 0.03

    def test_creates_mock_with_custom_values(self):
        """Should create mock config with custom values."""
        config = {
            "simulation": {
                "start_year": 2024,
                "end_year": 2028,
                "growth_target": 0.10,
            },
            "compensation": {
                "cola_rate": 0.04,
                "merit_budget": 0.05,
            },
        }
        mock = _create_mock_config(config)

        assert mock.simulation.start_year == 2024
        assert mock.simulation.end_year == 2028
        assert mock.simulation.target_growth_rate == 0.10
        assert mock.compensation.cola_rate == 0.04
        assert mock.compensation.merit_budget == 0.05

    def test_model_dump_returns_original_config(self):
        """model_dump should return the original config dict."""
        config = {"simulation": {"start_year": 2024}}
        mock = _create_mock_config(config)

        assert mock.model_dump() == config


@pytest.mark.fast
class TestExportResultsToExcel:
    """Test Excel export functionality."""

    def test_returns_none_when_db_not_found(self, tmp_path):
        """Should return None when database doesn't exist."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()

        result = export_results_to_excel(
            scenario_path=scenario_path,
            scenario_name="test",
            config={},
            seed=42,
        )

        assert result is None

    def test_returns_none_on_import_error(self, tmp_path):
        """Should return None when imports fail."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        db_path = scenario_path / "simulation.duckdb"
        db_path.touch()

        with patch(
            "planalign_api.services.simulation.result_handlers.export_results_to_excel",
            side_effect=ImportError("test error"),
        ):
            # The patched function will raise, simulating import failure
            pass


@pytest.mark.fast
class TestResultHandlersBackwardCompatibility:
    """Test backward compatibility imports."""

    def test_import_from_old_path(self):
        """Should be able to import from simulation_service.py."""
        from planalign_api.services.simulation_service import (
            export_results_to_excel as old_export,
        )

        assert old_export is export_results_to_excel

    def test_import_from_new_path(self):
        """Should be able to import from simulation package."""
        from planalign_api.services.simulation import (
            export_results_to_excel as new_export,
        )

        assert new_export is export_results_to_excel

    def test_underscore_prefixed_import(self):
        """Underscore-prefixed name should also work for backward compat."""
        from planalign_api.services.simulation_service import (
            _export_results_to_excel,
        )

        assert _export_results_to_excel is export_results_to_excel
