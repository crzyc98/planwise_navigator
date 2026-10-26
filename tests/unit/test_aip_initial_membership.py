"""Compile AIP membership SQL and execute it without a simulation database."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest

MACROS = Path(__file__).resolve().parents[2] / "dbt/macros"


def _compiler_error(message: str) -> None:
    raise ValueError(message)


def _compile(mode: str, **variables: Any) -> str:
    source = (MACROS / "utils/subsystem_seed.sql").read_text()
    source += (MACROS / "aip_initial_membership.sql").read_text()
    module = (
        Environment(undefined=StrictUndefined)
        .from_string(source)
        .make_module(
            {
                "var": lambda name, default=None: variables.get(name, default),
                "exceptions": SimpleNamespace(raise_compiler_error=_compiler_error),
            }
        )
    )
    return module.aip_initial_membership(mode, "census_opt_out", "employee_id").strip()


@pytest.fixture(scope="module")
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect() as conn:
        module = (
            Environment()
            .from_string((MACROS / "utils/stable_hash.sql").read_text())
            .module
        )
        conn.execute(module.install_stable_hash())
        yield conn


@pytest.mark.parametrize("mode", ["automatic", "participant_elected"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("probability", [0.0, 1.0])
@pytest.mark.parametrize("opt_out", [False, True, None])
def test_membership_compiles_and_respects_switches(
    connection: duckdb.DuckDBPyConnection,
    mode: str,
    enabled: bool,
    probability: float,
    opt_out: bool | None,
) -> None:
    sql = _compile(
        mode,
        deferral_escalation_enabled=enabled,
        deferral_escalation_participant_elected_signup_probability=probability,
    )
    actual = connection.execute(
        f"SELECT {sql} FROM (SELECT 'synthetic_employee' AS employee_id, "
        "?::BOOLEAN AS census_opt_out)",
        [opt_out],
    ).fetchone()[0]
    assert actual == (
        enabled and not opt_out and (mode == "automatic" or probability == 1.0)
    )


def test_automatic_sql_is_unchanged_and_elected_defaults_off() -> None:
    assert _compile("automatic") == "NOT COALESCE(census_opt_out, FALSE)"
    assert _compile("automatic", deferral_escalation_enabled=False) == "FALSE"
    assert "< 0.0" in _compile("participant_elected")


def test_election_is_seeded_and_independent_of_simulation_year(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    variables = {"deferral_escalation_participant_elected_signup_probability": 0.20}
    sql = _compile("participant_elected", simulation_year=2025, **variables)
    assert sql == _compile("participant_elected", simulation_year=2027, **variables)
    assert sql == _compile("participant_elected", random_seed=42, **variables)
    assert sql == _compile(
        "participant_elected",
        random_seed=99,
        random_seed_deferral_behavior=42,
        **variables,
    )
    reseeded = _compile("participant_elected", random_seed=99, **variables)
    rows = connection.execute(
        f"SELECT {sql}, {reseeded} FROM (SELECT "
        "'synthetic_' || i AS employee_id, FALSE AS census_opt_out "
        "FROM range(1000) employees(i))"
    ).fetchall()
    assert 150 < sum(member for member, _ in rows) < 250
    assert any(original != changed for original, changed in rows)


def test_unsupported_mode_still_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported deferral_escalation_mode"):
        _compile("unsupported")
