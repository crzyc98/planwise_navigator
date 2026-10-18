"""Write sponsoring-employer wage evidence beside an isolated run database."""

from pathlib import Path

import duckdb
import pandas as pd

from .contribution_sources import ContributionSourceSettings


def write_wage_evidence(
    settings: ContributionSourceSettings, database_path: Path
) -> Path:
    """Materialize a typed parquet input, including its schema when empty."""
    database = Path(database_path).resolve()
    path = database.with_suffix(".wage_evidence.parquet")
    temporary = path.with_suffix(".tmp.parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "employee_id",
        "employer_id",
        "wage_year",
        "wages",
        "basis",
        "provenance",
    ]
    records = [record.model_dump() for record in settings.wage_evidence]
    frame = pd.DataFrame.from_records(records, columns=columns).astype(object)
    with duckdb.connect() as connection:
        connection.register("wage_records", frame)
        connection.sql(
            "SELECT employee_id::VARCHAR AS employee_id, "
            "employer_id::VARCHAR AS employer_id, wage_year::INTEGER AS wage_year, "
            "wages::DECIMAL(18,2) AS wages, basis::VARCHAR AS basis, "
            "provenance::VARCHAR AS provenance FROM wage_records"
        ).write_parquet(str(temporary))
    temporary.replace(path)
    return path
