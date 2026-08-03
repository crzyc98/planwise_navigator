"""Integration gates for the byte-identical subsystem-seed dbt refactor."""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator
from tests.invariants.comparison import COMPARED_TABLES, compare_tables


pytest_plugins = ("tests.fixtures.invariant_simulation",)


ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT = ROOT / "dbt"
CONFIG_PATH = ROOT / "tests/fixtures/invariant_config.yaml"
_REFRACTOR_FILES = {
    "models/intermediate/events/int_termination_events.sql": "termination",
    "models/intermediate/events/int_new_hire_termination_events.sql": "termination",
    "models/intermediate/events/int_hiring_events.sql": "hiring",
    "models/intermediate/events/int_promotion_events.sql": "promotion",
}


@pytest.mark.integration
def test_default_subsystem_seed_refactor_is_output_identical(
    tmp_path, invariant_census_parquet
) -> None:
    """Default fallback must reproduce pre-refactor event and snapshot state exactly."""
    candidate_project = _copy_project(tmp_path / "candidate-project")
    baseline_project = _copy_project(tmp_path / "baseline-project")
    assert _restore_pre_refactor_seed_calls(baseline_project) == 10

    baseline_db = _run_project(
        baseline_project, tmp_path / "baseline.duckdb", invariant_census_parquet
    )
    candidate_db = _run_project(
        candidate_project, tmp_path / "candidate.duckdb", invariant_census_parquet
    )

    for table in COMPARED_TABLES:
        count_a, count_b, differences, samples = compare_tables(
            baseline_db, candidate_db, table
        )
        assert (
            count_a == count_b and differences == 0
        ), f"{table} changed under default subsystem seeds: {samples!r}"


@pytest.mark.integration
def test_termination_freeze_is_effective_and_does_not_pin_other_streams(
    tmp_path, invariant_census_parquet
) -> None:
    """A termination override holds that stream while global-seeded draws vary."""
    unfrozen_a = _run_project(
        _copy_project(tmp_path / "unfrozen-a-project"),
        tmp_path / "unfrozen_a.duckdb",
        invariant_census_parquet,
        seed=101,
        end_year=2025,
    )
    unfrozen_b = _run_project(
        _copy_project(tmp_path / "unfrozen-b-project"),
        tmp_path / "unfrozen_b.duckdb",
        invariant_census_parquet,
        seed=202,
        end_year=2025,
    )
    frozen_a = _run_project(
        _copy_project(tmp_path / "frozen-a-project"),
        tmp_path / "frozen_a.duckdb",
        invariant_census_parquet,
        seed=101,
        frozen_subsystem_seeds={"termination": 17},
        end_year=2025,
    )
    frozen_b = _run_project(
        _copy_project(tmp_path / "frozen-b-project"),
        tmp_path / "frozen_b.duckdb",
        invariant_census_parquet,
        seed=202,
        frozen_subsystem_seeds={"termination": 17},
        end_year=2025,
    )

    assert _termination_decisions(frozen_a) == _termination_decisions(frozen_b)
    assert _termination_decisions(unfrozen_a) != _termination_decisions(unfrozen_b)

    # The override is scoped to termination. Hiring remains byte-identical to
    # its matching unfrozen world, and promotion still receives the global seed
    # (its population can legitimately reflect the now-frozen terminations).
    assert _event_rows(frozen_a, "hire") == _event_rows(unfrozen_a, "hire")
    assert _event_rows(frozen_b, "hire") == _event_rows(unfrozen_b, "hire")
    assert _event_rows(frozen_a, "promotion") != _event_rows(frozen_b, "promotion")


def _copy_project(destination: Path) -> Path:
    """Copy dbt source and packages while leaving shared targets and DBs untouched."""
    shutil.copytree(
        DBT_PROJECT,
        destination,
        ignore=shutil.ignore_patterns(
            "target", "logs", "*.duckdb", "*.duckdb.wal", "__pycache__"
        ),
    )
    return destination


def _restore_pre_refactor_seed_calls(project: Path) -> int:
    """Make a local baseline project using exact pre-refactor global seed calls."""
    replacements = 0
    for relative_path, subsystem in _REFRACTOR_FILES.items():
        path = project / relative_path
        source = path.read_text(encoding="utf-8")
        needle = f"subsystem_seed('{subsystem}')"
        replacements += source.count(needle)
        path.write_text(
            source.replace(needle, "var('random_seed', 42)"), encoding="utf-8"
        )
    return replacements


def _run_project(
    project: Path,
    database: Path,
    census_parquet: Path,
    *,
    seed: int | None = None,
    frozen_subsystem_seeds: dict[str, int] | None = None,
    end_year: int = 2027,
) -> Path:
    """Run the same isolated fixture against one project variant.

    The freeze-containment case uses a single year so all worlds start from
    the same census. Multi-year workforce changes from other, deliberately
    unfrozen streams would otherwise change later candidate populations.
    """
    config = load_simulation_config(CONFIG_PATH, env_overrides=False)
    config.setup["census_parquet_path"] = str(census_parquet)
    if seed is not None:
        config = config.model_copy(
            update={
                "simulation": config.simulation.model_copy(update={"random_seed": seed})
            }
        )
    if frozen_subsystem_seeds:
        config = config.model_copy(
            update={
                "ensemble": config.ensemble.model_copy(
                    update={"frozen_subsystem_seeds": frozen_subsystem_seeds}
                )
            }
        )
    built = build_orchestrator(
        ConstructionSpec(
            config=config,
            database=database,
            threads=1,
            dbt_project_dir=project,
            dbt_artifacts_dir=database.parent / f"{database.stem}-artifacts",
            entry_point="invariant_test",
            validation_mode=True,
        )
    )
    built.orchestrator.execute_multi_year_simulation(
        start_year=2025, end_year=end_year, fail_on_validation_error=True
    )
    return database


def _event_rows(database: Path, event_type: str) -> list[tuple[object, ...]]:
    """Read semantic event state without globally-seeded UUID/timestamp fields."""
    columns = (
        "employee_id",
        "event_type",
        "simulation_year",
        "effective_date",
        "event_details",
        "compensation_amount",
        "previous_compensation",
        "employee_deferral_rate",
        "prev_employee_deferral_rate",
        "employee_age",
        "employee_tenure",
        "level_id",
        "age_band",
        "tenure_band",
        "event_probability",
        "event_category",
    )
    projection = ", ".join(columns)
    order_by = ", ".join(("simulation_year", "employee_id", "effective_date"))
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(
            f"SELECT {projection} FROM fct_yearly_events "
            f"WHERE event_type = ? ORDER BY {order_by}",
            [event_type],
        ).fetchall()


def _termination_decisions(database: Path) -> list[tuple[object, ...]]:
    """Compare only termination-stream decisions, not hiring-derived attributes."""
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.execute(
            "SELECT employee_id, event_type, simulation_year, effective_date, "
            "event_probability, event_category "
            "FROM fct_yearly_events WHERE event_type = 'termination' "
            "ORDER BY simulation_year, employee_id, effective_date"
        ).fetchall()
