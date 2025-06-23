"""Ingest census_preprocessed.parquet into DuckDB and run validation queries.

Usage::
    python -m orchestrator.ingest_data

This script will:
1. Connect to the DuckDB database (simulation.duckdb)
2. Create or replace the table `census_raw` from the Parquet file in data/
3. Print the table schema (DESCRIBE)
4. Validate row counts between the table and the source Parquet file
5. Compute basic summary statistics on numeric columns
"""
from pathlib import Path
from typing import List
import duckdb

# Local imports
from .connect_db import get_connection  # noqa: E402

DATA_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "census_preprocessed.parquet"
)


def ingest(con: duckdb.DuckDBPyConnection) -> None:
    """Create or replace the `census_raw` table from the Parquet file."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Parquet file not found at {DATA_FILE}. Please place it in the data/ directory."
        )

    sql = "CREATE OR REPLACE TABLE census_raw AS " "SELECT * FROM read_parquet(?);"
    con.execute(sql, [str(DATA_FILE)])
    print("✅ Loaded data into table census_raw\n")


def describe_table(con: duckdb.DuckDBPyConnection) -> List[tuple]:
    """Return and print the schema of census_raw."""
    rows = con.execute("DESCRIBE census_raw").fetchall()
    print("Table schema (DESCRIBE census_raw):")
    print("Column | Type | Null | Default | Extras")
    print("-" * 50)
    for row in rows:
        print(" | ".join(str(v) for v in row))
    print()
    return rows


def validate_row_counts(con: duckdb.DuckDBPyConnection) -> None:
    """Compare row counts between parquet and table."""
    table_count = con.execute("SELECT COUNT(*) FROM census_raw").fetchone()[0]
    parquet_count = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?)", [str(DATA_FILE)]
    ).fetchone()[0]

    print(f"Row count in census_raw     : {table_count}")
    print(f"Row count in source Parquet : {parquet_count}")
    status = "✅ MATCH" if table_count == parquet_count else "⚠️  MISMATCH"
    print(f"Status: {status}\n")


def summary_stats(con: duckdb.DuckDBPyConnection, schema_rows: List[tuple]) -> None:
    """Compute summary statistics on numeric columns."""
    numeric_types = {"INTEGER", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT"}
    numeric_cols = [
        r[0] for r in schema_rows if str(r[1]).upper().split("(")[0] in numeric_types
    ]

    if not numeric_cols:
        print("No numeric columns found for summary statistics.\n")
        return

    select_clauses = []
    for col in numeric_cols:
        select_clauses.append(
            f"COUNT({col}) AS {col}_count, MIN({col}) AS {col}_min, "
            f"MAX({col}) AS {col}_max, AVG({col}) AS {col}_avg"
        )
    query = "SELECT " + ", ".join(select_clauses) + " FROM census_raw;"
    stats = con.execute(query).fetchone()

    print("Summary statistics:")
    idx = 0
    for col in numeric_cols:
        cnt, mn, mx, avg = stats[idx : idx + 4]
        idx += 4
        print(f"{col}: count={cnt}, min={mn}, max={mx}, avg={avg}")
    print()


if __name__ == "__main__":
    con = get_connection()

    ingest(con)
    schema_rows = describe_table(con)
    validate_row_counts(con)
    summary_stats(con, schema_rows)

    con.close()
