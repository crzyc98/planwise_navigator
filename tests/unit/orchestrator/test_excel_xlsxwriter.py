"""Fast parity checks for the per-run workbook engine."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pytest
from openpyxl import load_workbook

from planalign_orchestrator.excel_exporter import ExcelExporter
from scripts.perf_profile.compare_workbooks import compare_workbooks

pytestmark = pytest.mark.fast


def fixture_frame() -> pd.DataFrame:
    with duckdb.connect(":memory:") as conn:
        return conn.execute("""
            SELECT i::INTEGER AS employee_id, 2025 AS simulation_year,
                CASE WHEN i = 1 THEN NULL ELSE i % 2 = 0 END AS flag,
                CASE WHEN i = 1 THEN NULL ELSE i / 10.0 END::DOUBLE AS amount,
                CASE WHEN i = 1 THEN NULL ELSE i / 100.0 END::DECIMAL(10,2) AS money,
                CASE WHEN i = 1 THEN NULL ELSE DATE '2025-01-01' END AS day,
                CASE WHEN i = 1 THEN NULL ELSE TIMESTAMP '2025-01-01 12:34:56.123' END AS stamp,
                CASE WHEN i = 1 THEN NULL ELSE TIMESTAMPTZ '2025-01-01 12:34:56+03' END AS zoned,
                CASE WHEN i = 201 THEN repeat('z', 100) ELSE '' END AS sampled
            FROM range(202) t(i)
        """).df()


def write_pair(tmp_path: Path, frame: pd.DataFrame) -> tuple[Path, Path]:
    exporter = ExcelExporter(None)
    paths = (tmp_path / "old.xlsx", tmp_path / "new.xlsx")
    frame = exporter._sanitize_for_excel(frame)
    for path, engine in zip(paths, ("openpyxl", "xlsxwriter")):
        with pd.ExcelWriter(path, engine=engine) as writer:
            exporter._write_formatted_sheet(writer, "Data", frame)
    return paths


def test_duckdb_roundtrip_and_formatting(tmp_path: Path) -> None:
    first, second = write_pair(tmp_path, fixture_frame())
    assert compare_workbooks(first, second) == []
    book = load_workbook(second)
    sheet = book["Data"]
    assert sheet.freeze_panes == "A2"
    assert sheet["C2"].value is True
    assert sheet["C3"].value is None
    assert sheet["C5"].value is False
    assert sheet["D2"].value == 0
    assert sheet["F2"].value == datetime(2025, 1, 1)
    assert sheet["G2"].value == datetime(2025, 1, 1, 12, 34, 56, 123000)
    assert sheet["H2"].value == datetime(2025, 1, 1, 9, 34, 56)
    assert sheet.column_dimensions["I"].width == len("sampled") + 2
    assert sheet["A1"].font.bold
    assert sheet["A1"].fill.fgColor.rgb[-6:] == "E6E6FA"
    assert sheet["A1"].alignment.horizontal == "center"
    book.close()


@pytest.mark.parametrize(
    "values",
    [
        [None, float("nan"), 0, False, 1.0, 1.25, Decimal("123.4500")],
        [date(2025, 1, 2), datetime(2025, 1, 2, 3, 4), pd.NaT, None],
        ["x" * 100, "=1+1", "https://example.com", "", None],
    ],
)
def test_object_conversion_widths(tmp_path: Path, values: list[Any]) -> None:
    first, second = write_pair(
        tmp_path, pd.DataFrame({"v": pd.Series(values, dtype=object)})
    )
    assert compare_workbooks(first, second) == []


def test_checker_rejects_changed_value_and_style(tmp_path: Path) -> None:
    first, second = write_pair(tmp_path, pd.DataFrame({"v": [1, 2]}))
    book = load_workbook(second)
    book["Data"]["A2"] = False
    book["Data"].freeze_panes = "B2"
    book.save(second)
    book.close()
    errors = compare_workbooks(first, second)
    assert any("bool" in error for error in errors)
    assert any("freeze panes" in error for error in errors)
