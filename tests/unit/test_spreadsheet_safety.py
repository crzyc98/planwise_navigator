"""Tests that exported Excel, CSV, and embedded chart workbooks store text as text.

All census and scenario rows here are synthetic.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pandas as pd
import pytest
from openpyxl import load_workbook

from planalign_api.models.employer_cost import ForfeiturePolicy
from planalign_api.models.report import (
    ReportDefinition,
    ReportPlanDesign,
    ReportProvenance,
    ReportScenario,
    ReportYear,
    ScenarioReport,
)
from planalign_api.services.census_analysis_service import CensusAnalysisService
from planalign_api.services.comparison_export_service import (
    ComparisonExportService,
    ExportScenario,
)
from planalign_api.services.import_quality import flagged_rows_csv
from planalign_api.services.report_pptx import CHART_NAME, render_pptx
from planalign_cli.commands.analyze import _export_cost_excel
from planalign_core.spreadsheet_safety import FORMULA_PREFIXES, neutralize_formula
from planalign_orchestrator.excel_exporter import ExcelExporter
from planalign_orchestrator.utils import DatabaseConnectionManager

pytestmark = pytest.mark.fast

FORMULA_SUM = "=1+1"
FORMULA_LINK = '=HYPERLINK("http://example.invalid","x")'


def _assert_xlsx_has_no_formulas(source: Path | bytes) -> None:
    """Assert neither openpyxl nor raw OOXML worksheet XML contains any formula."""
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    book = load_workbook(stream)
    try:
        for name in book.sheetnames:
            sheet = book[name]
            for row in sheet.iter_rows():
                for cell in row:
                    assert (
                        cell.data_type != "f"
                    ), f"Formula cell found at {name}!{cell.coordinate}: {cell.value!r}"
    finally:
        book.close()

    zip_source = io.BytesIO(source) if isinstance(source, bytes) else source
    with zipfile.ZipFile(zip_source) as archive:
        for member in archive.namelist():
            if member.startswith("xl/worksheets/sheet") and member.endswith(".xml"):
                xml = archive.read(member).decode("utf-8")
                assert (
                    "<f>" not in xml and "<f " not in xml
                ), f"Raw <f> element found in {member}"


def _all_values(source: Path | bytes) -> list[Any]:
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    book = load_workbook(stream)
    try:
        return [
            cell.value
            for name in book.sheetnames
            for row in book[name].iter_rows()
            for cell in row
        ]
    finally:
        book.close()


def _mock_config() -> Any:
    config = MagicMock()
    config.simulation.start_year = 2025
    config.simulation.end_year = 2025
    config.simulation.target_growth_rate = 0.0
    config.compensation.cola_rate = 0.0
    config.compensation.merit_budget = 0.0
    config.model_dump.return_value = {"name": FORMULA_SUM, "note": FORMULA_LINK}
    return config


def _create_sim_db(path: Path) -> Path:
    with duckdb.connect(str(path)) as conn:
        conn.execute("""
            CREATE TABLE fct_workforce_snapshot (
                employee_id VARCHAR,
                simulation_year INTEGER,
                employment_status VARCHAR,
                current_salary DOUBLE,
                employee_contribution_annual DOUBLE,
                employer_match_annual DOUBLE,
                employee_deferral_rate DOUBLE,
                department VARCHAR
            );
            CREATE TABLE fct_yearly_events (
                employee_id VARCHAR,
                simulation_year INTEGER,
                event_type VARCHAR,
                compensation_amount DOUBLE,
                notes VARCHAR
            );
            """)
        conn.execute(
            "INSERT INTO fct_workforce_snapshot VALUES "
            "(?, 2025, 'active', -5.0, 100.0, 50.0, 0.05, ?), "
            "(?, 2025, 'active', 60000.0, 3000.0, 1500.0, 0.05, 'Engineering')",
            [FORMULA_SUM, FORMULA_LINK, FORMULA_LINK],
        )
        conn.execute(
            "INSERT INTO fct_yearly_events VALUES "
            "(?, 2025, 'raise', -5.0, ?), "
            "(?, 2025, ?, 60000.0, 'ok')",
            [FORMULA_SUM, FORMULA_LINK, FORMULA_LINK, FORMULA_SUM],
        )
    return path


class TestSpreadsheetSafetyHelper:
    @pytest.mark.parametrize(
        "raw",
        [
            FORMULA_SUM,
            FORMULA_LINK,
            "+SUM(A1:A2)",
            "-1+1",
            "@SUM(A1)",
            "\t=1+1",
            "\r=1+1",
        ],
    )
    def test_neutralize_formula_prefixes_trigger_characters(self, raw: str) -> None:
        assert FORMULA_PREFIXES == ("=", "+", "-", "@", "\t", "\r")
        assert neutralize_formula(raw) == f"'{raw}"

    @pytest.mark.parametrize("raw", ["", "Baseline", "E0001", "a=b", "100%"])
    def test_neutralize_formula_leaves_ordinary_text_unchanged(self, raw: str) -> None:
        assert neutralize_formula(raw) == raw


class TestImportQualityCsvSafety:
    def test_flagged_rows_csv_neutralizes_formula_ids(self, tmp_path: Path) -> None:
        df = pd.DataFrame(
            {
                "employee_id": [FORMULA_SUM, FORMULA_LINK],
                "employee_birth_date": [pd.Timestamp("1980-01-01")] * 2,
                "employee_hire_date": [pd.Timestamp("2020-01-01")] * 2,
                "employee_gross_compensation": [-5.0, -5.0],
                "employee_deferral_rate": [0.05, 0.05],
                "employee_contribution": [0.0, 0.0],
                "active": [True, True],
            }
        )
        text = flagged_rows_csv(df, CensusAnalysisService(tmp_path))
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[1][1] == f"'{FORMULA_SUM}"
        assert rows[2][1] == f"'{FORMULA_LINK}"


class TestExcelExporterSafety:
    @pytest.mark.parametrize("split_by_year", [False, True])
    def test_results_xlsx_has_no_formulas_and_preserves_negative_numbers(
        self, tmp_path: Path, split_by_year: bool
    ) -> None:
        db_path = _create_sim_db(tmp_path / "sim.duckdb")
        exporter = ExcelExporter(DatabaseConnectionManager(db_path))
        xlsx_path = exporter.export_scenario_results(
            scenario_name="safe_test",
            output_dir=tmp_path / "out",
            config=_mock_config(),
            seed=42,
            export_format="excel",
            split_by_year=split_by_year,
        )
        _assert_xlsx_has_no_formulas(xlsx_path)
        values = _all_values(xlsx_path)
        assert FORMULA_SUM in values
        assert FORMULA_LINK in values
        assert -5 in values

    @pytest.mark.parametrize("split_by_year", [False, True])
    def test_export_csv_neutralizes_text_and_preserves_negative_numbers(
        self, tmp_path: Path, split_by_year: bool
    ) -> None:
        db_path = _create_sim_db(tmp_path / "sim.duckdb")
        exporter = ExcelExporter(DatabaseConnectionManager(db_path))
        out_dir = exporter.export_scenario_results(
            scenario_name="safe_test",
            output_dir=tmp_path / "csv_out",
            config=_mock_config(),
            seed=42,
            export_format="csv",
            split_by_year=split_by_year,
        )
        wf_name = (
            "safe_test_workforce_2025.csv"
            if split_by_year
            else "safe_test_workforce_snapshot.csv"
        )
        with (out_dir / wf_name).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        header = rows[0]
        id_idx = header.index("employee_id")
        dept_idx = header.index("department")
        salary_idx = header.index("current_salary")
        ids = {row[id_idx] for row in rows[1:]}
        depts = {row[dept_idx] for row in rows[1:]}
        salaries = {row[salary_idx] for row in rows[1:]}
        assert f"'{FORMULA_SUM}" in ids
        assert f"'{FORMULA_LINK}" in ids
        assert f"'{FORMULA_LINK}" in depts
        assert any(s in {"-5", "-5.0"} for s in salaries)
        assert not any(s.startswith("'-5") for s in salaries)

        with (out_dir / "safe_test_events_detail.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            event_rows = list(csv.reader(handle))
        event_flat = [cell for row in event_rows[1:] for cell in row]
        assert f"'{FORMULA_SUM}" in event_flat
        assert f"'{FORMULA_LINK}" in event_flat
        assert any(cell in {"-5", "-5.0"} for cell in event_flat)

    def test_comparison_workbook_has_no_formulas_and_preserves_negative_numbers(
        self, tmp_path: Path
    ) -> None:
        db1 = _create_sim_db(tmp_path / "s1.duckdb")
        db2 = _create_sim_db(tmp_path / "s2.duckdb")
        exporter = ExcelExporter(DatabaseConnectionManager(db1))
        out_path = tmp_path / "comparison.xlsx"
        exporter.create_comparison_workbook(
            {
                FORMULA_SUM: {"database_path": str(db1), "seed": 1},
                FORMULA_LINK: {"database_path": str(db2), "seed": 2},
            },
            out_path,
        )
        _assert_xlsx_has_no_formulas(out_path)
        values = _all_values(out_path)
        assert FORMULA_SUM in values
        assert FORMULA_LINK in values

    def test_ensemble_only_export_has_no_formulas_and_preserves_negative_numbers(
        self, tmp_path: Path
    ) -> None:
        ensemble_db = tmp_path / "ensemble.duckdb"
        with duckdb.connect(str(ensemble_db)) as conn:
            conn.execute("""
                CREATE TABLE fct_metric_distributions (
                    metric VARCHAR,
                    simulation_year INTEGER,
                    p10 DOUBLE, p25 DOUBLE, p50 DOUBLE, p75 DOUBLE, p90 DOUBLE,
                    mean DOUBLE, stddev DOUBLE,
                    n_seeds INTEGER, n_seeds_requested INTEGER,
                    is_sufficient BOOLEAN, percentile_method VARCHAR
                )
                """)
            conn.execute(
                "INSERT INTO fct_metric_distributions VALUES "
                "(?, 2025, -5.0, 0.0, 1.0, 2.0, 3.0, 1.0, 0.5, 10, 10, TRUE, ?)",
                [FORMULA_SUM, FORMULA_LINK],
            )
        exporter = ExcelExporter(DatabaseConnectionManager(tmp_path / "missing.duckdb"))
        out_path = exporter.export_scenario_results(
            scenario_name="ens",
            output_dir=tmp_path / "ens_out",
            config=_mock_config(),
            seed=1,
            export_format="excel",
            ensemble_db_path=ensemble_db,
        )
        _assert_xlsx_has_no_formulas(out_path)
        values = _all_values(out_path)
        assert FORMULA_SUM in values
        assert FORMULA_LINK in values
        assert -5 in values


class TestComparisonExportServiceSafety:
    def test_write_only_xlsx_has_no_formulas_including_metadata(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "scenario.duckdb"
        with duckdb.connect(str(db_path)) as conn:
            conn.execute("""
                CREATE TABLE fct_workforce_snapshot (
                    scenario_id VARCHAR DEFAULT 'default',
                    employee_id VARCHAR,
                    simulation_year INTEGER,
                    current_compensation DECIMAL(12, 2)
                );
                CREATE TABLE stg_census_data (
                    employee_id VARCHAR,
                    department VARCHAR
                );
                """)
            conn.execute(
                "INSERT INTO fct_workforce_snapshot VALUES "
                "('default', ?, 2025, -5.00), ('default', ?, 2025, 100.00)",
                [FORMULA_SUM, FORMULA_LINK],
            )
            conn.execute(
                "INSERT INTO stg_census_data VALUES (?, ?)",
                [FORMULA_SUM, FORMULA_LINK],
            )

        scenario = ExportScenario(
            scenario_id="s1",
            name=FORMULA_SUM,
            database_path=db_path,
            census_path=FORMULA_LINK,
            run_id="r1",
        )
        service = ComparisonExportService(storage=None, db_resolver=object())  # type: ignore[arg-type]
        out_dir = tmp_path / "cmp_out"
        out_dir.mkdir()
        xlsx_path = service.build([scenario], FORMULA_LINK, "xlsx", out_dir)

        _assert_xlsx_has_no_formulas(xlsx_path)
        values = _all_values(xlsx_path)
        assert FORMULA_SUM in values
        assert FORMULA_LINK in values
        assert -5 in values


class TestAnalyzeCostExcelSafety:
    def test_export_cost_excel_has_no_formulas_and_preserves_negative_numbers(
        self, tmp_path: Path
    ) -> None:
        year_row = SimpleNamespace(
            simulation_year=2025,
            gross_employer_match=Decimal("100"),
            gross_employer_core=Decimal("50"),
            gross_employer_cost=Decimal("150"),
            total_compensation=Decimal("1000"),
            forfeitures_generated=None,
            forfeiture_offset_applied=None,
            net_employer_cost=Decimal("-5"),
            gross_cost_pct_of_compensation=Decimal("0.15"),
            net_cost_pct_of_compensation=Decimal("-0.005"),
            offset_basis_available=False,
            offset_unavailable_reason=FORMULA_LINK,
        )
        series = [
            SimpleNamespace(
                scenario_name=FORMULA_SUM,
                schedule_name=FORMULA_LINK,
                forfeiture_policy=ForfeiturePolicy.OFFSET_EMPLOYER_CONTRIBUTIONS,
                years=[year_row],
                total_gross_employer_cost=Decimal("150"),
                total_forfeiture_offset=Decimal("0"),
                total_net_employer_cost=Decimal("-5"),
                years_without_offset_basis=[2025],
            ),
            SimpleNamespace(
                scenario_name=FORMULA_LINK,
                schedule_name=FORMULA_SUM,
                forfeiture_policy=ForfeiturePolicy.PAY_PLAN_EXPENSES,
                years=[year_row],
                total_gross_employer_cost=Decimal("150"),
                total_forfeiture_offset=Decimal("0"),
                total_net_employer_cost=Decimal("-5"),
                years_without_offset_basis=[2025],
            ),
        ]
        out_path = _export_cost_excel(series, str(tmp_path / "cost.xlsx"))
        _assert_xlsx_has_no_formulas(out_path)
        values = _all_values(out_path)
        assert f"'{FORMULA_SUM}" in values
        assert f"'{FORMULA_LINK}" in values
        assert -5 in values


class TestReportPptxEmbeddedChartSafety:
    def test_pptx_embedded_chart_workbook_has_no_formulas(self, tmp_path: Path) -> None:
        pptx = pytest.importorskip("pptx")
        design = ReportPlanDesign(
            eligibility="Immediate",
            auto_enrollment="3%",
            escalation="None",
            match="100% up to 4%",
            core="None",
        )
        scenarios = [
            ReportScenario(
                scenario_id="s0",
                name=FORMULA_SUM,
                is_anchor=True,
                design=design,
                years=[
                    ReportYear(
                        year=2026,
                        employer_cost=-5.0,
                        cost_pct_of_capped_pay=4.0,
                        participation_rate=70.0,
                        average_deferral_rate=5.0,
                    )
                ],
                total_employer_cost=-5.0,
                total_cost_pct_of_capped_pay=4.0,
            ),
            ReportScenario(
                scenario_id="s1",
                name=FORMULA_LINK,
                is_anchor=False,
                design=design,
                years=[
                    ReportYear(
                        year=2026,
                        employer_cost=100.0,
                        cost_pct_of_capped_pay=5.0,
                        participation_rate=75.0,
                        average_deferral_rate=6.0,
                    )
                ],
                total_employer_cost=100.0,
                total_cost_pct_of_capped_pay=5.0,
            ),
        ]
        report = ScenarioReport(
            title="Safety test",
            generated_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
            anchor_scenario_id="s0",
            scenarios=scenarios,
            definitions=[ReportDefinition(term="employer_cost", text="Cost note.")],
            provenance=[
                ReportProvenance(
                    workspace_id="ws",
                    scenario_id=s.scenario_id,
                    scenario_name=s.name,
                    run_id=f"run-{s.scenario_id}",
                    config_fingerprint="a" * 12,
                )
                for s in scenarios
            ],
        )
        pptx_path = tmp_path / "report.pptx"
        render_pptx(report, pptx_path)
        deck = pptx.Presentation(str(pptx_path))
        chart_shapes = [
            shape
            for slide in deck.slides
            for shape in slide.shapes
            if shape.name == CHART_NAME
        ]
        assert len(chart_shapes) == 1
        xlsx_blob = chart_shapes[0].chart.part.chart_workbook.xlsx_part.blob
        _assert_xlsx_has_no_formulas(xlsx_blob)
        values = _all_values(xlsx_blob)
        assert any(
            isinstance(v, str) and v.startswith(f"'{FORMULA_SUM}") for v in values
        )
        assert any(
            isinstance(v, str) and v.startswith(f"'{FORMULA_LINK}") for v in values
        )
        assert -5 in values
