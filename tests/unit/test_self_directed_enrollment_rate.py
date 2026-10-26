"""Execute the shared enrollment SQL with boundary inputs and seeded draws."""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
from jinja2 import Environment, StrictUndefined
from jinja2.environment import TemplateModule
from jinja2.nativetypes import NativeEnvironment
import pytest

pytestmark = pytest.mark.fast
MACROS = Path(__file__).resolve().parents[2] / "dbt/macros"
TIERS = [
    {"max_auto_enroll_default_rate": 0.03, "share": 0.10},
    {"max_auto_enroll_default_rate": None, "share": 0.15},
]


def _macros(**variables: Any) -> TemplateModule:
    source = "\n".join(
        (MACROS / name).read_text()
        for name in (
            "utils/subsystem_seed.sql",
            "match_magnet_snap.sql",
            "self_directed_enrollment_rate.sql",
        )
    )
    return (
        NativeEnvironment(undefined=StrictUndefined)
        .from_string(source)
        .make_module(
            {
                "var": lambda name, default=None: variables.get(name, default),
                "return": lambda x: x,
            }
        )
    )


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


@pytest.mark.parametrize(
    "default,share", [(0.02, 0.10), (0.03, 0.10), (0.0301, 0.15), (0.06, 0.15)]
)
def test_tier_boundary_is_inclusive(default: float, share: float) -> None:
    assert _macros().below_default_share(default, TIERS) == share


@pytest.mark.parametrize(
    "default,draw,expected",
    [
        (0.06, 0.0, 0.05),
        (0.06, 0.499999, 0.05),
        (0.06, 0.5, 0.04),
        (0.06, 0.8, 0.03),
        (0.06, 0.999999, 0.03),
        (0.03, 0.0, 0.02),
        (0.03, 0.5, 0.01),
        (0.03, 0.8, 0.01),
        (0.01, 0.0, 0.01),
    ],
)
def test_weight_boundaries_and_floor(
    connection: duckdb.DuckDBPyConnection,
    default: float,
    draw: float,
    expected: float,
) -> None:
    sql = _macros().below_default_rate(default, draw)
    assert connection.execute(f"SELECT {sql}").fetchone()[0] == Decimal(str(expected))


@pytest.mark.parametrize(
    "rate,ceiling,draw,enabled,downward,upward,expected",
    [
        (0.03, 0.04, 0.1, True, True, True, 0.04),
        (0.05, 0.04, 0.1, True, True, True, 0.04),
        (0.06, 0.04, 0.1, True, True, True, 0.04),
        (0.0601, 0.04, 0.1, True, True, True, 0.0601),
        (0.05, 0.04, 0.45, True, True, True, 0.05),
        (0.05, 0.04, 0.1, True, False, True, 0.05),
        (0.05, 0.04, 0.1, False, True, True, 0.05),
        (0.03, 0.04, 0.1, True, True, False, 0.03),
        (0.05, 0.04, 0.1, True, True, False, 0.04),
        (0.07, 0.06, 0.1, True, True, True, 0.07),
        (0.05, 0.0, 0.1, True, True, True, 0.05),
    ],
)
def test_magnet_window_and_probability(
    connection: duckdb.DuckDBPyConnection,
    rate: float,
    ceiling: float,
    draw: float,
    enabled: bool,
    downward: bool,
    upward: bool,
    expected: float,
) -> None:
    sql = _macros().match_magnet_snap(
        rate,
        ceiling,
        draw,
        enabled,
        0.45,
        downward,
        0.06,
        upward,
    )
    assert connection.execute(f"SELECT {sql}").fetchone()[0] == Decimal(str(expected))


