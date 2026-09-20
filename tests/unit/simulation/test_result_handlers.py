"""Tests for result_handlers module."""

from unittest.mock import MagicMock, patch

import pytest

from planalign_api.services.simulation.result_handlers import (
    export_results_to_excel,
    find_results_export,
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

    def test_returns_none_when_run_dir_db_missing_and_scenario_db_missing(
        self, tmp_path
    ):
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

    def test_run_dir_never_falls_back_to_mutable_scenario_database(self, tmp_path):
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()
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
        mock_sc.model_validate.side_effect = ValueError("bad config")

        with patch.dict(
            "sys.modules",
            {
                "planalign_orchestrator.utils": MagicMock(
                    DatabaseConnectionManager=mock_dcm
                ),
                "planalign_orchestrator.excel_exporter": MagicMock(
                    ExcelExporter=mock_ee
                ),
                "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
            },
        ):
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

        def export(**kwargs):
            staged_path = kwargs["output_dir"] / expected_excel.name
            staged_path.write_bytes(b"workbook")
            return staged_path

        mock_exporter.export_scenario_results.side_effect = export
        mock_sim_config = MagicMock()

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.model_validate.return_value = mock_sim_config

        with patch.dict(
            "sys.modules",
            {
                "planalign_orchestrator.utils": MagicMock(
                    DatabaseConnectionManager=mock_dcm
                ),
                "planalign_orchestrator.excel_exporter": MagicMock(
                    ExcelExporter=mock_ee
                ),
                "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
            },
        ):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={"simulation": {"start_year": 2025}},
                seed=42,
            )

        assert result == expected_excel
        mock_exporter.export_scenario_results.assert_called_once()
        export_kwargs = mock_exporter.export_scenario_results.call_args.kwargs
        assert export_kwargs["scenario_name"] == "test"
        assert export_kwargs["config"] is mock_sim_config
        assert export_kwargs["seed"] == 42
        assert export_kwargs["export_format"] == "excel"
        assert export_kwargs["output_dir"].parent == scenario_path / "results"
        assert not export_kwargs["output_dir"].exists()

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

        def export(**kwargs):
            staged_path = kwargs["output_dir"] / expected_excel.name
            staged_path.write_bytes(b"workbook")
            return staged_path

        mock_exporter.export_scenario_results.side_effect = export

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.model_validate.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "planalign_orchestrator.utils": MagicMock(
                    DatabaseConnectionManager=mock_dcm
                ),
                "planalign_orchestrator.excel_exporter": MagicMock(
                    ExcelExporter=mock_ee
                ),
                "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
            },
        ):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
                run_dir=run_dir,
            )

        # DatabaseConnectionManager should have been called with run_dir db
        mock_dcm.assert_called_once_with(run_dir / "simulation.duckdb", read_only=True)
        assert result == expected_excel

    def test_falls_back_to_mock_config_on_validation_failure(self, tmp_path):
        """Should use _create_mock_config when SimulationConfig.model_validate fails."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()

        expected_excel = scenario_path / "results" / "output.xlsx"

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()

        def export(**kwargs):
            staged_path = kwargs["output_dir"] / expected_excel.name
            staged_path.write_bytes(b"workbook")
            return staged_path

        mock_exporter.export_scenario_results.side_effect = export

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.model_validate.side_effect = ValueError("invalid config")

        with patch.dict(
            "sys.modules",
            {
                "planalign_orchestrator.utils": MagicMock(
                    DatabaseConnectionManager=mock_dcm
                ),
                "planalign_orchestrator.excel_exporter": MagicMock(
                    ExcelExporter=mock_ee
                ),
                "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
            },
        ):
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

        def export(**kwargs):
            staged_path = kwargs["output_dir"] / "output.xlsx"
            staged_path.write_bytes(b"workbook")
            return staged_path

        mock_exporter.export_scenario_results.side_effect = export

        mock_dcm = MagicMock(return_value=mock_db_manager)
        mock_ee = MagicMock(return_value=mock_exporter)
        mock_sc = MagicMock()
        mock_sc.model_validate.return_value = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "planalign_orchestrator.utils": MagicMock(
                    DatabaseConnectionManager=mock_dcm
                ),
                "planalign_orchestrator.excel_exporter": MagicMock(
                    ExcelExporter=mock_ee
                ),
                "planalign_orchestrator.config": MagicMock(SimulationConfig=mock_sc),
            },
        ):
            export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
            )

        assert (scenario_path / "results").is_dir()

    def test_failed_export_does_not_replace_existing_workbook(self, tmp_path):
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        (scenario_path / "simulation.duckdb").touch()
        results_dir = scenario_path / "results"
        results_dir.mkdir()
        existing = results_dir / "test_results.xlsx"
        existing.write_bytes(b"previous-workbook")

        mock_db_manager = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_scenario_results.side_effect = RuntimeError("boom")

        with patch.dict(
            "sys.modules",
            {
                "planalign_orchestrator.utils": MagicMock(
                    DatabaseConnectionManager=MagicMock(return_value=mock_db_manager)
                ),
                "planalign_orchestrator.excel_exporter": MagicMock(
                    ExcelExporter=MagicMock(return_value=mock_exporter)
                ),
                "planalign_orchestrator.config": MagicMock(
                    SimulationConfig=MagicMock()
                ),
            },
        ):
            result = export_results_to_excel(
                scenario_path=scenario_path,
                scenario_name="test",
                config={},
                seed=42,
            )

        assert result is None
        assert existing.read_bytes() == b"previous-workbook"
        assert not list(results_dir.glob(".excel-export-*"))


@pytest.mark.fast
class TestFindResultsExport:
    def test_ignores_zero_byte_workbook(self, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "test_results.xlsx").touch()

        assert find_results_export(tmp_path, "test", "xlsx") is None

    def test_returns_completed_workbook(self, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        workbook = results_dir / "test_results.xlsx"
        workbook.write_bytes(b"workbook")

        assert find_results_export(tmp_path, "test", "xlsx") == workbook


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
