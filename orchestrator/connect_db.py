"""Connect to the DuckDB database `simulation.duckdb`.
This script will create the database file if it does not exist and simply
establish a connection to verify accessibility.
"""
from pathlib import Path
import duckdb

# Database lives at repo root
DB_PATH = Path(__file__).resolve().parent.parent / "simulation.duckdb"


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection to the database, creating the file if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    return con


if __name__ == "__main__":
    con = get_connection()
    print(f"Connected to DuckDB at {DB_PATH}")
    con.close()
