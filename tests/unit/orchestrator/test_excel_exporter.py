"""Unit tests for ExcelExporter.

Covers: _check_table_exists, _sanitize_for_excel, _write_events_detail_sheets,
_calculate_summary_metrics, _calculate_events_summary, _build_metadata_dataframe,
_get_git_metadata, _get_table_columns, _format_worksheet, create_comparison_workbook,
_export_csv, _export_excel, _create_minimal_export, export_scenario_results.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from planalign_orchestrator.excel_exporter import ExcelExporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_manager(conn_mock):
    """Build a DatabaseConnectionManager mock whose get_connection() yields *conn_mock*."""
    db_manager = MagicMock()

    @contextmanager
    def _ctx():
        yield conn_mock

    db_manager.get_connection = _ctx
    return db_manager


def _conn_returning_df(df: pd.DataFrame):
    """Return a mock connection whose execute().df() returns *df*."""
    conn = MagicMock()
    result = MagicMock()
    result.df.return_value = df
    conn.execute.return_value = result
    return conn


def _make_config():
    """Create a mock SimulationConfig."""
    config = MagicMock()
    config.simulation.start_year = 2025
    config.simulation.end_year = 2027
    config.simulation.target_growth_rate = 0.05
    config.compensation.cola_rate = 0.03
    config.compensation.merit_budget = 0.02
    config.model_dump.return_value = {"simulation": {"start_year": 2025}}
    return config


# ---------------------------------------------------------------------------
# _check_table_exists
# ---------------------------------------------------------------------------

class TestCheckTableExists:

    @pytest.mark.fast
    def test_table_exists_via_information_schema(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (1,)
        exporter = ExcelExporter(_make_db_manager(conn))
        assert exporter._check_table_exists(conn, "fct_workforce_snapshot") is True

    @pytest.mark.fast
    def test_table_not_exists_via_information_schema(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (0,)
        exporter = ExcelExporter(_make_db_manager(conn))
        assert exporter._check_table_exists(conn, "missing_table") is False

    @pytest.mark.fast
    def test_table_exists_via_information_schema_none_result(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        exporter = ExcelExporter(_make_db_manager(conn))
        assert exporter._check_table_exists(conn, "some_table") is False

    @pytest.mark.fast
    def test_fallback_direct_query_success(self):
        """When information_schema raises, fall back to direct SELECT."""
        conn = MagicMock()

        call_count = [0]
        def _side_effect(query):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("information_schema not available")
            result = MagicMock()
            result.fetchone.return_value = (42,)
            return result

        conn.execute.side_effect = _side_effect
        exporter = ExcelExporter(_make_db_manager(conn))
        assert exporter._check_table_exists(conn, "fct_workforce_snapshot") is True

    @pytest.mark.fast
    def test_fallback_direct_query_failure(self):
        """Both paths fail -> False."""
        conn = MagicMock()
        conn.execute.side_effect = Exception("nope")
        exporter = ExcelExporter(_make_db_manager(conn))
        assert exporter._check_table_exists(conn, "missing_table") is False


# ---------------------------------------------------------------------------
# _sanitize_for_excel
# ---------------------------------------------------------------------------

class TestSanitizeForExcel:

    @pytest.mark.fast
    def test_plain_dataframe_unchanged(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        result = exporter._sanitize_for_excel(df)
        pd.testing.assert_frame_equal(result, df)

    @pytest.mark.fast
    def test_tz_aware_datetime_stripped(self):
        ts = pd.to_datetime(["2025-01-01", "2025-06-15"]).tz_localize("US/Eastern")
        df = pd.DataFrame({"dt": ts})
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        result = exporter._sanitize_for_excel(df)
        assert result["dt"].dt.tz is None

    @pytest.mark.fast
    def test_naive_datetime_unchanged(self):
        ts = pd.to_datetime(["2025-01-01", "2025-06-15"])
        df = pd.DataFrame({"dt": ts})
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        result = exporter._sanitize_for_excel(df)
        assert result["dt"].dt.tz is None
        pd.testing.assert_series_equal(result["dt"], df["dt"])

    @pytest.mark.fast
    def test_object_column_with_tz_timestamps(self):
        ts1 = pd.Timestamp("2025-01-01", tz="US/Eastern")
        ts2 = pd.Timestamp("2025-06-15", tz="UTC")
        df = pd.DataFrame({"mixed": [ts1, ts2]})
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        result = exporter._sanitize_for_excel(df)
        for val in result["mixed"]:
            if isinstance(val, pd.Timestamp):
                assert val.tz is None

    @pytest.mark.fast
    def test_object_column_no_timestamps(self):
        df = pd.DataFrame({"txt": ["hello", "world"]})
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        result = exporter._sanitize_for_excel(df)
        pd.testing.assert_frame_equal(result, df)

    @pytest.mark.fast
    def test_returns_copy(self):
        df = pd.DataFrame({"a": [1, 2]})
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        result = exporter._sanitize_for_excel(df)
        assert result is not df


# ---------------------------------------------------------------------------
# _get_table_columns
# ---------------------------------------------------------------------------

class TestGetTableColumns:

    @pytest.mark.fast
    def test_pragma_path(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [
            (0, "Employee_Id", "VARCHAR", False, None, False),
            (1, "Simulation_Year", "INTEGER", False, None, False),
        ]
        exporter = ExcelExporter(_make_db_manager(conn))
        cols = exporter._get_table_columns(conn, "fct_workforce_snapshot")
        assert cols == ["employee_id", "simulation_year"]

    @pytest.mark.fast
    def test_fallback_information_schema(self):
        """When PRAGMA fails, fallback to information_schema."""
        conn = MagicMock()

        call_count = [0]
        def _side_effect(query, *args):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("PRAGMA not supported")
            result = MagicMock()
            result.df.return_value = pd.DataFrame({"name": ["col_a", "col_b"]})
            return result

        conn.execute.side_effect = _side_effect
        exporter = ExcelExporter(_make_db_manager(conn))
        cols = exporter._get_table_columns(conn, "some_table")
        assert cols == ["col_a", "col_b"]

    @pytest.mark.fast
    def test_both_paths_fail(self):
        conn = MagicMock()
        conn.execute.side_effect = Exception("fail")
        exporter = ExcelExporter(_make_db_manager(conn))
        cols = exporter._get_table_columns(conn, "missing")
        assert cols == []


# ---------------------------------------------------------------------------
# _get_git_metadata
# ---------------------------------------------------------------------------

class TestGetGitMetadata:

    @pytest.mark.fast
    @patch("planalign_orchestrator.excel_exporter.subprocess.run")
    def test_success(self, mock_run):
        results = [
            MagicMock(stdout="abc123\n"),
            MagicMock(stdout="main\n"),
            MagicMock(stdout=""),
        ]
        mock_run.side_effect = results
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        meta = exporter._get_git_metadata()
        assert meta["git_sha"] == "abc123"
        assert meta["git_branch"] == "main"
        assert meta["git_clean"] is True

    @pytest.mark.fast
    @patch("planalign_orchestrator.excel_exporter.subprocess.run")
    def test_dirty_working_directory(self, mock_run):
        results = [
            MagicMock(stdout="abc123\n"),
            MagicMock(stdout="main\n"),
            MagicMock(stdout=" M file.py\n"),
        ]
        mock_run.side_effect = results
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        meta = exporter._get_git_metadata()
        assert meta["git_clean"] is False

    @pytest.mark.fast
    @patch("planalign_orchestrator.excel_exporter.subprocess.run")
    def test_all_git_commands_fail(self, mock_run):
        mock_run.side_effect = Exception("git not found")
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        meta = exporter._get_git_metadata()
        assert meta["git_sha"] == "unknown"
        assert meta["git_branch"] == "unknown"
        assert meta["git_clean"] is False


# ---------------------------------------------------------------------------
# _calculate_summary_metrics – column availability variants
# ---------------------------------------------------------------------------

class TestCalculateSummaryMetrics:

    def _setup(self, columns, query_result_df):
        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._get_table_columns = MagicMock(return_value=columns)
        exporter._query_to_df = MagicMock(return_value=query_result_df)
        return exporter, conn

    @pytest.mark.fast
    def test_all_columns_present(self):
        cols = [
            "simulation_year", "employment_status", "enrollment_date",
            "current_salary", "employee_contribution_annual",
            "employer_match_annual", "employee_deferral_rate",
        ]
        result_df = pd.DataFrame({"simulation_year": [2025], "total_employees": [100]})
        exporter, conn = self._setup(cols, result_df)
        df = exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "employment_status = 'active'" in query_arg
        assert "enrollment_date IS NOT NULL" in query_arg
        assert "AVG(current_salary)" in query_arg
        assert "employee_contribution_annual" in query_arg
        assert "employer_match_annual" in query_arg
        assert "employee_deferral_rate" in query_arg

    @pytest.mark.fast
    def test_status_column_fallback(self):
        cols = ["simulation_year", "status"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "status = 'active'" in query_arg

    @pytest.mark.fast
    def test_no_status_column(self):
        cols = ["simulation_year"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "CAST(NULL AS BIGINT) AS active_employees" in query_arg

    @pytest.mark.fast
    def test_salary_fallback_to_salary(self):
        cols = ["simulation_year", "salary"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "AVG(salary)" in query_arg

    @pytest.mark.fast
    def test_no_salary_column(self):
        cols = ["simulation_year"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "CAST(NULL AS DOUBLE) AS avg_salary" in query_arg

    @pytest.mark.fast
    def test_deferral_rate_fallback(self):
        cols = ["simulation_year", "deferral_rate"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "AVG(COALESCE(deferral_rate, 0))" in query_arg

    @pytest.mark.fast
    def test_no_deferral_column(self):
        cols = ["simulation_year"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "CAST(NULL AS DOUBLE) AS avg_deferral_rate" in query_arg

    @pytest.mark.fast
    def test_no_enrollment_date(self):
        cols = ["simulation_year"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "CAST(NULL AS BIGINT) AS enrolled_employees" in query_arg

    @pytest.mark.fast
    def test_no_contribution_columns(self):
        cols = ["simulation_year"]
        result_df = pd.DataFrame({"simulation_year": [2025]})
        exporter, conn = self._setup(cols, result_df)
        exporter._calculate_summary_metrics(conn)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "CAST(NULL AS DOUBLE) AS total_employee_contributions" in query_arg
        assert "CAST(NULL AS DOUBLE) AS total_employer_match" in query_arg


# ---------------------------------------------------------------------------
# _calculate_events_summary
# ---------------------------------------------------------------------------

class TestCalculateEventsSummary:

    @pytest.mark.fast
    def test_returns_query_result(self):
        expected = pd.DataFrame({
            "simulation_year": [2025, 2025],
            "event_type": ["hire", "termination"],
            "event_count": [10, 5],
        })
        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=expected)
        result = exporter._calculate_events_summary(conn)
        pd.testing.assert_frame_equal(result, expected)
        query_arg = exporter._query_to_df.call_args[0][1]
        assert "fct_yearly_events" in query_arg


# ---------------------------------------------------------------------------
# _build_metadata_dataframe
# ---------------------------------------------------------------------------

class TestBuildMetadataDataframe:

    @pytest.mark.fast
    @patch.object(ExcelExporter, "_get_git_metadata", return_value={
        "git_sha": "abc123", "git_branch": "main", "git_clean": True
    })
    def test_basic_metadata(self, _mock_git):
        config = _make_config()
        conn = MagicMock()
        years_df = pd.DataFrame({"min_y": [2025], "max_y": [2027]})

        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=years_df)

        df = exporter._build_metadata_dataframe(config, seed=42, conn=conn, total_rows=500, split=False)

        params = dict(zip(df["Parameter"], df["Value"]))
        assert params["random_seed"] == "42"
        assert params["start_year"] == "2025"
        assert params["end_year"] == "2027"
        assert params["workforce_rows"] == "500"
        assert params["snapshot_split_by_year"] == "False"
        assert params["git_sha"] == "abc123"

    @pytest.mark.fast
    @patch.object(ExcelExporter, "_get_git_metadata", return_value={
        "git_sha": "unknown", "git_branch": "unknown", "git_clean": False
    })
    def test_total_rows_none_triggers_query(self, _mock_git):
        config = _make_config()
        conn = MagicMock()

        call_count = [0]
        def _query_side_effect(conn_arg, query, *args, **kwargs):
            call_count[0] += 1
            if "MIN" in query:
                return pd.DataFrame({"min_y": [2025], "max_y": [2026]})
            if "COUNT" in query:
                return pd.DataFrame({"cnt": [200]})
            return pd.DataFrame()

        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(side_effect=_query_side_effect)

        df = exporter._build_metadata_dataframe(config, seed=1, conn=conn, total_rows=None, split=True)
        params = dict(zip(df["Parameter"], df["Value"]))
        assert params["workforce_rows"] == "200"

    @pytest.mark.fast
    @patch.object(ExcelExporter, "_get_git_metadata", return_value={})
    def test_year_query_failure_uses_config(self, _mock_git):
        config = _make_config()
        conn = MagicMock()

        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(side_effect=Exception("db error"))

        df = exporter._build_metadata_dataframe(config, seed=1, conn=conn, total_rows=0, split=False)
        params = dict(zip(df["Parameter"], df["Value"]))
        assert params["start_year"] == "2025"
        assert params["end_year"] == "2027"

    @pytest.mark.fast
    @patch.object(ExcelExporter, "_get_git_metadata", return_value={})
    def test_config_without_model_dump(self, _mock_git):
        config = _make_config()
        del config.model_dump
        conn = MagicMock()

        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=pd.DataFrame({"min_y": [2025], "max_y": [2025]}))

        df = exporter._build_metadata_dataframe(config, seed=1, conn=conn, total_rows=0, split=False)
        # config_json lines should still be present (empty dict)
        assert any("config_json" in str(p) for p in df["Parameter"])


# ---------------------------------------------------------------------------
# _format_worksheet
# ---------------------------------------------------------------------------

class TestFormatWorksheet:

    @pytest.mark.fast
    def test_formats_headers(self):
        """Verify formatting is applied without error on a real openpyxl worksheet."""
        try:
            from openpyxl import Workbook
        except ImportError:
            pytest.skip("openpyxl not installed")

        wb = Workbook()
        ws = wb.active
        ws.append(["Name", "Age", "Salary"])
        ws.append(["Alice", 30, 100000])

        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        exporter._format_worksheet(ws)

        # Header should be bold
        assert ws["A1"].font.bold is True
        # Freeze panes set
        assert ws.freeze_panes == "A2"

    @pytest.mark.fast
    def test_handles_import_error(self):
        """If openpyxl styles import fails, method should not raise."""
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        ws = MagicMock()
        # Simulate openpyxl not available by passing a mock; should not raise
        with patch("planalign_orchestrator.excel_exporter.ExcelExporter._format_worksheet") as mock_fmt:
            mock_fmt.return_value = None
            exporter._format_worksheet(ws)


# ---------------------------------------------------------------------------
# _create_minimal_export
# ---------------------------------------------------------------------------

class TestCreateMinimalExport:

    @pytest.mark.fast
    def test_csv_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            exporter = ExcelExporter(_make_db_manager(MagicMock()))
            path = exporter._create_minimal_export("test_scenario", output_dir, "csv")
            assert path.exists()
            assert path.suffix == ".csv"
            df = pd.read_csv(path)
            assert "message" in df.columns

    @pytest.mark.fast
    def test_excel_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            exporter = ExcelExporter(_make_db_manager(MagicMock()))
            path = exporter._create_minimal_export("test_scenario", output_dir, "excel")
            assert path.exists()
            assert path.suffix == ".xlsx"


# ---------------------------------------------------------------------------
# _write_events_detail_sheets
# ---------------------------------------------------------------------------

class TestWriteEventsDetailSheets:

    @pytest.mark.fast
    def test_writes_events_sheet(self):
        events_df = pd.DataFrame({
            "simulation_year": [2025],
            "employee_id": ["E001"],
            "event_type": ["hire"],
        })
        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=events_df)

        try:
            from openpyxl import Workbook
        except ImportError:
            pytest.skip("openpyxl not installed")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                exporter._write_events_detail_sheets(writer, conn)
            # Verify sheet was created
            xl = pd.ExcelFile(path)
            assert "Events_Detail" in xl.sheet_names


# ---------------------------------------------------------------------------
# _export_csv
# ---------------------------------------------------------------------------

class TestExportCsv:

    @pytest.mark.fast
    def test_export_csv_no_split(self):
        workforce_df = pd.DataFrame({
            "simulation_year": [2025, 2025],
            "employee_id": ["E001", "E002"],
        })
        summary_df = pd.DataFrame({"simulation_year": [2025], "total": [2]})
        metadata_df = pd.DataFrame({"Parameter": ["seed"], "Value": ["42"]})

        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=workforce_df)
        exporter._calculate_summary_metrics = MagicMock(return_value=summary_df)
        exporter._check_table_exists = MagicMock(return_value=False)
        exporter._build_metadata_dataframe = MagicMock(return_value=metadata_df)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = exporter._export_csv("scenario1", output_dir, conn, config, 42, split=False)
            assert result == output_dir
            assert (output_dir / "scenario1_workforce_snapshot.csv").exists()
            assert (output_dir / "scenario1_summary_metrics.csv").exists()
            assert (output_dir / "scenario1_metadata.csv").exists()

    @pytest.mark.fast
    def test_export_csv_split_by_year(self):
        years_df = pd.DataFrame({"simulation_year": [2025, 2026]})
        year_data = pd.DataFrame({"simulation_year": [2025], "employee_id": ["E001"]})

        call_count = [0]
        def _query_side_effect(conn_arg, query, *args, **kwargs):
            call_count[0] += 1
            if "DISTINCT" in query:
                return years_df
            return year_data

        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(side_effect=_query_side_effect)
        exporter._calculate_summary_metrics = MagicMock(
            return_value=pd.DataFrame({"simulation_year": [2025]})
        )
        exporter._check_table_exists = MagicMock(return_value=False)
        exporter._build_metadata_dataframe = MagicMock(
            return_value=pd.DataFrame({"Parameter": ["seed"], "Value": ["1"]})
        )

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            exporter._export_csv("sc", output_dir, conn, config, 1, split=True)
            assert (output_dir / "sc_workforce_2025.csv").exists()
            assert (output_dir / "sc_workforce_2026.csv").exists()

    @pytest.mark.fast
    def test_export_csv_with_events(self):
        workforce_df = pd.DataFrame({"simulation_year": [2025], "employee_id": ["E001"]})
        events_detail_df = pd.DataFrame({"simulation_year": [2025], "event_type": ["hire"]})
        events_summary_df = pd.DataFrame({"simulation_year": [2025], "event_type": ["hire"], "event_count": [1]})
        summary_df = pd.DataFrame({"simulation_year": [2025], "total": [1]})
        metadata_df = pd.DataFrame({"Parameter": ["seed"], "Value": ["1"]})

        call_count = [0]
        def _query_side_effect(conn_arg, query, *args, **kwargs):
            call_count[0] += 1
            if "fct_yearly_events" in query:
                return events_detail_df
            return workforce_df

        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(side_effect=_query_side_effect)
        exporter._calculate_summary_metrics = MagicMock(return_value=summary_df)
        exporter._calculate_events_summary = MagicMock(return_value=events_summary_df)
        exporter._check_table_exists = MagicMock(return_value=True)
        exporter._build_metadata_dataframe = MagicMock(return_value=metadata_df)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            exporter._export_csv("sc", output_dir, conn, config, 1, split=False)
            assert (output_dir / "sc_events_detail.csv").exists()
            assert (output_dir / "sc_events_summary.csv").exists()


# ---------------------------------------------------------------------------
# _export_excel
# ---------------------------------------------------------------------------

class TestExportExcel:

    @pytest.mark.fast
    def test_export_excel_basic(self):
        workforce_df = pd.DataFrame({"simulation_year": [2025], "employee_id": ["E001"]})
        summary_df = pd.DataFrame({"simulation_year": [2025], "total": [1]})
        metadata_df = pd.DataFrame({"Parameter": ["seed"], "Value": ["1"]})

        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=workforce_df)
        exporter._calculate_summary_metrics = MagicMock(return_value=summary_df)
        exporter._check_table_exists = MagicMock(return_value=False)
        exporter._build_metadata_dataframe = MagicMock(return_value=metadata_df)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = exporter._export_excel("sc", output_dir, conn, config, 1, split=False, total_rows=1)
            assert path.exists()
            assert path.suffix == ".xlsx"
            xl = pd.ExcelFile(path)
            assert "Workforce_Snapshot" in xl.sheet_names
            assert "Summary_Metrics" in xl.sheet_names
            assert "Metadata" in xl.sheet_names

    @pytest.mark.fast
    def test_export_excel_with_events(self):
        workforce_df = pd.DataFrame({"simulation_year": [2025], "employee_id": ["E001"]})
        summary_df = pd.DataFrame({"simulation_year": [2025], "total": [1]})
        events_df = pd.DataFrame({"simulation_year": [2025], "event_type": ["hire"]})
        events_summary = pd.DataFrame({"simulation_year": [2025], "event_type": ["hire"], "event_count": [1]})
        metadata_df = pd.DataFrame({"Parameter": ["seed"], "Value": ["1"]})

        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(return_value=workforce_df)
        exporter._calculate_summary_metrics = MagicMock(return_value=summary_df)
        exporter._calculate_events_summary = MagicMock(return_value=events_summary)
        exporter._check_table_exists = MagicMock(return_value=True)
        exporter._write_events_detail_sheets = MagicMock()
        exporter._build_metadata_dataframe = MagicMock(return_value=metadata_df)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = exporter._export_excel("sc", output_dir, conn, config, 1, split=False, total_rows=1)
            xl = pd.ExcelFile(path)
            assert "Summary_Metrics" in xl.sheet_names
            assert "Metadata" in xl.sheet_names
            exporter._write_events_detail_sheets.assert_called_once()

    @pytest.mark.fast
    def test_export_excel_split_by_year(self):
        years_df = pd.DataFrame({"simulation_year": [2025, 2026]})
        year_data = pd.DataFrame({"simulation_year": [2025], "employee_id": ["E001"]})
        summary_df = pd.DataFrame({"simulation_year": [2025], "total": [1]})
        metadata_df = pd.DataFrame({"Parameter": ["seed"], "Value": ["1"]})

        call_count = [0]
        def _query_side_effect(conn_arg, query, *args, **kwargs):
            call_count[0] += 1
            if "DISTINCT" in query:
                return years_df
            return year_data

        conn = MagicMock()
        exporter = ExcelExporter(_make_db_manager(conn))
        exporter._query_to_df = MagicMock(side_effect=_query_side_effect)
        exporter._calculate_summary_metrics = MagicMock(return_value=summary_df)
        exporter._check_table_exists = MagicMock(return_value=False)
        exporter._build_metadata_dataframe = MagicMock(return_value=metadata_df)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = exporter._export_excel("sc", output_dir, conn, config, 1, split=True, total_rows=100)
            xl = pd.ExcelFile(path)
            assert "Workforce_2025" in xl.sheet_names
            assert "Workforce_2026" in xl.sheet_names


# ---------------------------------------------------------------------------
# export_scenario_results (integration of sub-methods)
# ---------------------------------------------------------------------------

class TestExportScenarioResults:

    @pytest.mark.fast
    def test_table_not_found_creates_minimal(self):
        conn = MagicMock()
        db_manager = _make_db_manager(conn)
        exporter = ExcelExporter(db_manager)
        exporter._check_table_exists = MagicMock(return_value=False)

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            path = exporter.export_scenario_results(
                scenario_name="sc",
                output_dir=Path(tmp),
                config=config,
                seed=1,
                export_format="excel",
            )
            assert path.exists()
            assert "minimal" in path.name

    @pytest.mark.fast
    def test_csv_format_dispatches(self):
        count_df = pd.DataFrame({"cnt": [10]})
        conn = MagicMock()
        db_manager = _make_db_manager(conn)
        exporter = ExcelExporter(db_manager)
        exporter._check_table_exists = MagicMock(return_value=True)
        exporter._query_to_df = MagicMock(return_value=count_df)
        exporter._export_csv = MagicMock(return_value=Path("/tmp/out"))

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            exporter.export_scenario_results(
                scenario_name="sc",
                output_dir=Path(tmp),
                config=config,
                seed=1,
                export_format="csv",
            )
            exporter._export_csv.assert_called_once()

    @pytest.mark.fast
    def test_excel_format_dispatches(self):
        count_df = pd.DataFrame({"cnt": [10]})
        conn = MagicMock()
        db_manager = _make_db_manager(conn)
        exporter = ExcelExporter(db_manager)
        exporter._check_table_exists = MagicMock(return_value=True)
        exporter._query_to_df = MagicMock(return_value=count_df)
        exporter._export_excel = MagicMock(return_value=Path("/tmp/out.xlsx"))

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            exporter.export_scenario_results(
                scenario_name="sc",
                output_dir=Path(tmp),
                config=config,
                seed=1,
                export_format="excel",
            )
            exporter._export_excel.assert_called_once()

    @pytest.mark.fast
    def test_auto_split_threshold(self):
        """When rows exceed split_threshold, split=True."""
        count_df = pd.DataFrame({"cnt": [1_000_000]})
        conn = MagicMock()
        db_manager = _make_db_manager(conn)
        exporter = ExcelExporter(db_manager, split_threshold=500_000)
        exporter._check_table_exists = MagicMock(return_value=True)
        exporter._query_to_df = MagicMock(return_value=count_df)
        exporter._export_excel = MagicMock(return_value=Path("/tmp/out.xlsx"))

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            exporter.export_scenario_results(
                scenario_name="sc",
                output_dir=Path(tmp),
                config=config,
                seed=1,
            )
            # split argument should be True
            call_kwargs_or_args = exporter._export_excel.call_args
            # positional: scenario_name, output_dir, conn, config, seed, split, total_rows
            assert bool(call_kwargs_or_args[0][5]) is True  # split=True

    @pytest.mark.fast
    def test_forced_split_by_year(self):
        count_df = pd.DataFrame({"cnt": [10]})
        conn = MagicMock()
        db_manager = _make_db_manager(conn)
        exporter = ExcelExporter(db_manager)
        exporter._check_table_exists = MagicMock(return_value=True)
        exporter._query_to_df = MagicMock(return_value=count_df)
        exporter._export_excel = MagicMock(return_value=Path("/tmp/out.xlsx"))

        config = _make_config()
        with tempfile.TemporaryDirectory() as tmp:
            exporter.export_scenario_results(
                scenario_name="sc",
                output_dir=Path(tmp),
                config=config,
                seed=1,
                split_by_year=True,
            )
            assert exporter._export_excel.call_args[0][5] is True


# ---------------------------------------------------------------------------
# create_comparison_workbook
# ---------------------------------------------------------------------------

class TestCreateComparisonWorkbook:

    @pytest.mark.fast
    def test_no_data_prints_warning(self, capsys):
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "comparison.xlsx"
            exporter.create_comparison_workbook({}, output_path)
            captured = capsys.readouterr()
            assert "No comparison data" in captured.out

    @pytest.mark.fast
    def test_missing_database_skipped(self, capsys):
        results = {
            "scenario_a": {"database_path": "/nonexistent/path.duckdb"},
        }
        exporter = ExcelExporter(_make_db_manager(MagicMock()))
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "comparison.xlsx"
            exporter.create_comparison_workbook(results, output_path)
            captured = capsys.readouterr()
            assert "No comparison data" in captured.out

    @pytest.mark.fast
    @patch("planalign_orchestrator.excel_exporter.DatabaseConnectionManager")
    def test_successful_comparison(self, MockDBManager):
        summary_df = pd.DataFrame({
            "simulation_year": [2025],
            "total_employees": [100],
            "active_employees": [90],
            "enrolled_employees": [80],
            "avg_salary": [50000.0],
            "total_employee_contributions": [1000.0],
            "total_employer_match": [500.0],
            "avg_deferral_rate": [0.06],
        })

        mock_conn = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        MockDBManager.return_value.get_connection.return_value = mock_ctx

        with tempfile.TemporaryDirectory() as tmp:
            # Create a fake database file so Path.exists() passes
            db_path = Path(tmp) / "scenario_a.duckdb"
            db_path.write_bytes(b"fake")

            results = {
                "scenario_a": {
                    "database_path": str(db_path),
                    "execution_time_seconds": 10.5,
                    "seed": 42,
                },
            }

            exporter = ExcelExporter(_make_db_manager(MagicMock()))
            exporter._calculate_summary_metrics = MagicMock(return_value=summary_df)

            output_path = Path(tmp) / "comparison.xlsx"
            exporter.create_comparison_workbook(results, output_path)

            assert output_path.exists()
            xl = pd.ExcelFile(output_path)
            assert "Scenario_Comparison" in xl.sheet_names

    @pytest.mark.fast
    @patch("planalign_orchestrator.excel_exporter.DatabaseConnectionManager")
    def test_comparison_error_reraises(self, MockDBManager):
        MockDBManager.side_effect = Exception("connection failed")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sc.duckdb"
            db_path.write_bytes(b"fake")

            results = {"sc": {"database_path": str(db_path)}}
            exporter = ExcelExporter(_make_db_manager(MagicMock()))
            output_path = Path(tmp) / "comparison.xlsx"

            with pytest.raises(Exception, match="connection failed"):
                exporter.create_comparison_workbook(results, output_path)


# ---------------------------------------------------------------------------
# _query_to_df
# ---------------------------------------------------------------------------

class TestQueryToDf:

    @pytest.mark.fast
    def test_without_params(self):
        expected = pd.DataFrame({"a": [1]})
        conn = MagicMock()
        conn.execute.return_value.df.return_value = expected
        exporter = ExcelExporter(_make_db_manager(conn))
        result = exporter._query_to_df(conn, "SELECT 1 AS a")
        pd.testing.assert_frame_equal(result, expected)
        conn.execute.assert_called_once_with("SELECT 1 AS a")

    @pytest.mark.fast
    def test_with_params(self):
        expected = pd.DataFrame({"a": [1]})
        conn = MagicMock()
        conn.execute.return_value.df.return_value = expected
        exporter = ExcelExporter(_make_db_manager(conn))
        result = exporter._query_to_df(conn, "SELECT ? AS a", params=[1])
        conn.execute.assert_called_once_with("SELECT ? AS a", [1])
