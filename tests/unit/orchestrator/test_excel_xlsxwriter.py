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


def write_pair(
    tmp_path: Path, frame: pd.DataFrame, sheet_name: str = "Workforce_Snapshot"
) -> tuple[Path, Path]:
    exporter = ExcelExporter(None)
    paths = (tmp_path / "old.xlsx", tmp_path / "new.xlsx")
    frame = exporter._sanitize_for_excel(frame)
    for path, engine in zip(paths, ("openpyxl", "xlsxwriter")):
        with pd.ExcelWriter(
            path,
            engine=engine,
            engine_kwargs=(
                {"options": {"strings_to_urls": False}}
                if engine == "xlsxwriter"
                else {}
            ),
        ) as writer:
            exporter._write_formatted_sheet(writer, sheet_name, frame)
    return paths


@pytest.mark.parametrize(
    "sheet_name", ["Workforce_Snapshot", "Workforce_2025", "Events_Detail"]
)
def test_duckdb_roundtrip_and_formatting(tmp_path: Path, sheet_name: str) -> None:
    first, second = write_pair(tmp_path, fixture_frame(), sheet_name)
    assert compare_workbooks(first, second) == []
    book = load_workbook(second)
    sheet = book[sheet_name]
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
    book["Workforce_Snapshot"]["A2"] = False
    book["Workforce_Snapshot"].freeze_panes = "B2"
    book.save(second)
    book.close()
    errors = compare_workbooks(first, second)
    assert any("bool" in error for error in errors)
    assert any("freeze panes" in error for error in errors)


@pytest.mark.parametrize(
    "dtype,values",
    [
        ("Int64", [None, 0, -7]),
        ("UInt64", [None, 0, 7]),
        ("Float64", [None, float("inf"), -float("inf")]),
        ("float64", [float("nan"), 0.0, 1.5]),
        ("boolean", [None, True, False]),
        ("string", [None, "00123", "https://example.com"]),
        ("datetime64[ns]", [pd.NaT, datetime(2025, 1, 2), None]),
        (
            "datetime64[ns, US/Eastern]",
            [pd.NaT, pd.Timestamp("2025-01-02", tz="US/Eastern"), None],
        ),
        (object, [None, Decimal("123.4500"), Decimal("NaN")]),
        (object, [None, date(2025, 1, 2), pd.Timestamp("2025-01-02", tz="US/Eastern")]),
        (object, [None, "x" * 40000, "=1+1"]),
        (object, [None, "00123", "https://example.com"]),
    ],
)
def test_direct_column_conversions(
    tmp_path: Path, dtype: Any, values: list[Any]
) -> None:
    first, second = write_pair(
        tmp_path, pd.DataFrame({"v": pd.Series(values, dtype=dtype)})
    )
    assert compare_workbooks(first, second) == []
    book = load_workbook(second)
    assert (2, 1) in book["Workforce_Snapshot"]._cells
    assert book["Workforce_Snapshot"]["A2"].number_format == "General"
    assert book["Workforce_Snapshot"]["A4"].hyperlink is None
    book.close()


def test_direct_writer_rejects_oversized_sheet(tmp_path: Path) -> None:
    frame = pd.DataFrame(index=pd.RangeIndex(1_048_577))
    with pd.ExcelWriter(tmp_path / "oversized.xlsx", engine="xlsxwriter") as writer:
        with pytest.raises(ValueError, match="This sheet is too large"):
            ExcelExporter(None)._write_formatted_sheet(writer, "Events_Detail", frame)
