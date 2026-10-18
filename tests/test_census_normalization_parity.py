"""Shared import vectors for direct SQL uploads and mapped pandas imports."""

import csv
from datetime import date
from io import StringIO

import duckdb
import pandas as pd
import pytest

from planalign_api.models.imports import FieldMapping
from planalign_api.services.file_service import FileService
from planalign_api.services.mapping_engine import MappingEngine

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("column", "kind", "values", "expected"),
    [
        (
            "active",
            "boolean",
            [" Y ", "employed", "0", "  "],
            [True, True, False, None],
        ),
        (
            "employee_hire_date",
            "date",
            ["2020-01-15", "2021-02-16", "  "],
            [date(2020, 1, 15), date(2021, 2, 16), None],
        ),
        (
            "employee_gross_compensation",
            "decimal",
            ["$1,200.50", "(€ 300)", "  "],
            [1200.5, -300.0, None],
        ),
    ],
)
def test_direct_and_mapped_inputs_share_normalized_values(
    tmp_path, column, kind, values, expected
):
    rows = [[f" EMP{i:03d} ", value] for i, value in enumerate(values)]
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["employee_id", column])
    writer.writerows(rows)

    service = FileService(tmp_path)
    _, _, path = service.save_uploaded_file(
        "ws", stream.getvalue().encode(), "input.csv"
    )
    with duckdb.connect(":memory:") as conn:
        direct = conn.execute(
            f'SELECT employee_id, "{column}" FROM read_parquet(?) ORDER BY employee_id',
            [path],
        ).fetchall()

    mappings = [
        FieldMapping(
            input_column="id",
            output_column="employee_id",
            output_type="string",
            transformations=[],
        ),
        FieldMapping(
            input_column="value",
            output_column=column,
            output_type=kind,
            transformations=[],
        ),
    ]
    mapped = MappingEngine().apply(
        pd.DataFrame({"id": [row[0] for row in rows], "value": values}), mappings
    )
    mapped_values = [None if pd.isna(value) else value for value in mapped[column]]

    assert direct == [(f"EMP{i:03d}", value) for i, value in enumerate(expected)]
    assert mapped["employee_id"].tolist() == [f"EMP{i:03d}" for i in range(len(values))]
    assert mapped_values == expected
