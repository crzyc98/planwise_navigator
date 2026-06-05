"""Regression tests: DuckDB 1.0.0 StringDtype normalization in generate_parquet.

DuckDB's read_parquet().df() returns pandas StringDtype columns, not object dtype.
DuckDB 1.0.0 cannot re-register a DataFrame with StringDtype columns, raising:
  NotImplementedException: Not implemented Error: Data type 'str' not recognized
"""

import io

import duckdb
import pandas as pd
import pytest


@pytest.mark.fast
def test_normalize_dtypes_removes_string_dtype():
    """_normalize_dtypes_for_duckdb converts StringDtype columns to object dtype."""
    from planalign_api.services.import_service import _normalize_dtypes_for_duckdb

    df = pd.DataFrame({"name": pd.array(["Alice", None, "Bob"], dtype="string")})
    assert isinstance(df["name"].dtype, pd.StringDtype)

    result = _normalize_dtypes_for_duckdb(df)
    assert result["name"].dtype == object


@pytest.mark.fast
def test_normalize_dtypes_noop_for_object_dtype():
    """_normalize_dtypes_for_duckdb is a no-op when no StringDtype columns are present."""
    from planalign_api.services.import_service import _normalize_dtypes_for_duckdb

    df = pd.DataFrame({"name": pd.Series(["Alice", None, "Bob"], dtype=object)})
    assert df["name"].dtype == object

    result = _normalize_dtypes_for_duckdb(df)
    assert result["name"].dtype == object
    assert result is df


@pytest.mark.fast
def test_duckdb_register_after_read_parquet(tmp_path):
    """End-to-end reproduction: CSV → source.parquet → read_parquet → normalize → COPY TO parquet.

    Without the fix, conn.register fails with:
      NotImplementedException: Not implemented Error: Data type 'str' not recognized
    """
    from planalign_api.services.import_service import _normalize_dtypes_for_duckdb

    csv_data = "employee_id,name,salary\nEMP001,Alice,75000\nEMP002,,85000\n"
    df = pd.read_csv(io.StringIO(csv_data), dtype=object)

    source_path = tmp_path / "source.parquet"
    conn = duckdb.connect(":memory:")
    conn.register("_src", df)
    conn.execute(f"COPY _src TO '{source_path}' (FORMAT PARQUET)")
    conn.close()

    conn = duckdb.connect(":memory:")
    df2 = conn.execute(f"SELECT * FROM read_parquet('{source_path}')").df()
    conn.close()

    assert any(isinstance(df2[c].dtype, pd.StringDtype) for c in df2.columns), (
        "Precondition: read_parquet must return StringDtype columns for this test to be meaningful"
    )

    df2 = _normalize_dtypes_for_duckdb(df2)

    output_path = tmp_path / "output.parquet"
    conn = duckdb.connect(":memory:")
    conn.register("_transformed", df2)
    conn.execute(f"COPY _transformed TO '{output_path}' (FORMAT PARQUET)")
    conn.close()

    assert output_path.exists()
    assert output_path.stat().st_size > 0