@pytest.mark.parametrize("upward", [True, False])
@pytest.mark.parametrize("ceiling", [0.02, 0.08])
def test_deliberate_choices_bypass_both_magnet_directions(
    connection: duckdb.DuckDBPyConnection,
    upward: bool,
    ceiling: float,
) -> None:
    module = _macros(
        auto_enrollment_default_deferral_rate=0.06,
        below_default_share_tiers=[
            {"max_auto_enroll_default_rate": None, "share": 1.0}
        ],
        below_default_steps=[{"pp": 1, "weight": 1.0}],
        enrollment_match_magnet_downward_enabled=True,
        enrollment_match_magnet_probability=1.0,
    )
    sql = module.self_directed_enrollment_rate(
        0.06, ceiling, 0.0, "'employee'", 2025, upward
    )
    assert connection.execute(f"SELECT {sql}").fetchone()[0] == Decimal("0.05")


@pytest.mark.parametrize("upward,expected", [(True, 0.08), (False, 0.05)])
def test_ae_disabled_keeps_only_existing_upward_behavior(
    connection: duckdb.DuckDBPyConnection,
    upward: bool,
    expected: float,
) -> None:
    module = _macros(
        auto_enrollment_enabled=False,
        below_default_share_tiers=[
            {"max_auto_enroll_default_rate": None, "share": 1.0}
        ],
        enrollment_match_magnet_downward_enabled=True,
    )
    sql = module.self_directed_enrollment_rate(
        0.05, 0.08, 0.0, "'employee'", 2025, upward
    )
    assert connection.execute(f"SELECT {sql}").fetchone()[0] == Decimal(str(expected))
    sql = module.self_directed_enrollment_rate(
        0.06, 0.04, 0.0, "'employee'", 2025, upward
    )
    assert connection.execute(f"SELECT {sql}").fetchone()[0] == Decimal("0.06")


def test_draws_are_repeatable_independent_and_follow_subsystem_seed(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    def draws(**variables: Any) -> list[tuple[float, float]]:
        module = _macros(**variables)
        expressions = [
            module.enrollment_behavior_draw("'employee-' || i", 2025, salt)
            for salt in ("-below-default-", "-below-default-step-")
        ]
        return connection.execute(
            f"SELECT {','.join(expressions)} FROM range(100) t(i)"
        ).fetchall()

    baseline = draws(random_seed=42)
    assert baseline == draws(random_seed=42)
    assert baseline != draws(random_seed=43)
    assert baseline == draws(random_seed=43, random_seed_deferral_behavior=42)
    assert any(choice != step for choice, step in baseline)
    assert all(0 <= value < 1 for row in baseline for value in row)


@pytest.mark.parametrize("upward", [True, False])
@pytest.mark.parametrize(
    "ae,share,ceiling,draw,magnet,expected",
    [
        (True, 0.15, 0.04, 0.9, True, 0.06),
        (True, 0.15, 0.04, 0.1, True, 0.04),
        (True, 0.15, 0.04, 0.1, False, 0.06),
        (True, 0.0, 0.04, 0.9, True, 0.02),
        (False, 0.15, 0.04, 0.9, True, 0.02),
    ],
)
def test_non_chooser_floor_precedes_magnet_only_with_active_share(
    connection: duckdb.DuckDBPyConnection,
    upward: bool,
    ae: bool,
    share: float,
    ceiling: float,
    draw: float,
    magnet: bool,
    expected: float,
) -> None:
    module = _macros(
        auto_enrollment_enabled=ae,
        auto_enrollment_default_deferral_rate=0.06,
        below_default_share_tiers=[
            {"max_auto_enroll_default_rate": None, "share": share}
        ],
        enrollment_match_magnet_enabled=magnet,
        enrollment_match_magnet_downward_enabled=True,
    )
    sql = module.self_directed_enrollment_rate(
        0.02, ceiling, draw, "employee_id", 2025, upward
    )
    choice = module.enrollment_behavior_draw("employee_id", 2025, "-below-default-")
    rates = connection.execute(
        "WITH employees AS (SELECT 'employee-' || i AS employee_id FROM range(100) t(i)) "
        f"SELECT DISTINCT {sql} FROM employees WHERE {choice} >= 0.15"
    ).fetchall()
    assert rates == [(Decimal(str(expected)),)]
