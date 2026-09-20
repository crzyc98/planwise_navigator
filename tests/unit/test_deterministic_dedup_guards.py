"""Source contracts for fail-loud dbt grain guards."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_MODEL = ROOT / "dbt/models/marts/fct_workforce_snapshot.sql"
CORE_MODEL = ROOT / "dbt/models/intermediate/int_employer_core_contributions.sql"


def test_snapshot_baseline_rejects_duplicates_without_row_number_dedup() -> None:
    source = SNAPSHOT_MODEL.read_text()

    assert "baseline_duplicate_guard AS" in source
    assert "duplicate baseline workforce rows" in source
    assert "HAVING COUNT(*) > 1" in source
    assert "baseline_rank" not in source
    assert "PARTITION BY employee_id ORDER BY employee_id" not in source


def test_core_contributions_reject_duplicates_before_publication() -> None:
    source = CORE_MODEL.read_text()

    guard = source.index("duplicate_row_guard AS")
    validated = source.index("validated_integration_basis AS")
    publication = source.index("SELECT\n    employee_id,", validated)

    assert guard < validated < publication
    assert "duplicate employer core rows" in source
    assert "GROUP BY employee_id, plan_design_id, simulation_year" in source
    assert "WHERE rn = 1" not in source
