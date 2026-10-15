"""Execute the raw census duplicate audit against optional-column variants."""

from datetime import date
from pathlib import Path

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest


MODEL = (
    Path(__file__).resolve().parents[2]
    / "dbt/models/staging/stg_census_duplicates_audit.sql"
)


@pytest.mark.fast
@pytest.mark.parametrize("include_ssn", [False, True])
@pytest.mark.parametrize("include_termination", [False, True])
def test_optional_columns_preserve_raw_duplicate_ranking(
    tmp_path: Path, include_ssn: bool, include_termination: bool
) -> None:
    parquet = tmp_path / "census.parquet"
    optional_columns = (
        ", 'synthetic-ssn'::VARCHAR AS employee_ssn" if include_ssn else ""
    ) + (
        ", DATE '2024-12-01' AS employee_termination_date"
        if include_termination
        else ""
    )
    with duckdb.connect(str(tmp_path / "audit.duckdb")) as conn:
        conn.execute(
            f"""COPY (
              SELECT employee_id, DATE '1980-01-01' AS employee_birth_date,
                employee_hire_date, employee_gross_compensation, TRUE AS active
                {optional_columns}
              FROM (VALUES
                ('duplicate', DATE '2020-01-01', 90000),
                ('duplicate', DATE '2021-01-01', 80000),
                ('duplicate', DATE '2021-01-01', 85000),
                ('unique', DATE '2020-01-01', 70000)
              ) AS census(employee_id, employee_hire_date, employee_gross_compensation)
            ) TO '{parquet.as_posix()}' (FORMAT PARQUET)"""
        )
        sql = (
            Environment(undefined=StrictUndefined)
            .from_string(MODEL.read_text())
            .render(config=lambda **_: "", var=lambda _: parquet.as_posix())
        )
        conn.execute(f"CREATE TABLE audit AS {sql}")
        rows = conn.execute(
            """SELECT employee_id, employee_gross_compensation, duplicate_count,
              occurrence_rank, dedup_status, employee_ssn, employee_termination_date
            FROM audit ORDER BY occurrence_rank"""
        ).fetchall()

    ssn = "synthetic-ssn" if include_ssn else None
    termination = date(2024, 12, 1) if include_termination else None
    assert rows == [
        ("duplicate", 85000, 3, 1, "KEPT", ssn, termination),
        ("duplicate", 80000, 3, 2, "DROPPED", ssn, termination),
        ("duplicate", 90000, 3, 3, "DROPPED", ssn, termination),
    ]
