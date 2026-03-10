"""Tests for result_handlers module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
        assert mock.compensation.cola_rate == 0.02
        assert mock.compensation.merit_budget == 0.035

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

    def test_partial_simulation_config(self):
        """Should use defaults for missing simulation keys."""
        config = {"simulation": {"start_year": 2030}}
        mock = _create_mock_config(config)

        assert mock.simulation.start_year == 2030
        assert mock.simulation.end_year == 2027  # default
        assert mock.simulation.target_growth_rate == 0.05  # default

    def test_partial_compensation_config(self):
        """Should use defaults for missing compensation keys."""
        config = {"compensation": {"cola_rate": 0.03}}
        mock = _create_mock_config(config)

        assert mock.compensation.cola_rate == 0.03
        assert mock.compensation.merit_budget == 0.035  # default

    def test_empty_nested_dicts(self):
        """Should handle empty nested dicts gracefully."""
        config = {"simulation": {}, "compensation": {}}
        mock = _create_mock_config(config)

        assert mock.simulation.start_year == 2025
        assert mock.compensation.cola_rate == 0.02


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

    def test_returns_none_when_run_dir_db_missing_and_scenario_db_missing(self, tmp_path):
        """Should return None when neither run_dir nor scenario_path has a database."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        result = export_results_to_excel(
            scenario_path=scenario_path,
            scenario_name="test",
            config={},
            seed=42,
            run_dir=run_dir,
        )

        assert result is None

    def test_returns_none_on_import_error(self, tmp_path):
        """Should return None and log error when import fails."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        # The function does a lazy import inside its try block.
        # Force that import to fail by poisoning sys.modules.
        with patch.dict(
            "sys.modules",
            {"planalign_orchestrator.utils": None},
        ):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
            )

        assert result is None

    def test_returns_none_on_generic_exception(self, tmp_path):
        """Should return None when exporter raises a generic exception."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_scenario_results.side_effect = RuntimeError("export boom")

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.from_dict.side_effect = ValueError("bad config")

        with patch.dict("sys.modules", {
            "planalign_orchestrator.utils": MagicMock(DatabaseConnectionManager=mock_dcm),
            "planalign_orchestrator.excel_exporter": MagicMock(ExcelExporter=mock_ee),
            "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
        }):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
            )

        assert result is None

    def test_success_path_with_mock_exporter(self, tmp_path):
        """Should return excel path on successful export."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        expected_excel = scenario_path / "results" / "test_results.xlsx"

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_scenario_results.return_value = expected_excel
        mock_sim_config = MagicMock()

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.from_dict.return_value = mock_sim_config

        with patch.dict("sys.modules", {
            "planalign_orchestrator.utils": MagicMock(DatabaseConnectionManager=mock_dcm),
            "planalign_orchestrator.excel_exporter": MagicMock(ExcelExporter=mock_ee),
            "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
        }):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={"simulation": {"start_year": 2025}},
                seed=42,
            )

        assert result == expected_excel
        mock_exporter.export_scenario_results.assert_called_once_with(
            scenario_name="test",
            output_dir=scenario_path / "results",
            config=mock_sim_config,
            seed=42,
            export_format="excel",
        )

    def test_success_with_run_dir_database(self, tmp_path):
        """Should prefer run_dir database over scenario_path database."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "simulation.duckdb").touch()

        expected_excel = run_dir / "results.xlsx"

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_scenario_results.return_value = expected_excel

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.from_dict.return_value = MagicMock()

        with patch.dict("sys.modules", {
            "planalign_orchestrator.utils": MagicMock(DatabaseConnectionManager=mock_dcm),
            "planalign_orchestrator.excel_exporter": MagicMock(ExcelExporter=mock_ee),
            "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
        }):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
                run_dir=run_dir,
            )

        # DatabaseConnectionManager should have been called with run_dir db
        mock_dcm.assert_called_once_with(run_dir / "simulation.duckdb")
        assert result == expected_excel

    def test_falls_back_to_mock_config_on_from_dict_failure(self, tmp_path):
        """Should use _create_mock_config when SimulationConfig.from_dict fails."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        expected_excel = scenario_path / "results" / "output.xlsx"

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_scenario_results.return_value = expected_excel

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.from_dict.side_effect = ValueError("invalid config")

        with patch.dict("sys.modules", {
            "planalign_orchestrator.utils": MagicMock(DatabaseConnectionManager=mock_dcm),
            "planalign_orchestrator.excel_exporter": MagicMock(ExcelExporter=mock_ee),
            "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
        }):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={"simulation": {"start_year": 2030}},
                seed=99,
            )

        assert result == expected_excel
        # The config passed to exporter should be a mock config object
        call_args = mock_exporter.export_scenario_results.call_args
        config_arg = call_args.kwargs.get("config") or call_args[1].get("config")
        assert config_arg.simulation.start_year == 2030

    def test_creates_results_dir_when_no_run_dir(self, tmp_path):
        """Should create results/ subdirectory when run_dir is not provided."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_scenario_results.return_value = Path("/fake/output.xlsx")

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.from_dict.return_value = MagicMock()

        with patch.dict("sys.modules", {
            "planalign_orchestrator.utils": MagicMock(DatabaseConnectionManager=mock_dcm),
            "planalign_orchestrator.excel_exporter": MagicMock(ExcelExporter=mock_ee),
            "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
        }):
            export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
            )

        assert (scenario_path / "results").is_dir()


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
