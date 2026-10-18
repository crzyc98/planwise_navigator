"""Shared paths for checked-in dbt seeds used by API services."""

from pathlib import Path

DBT_SEEDS_DIR = Path(__file__).resolve().parents[2] / "dbt" / "seeds"
