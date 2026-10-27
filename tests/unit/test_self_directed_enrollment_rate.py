"""Execute the shared enrollment SQL with boundary inputs and seeded draws."""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast

import duckdb
from jinja2 import Environment, StrictUndefined
from jinja2.nativetypes import NativeEnvironment
import pytest

pytestmark = pytest.mark.fast
MACROS = Path(__file__).resolve().parents[2] / "dbt/macros"
TIERS = [
    {"max_auto_enroll_default_rate": 0.03, "share": 0.10},
    {"max_auto_enroll_default_rate": None, "share": 0.15},
]


SQLExpression = str | float | int


class EnrollmentMacros(Protocol):
    def below_default_share(
        self, auto_default: SQLExpression, tiers: Any = ...
    ) -> str: ...
    def below_default_effective_share(
        self, auto_default: SQLExpression, age: SQLExpression, income: SQLExpression
    ) -> str: ...
    def below_default_rate(
        self, auto_default: SQLExpression, step_random: SQLExpression
    ) -> str: ...
    def enrollment_behavior_draw(
        self, employee_id: str, simulation_year: SQLExpression, salt: str
    ) -> str: ...
    def self_directed_enrollment_rate(
        self,
        selected_rate: SQLExpression,
        ceiling: SQLExpression,
        magnet_random: SQLExpression,
        employee_id: str,
        simulation_year: SQLExpression,
        upward_enabled: bool = ...,
        auto_default: SQLExpression | None = ...,
        age: SQLExpression = ...,
        income: SQLExpression = ...,
    ) -> str: ...
    def match_magnet_snap(
        self,
        selected_rate: SQLExpression,
        ceiling: SQLExpression,
        magnet_random: SQLExpression,
        enabled: bool,
        snap_prob: float,
        downward_enabled: bool,
        auto_default: SQLExpression,
        upward_enabled: bool,
    ) -> str: ...


def _macros(neutral: bool = True, **variables: Any) -> EnrollmentMacros:
    source = "\n".join(
        (MACROS / name).read_text()
        for name in (
            "utils/subsystem_seed.sql",
            "match_magnet_snap.sql",
            "deferral_change.sql",
            "self_directed_enrollment_rate.sql",
        )
    )
    if neutral:
        bands = [{"min": 0, "multiplier": 1}]
        variables = {
            "below_default_multipliers_age": bands,
            "below_default_multipliers_income": bands,
            **variables,
        }
    return cast(
        EnrollmentMacros,
        NativeEnvironment(undefined=StrictUndefined)
        .from_string(source)
        .make_module(
            {
                "var": lambda name, default=None: variables.get(name, default),
                "return": lambda x: x,
            }
        ),
    )


@pytest.fixture(scope="module")
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect() as conn:
        module = (
            Environment()
            .from_string((MACROS / "utils/stable_hash.sql").read_text())
            .module
        )
        conn.execute(getattr(module, "install_stable_hash")())
        yield conn


@pytest.mark.parametrize(
    "default,share", [(0.02, 0.10), (0.03, 0.10), (0.0301, 0.15), (0.06, 0.15)]
)
def test_tier_boundary_is_inclusive(
    connection: duckdb.DuckDBPyConnection, default: float, share: float
) -> None:
    sql = _macros().below_default_share("auto_default", TIERS)
    result = connection.execute(
        f"SELECT {sql} FROM (SELECT {default} AS auto_default)"
    ).fetchone()
    assert result is not None
    assert float(result[0]) == share


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
    result = connection.execute(f"SELECT {sql}").fetchone()
    assert result is not None
    assert result[0] == Decimal(str(expected))


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
    result = connection.execute(f"SELECT {sql}").fetchone()
    assert result is not None
    assert result[0] == Decimal(str(expected))


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
    result = connection.execute(f"SELECT {sql}").fetchone()
    assert result is not None
    assert result[0] == Decimal("0.05")


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
    result = connection.execute(f"SELECT {sql}").fetchone()
    assert result is not None
    assert result[0] == Decimal(str(expected))
    sql = module.self_directed_enrollment_rate(
        0.06, 0.04, 0.0, "'employee'", 2025, upward
    )
    result = connection.execute(f"SELECT {sql}").fetchone()
    assert result is not None
    assert result[0] == Decimal("0.06")


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


@pytest.mark.parametrize("upward", [True, False])
def test_per_row_defaults_resolve_all_four_decisions(
    connection: duckdb.DuckDBPyConnection, upward: bool
) -> None:
    module = _macros(
        auto_enrollment_default_deferral_rate=0.10,
        below_default_share_tiers=TIERS,
        enrollment_match_magnet_downward_enabled=True,
        enrollment_match_magnet_probability=1.0,
    )
    sql = module.self_directed_enrollment_rate(
        "0.01",
        "0.04",
        "magnet_draw",
        "employee_id",
        2025,
        upward_enabled=upward,
        auto_default="ae_default",
    )
    choice = module.enrollment_behavior_draw("employee_id", 2025, "-below-default-")
    step = module.enrollment_behavior_draw("employee_id", 2025, "-below-default-step-")
    rows = connection.execute(
        "WITH employees AS (SELECT 'employee-' || i AS employee_id, ae_default, "
        "magnet_draw FROM range(1000) t(i) CROSS JOIN (VALUES (0.03), (0.06)) d(ae_default) "
        "CROSS JOIN (VALUES (0.0), (1.0)) m(magnet_draw)) "
        f"SELECT ae_default, magnet_draw, {choice}, {step}, {sql} FROM employees"
    ).fetchall()
    for default, magnet_draw, choose_draw, step_draw, actual in rows:
        share = 0.10 if default == Decimal("0.03") else 0.15
        if choose_draw < share:
            pp = 1 if step_draw < 0.5 else 2 if step_draw < 0.8 else 3
            expected = max(Decimal("0.01"), default - Decimal("0.01") * pp)
        elif magnet_draw == 0 and (upward or default == Decimal("0.06")):
            expected = Decimal("0.04")
        else:
            expected = default
        assert actual == expected


@pytest.mark.parametrize(
    "age,income,share,expected",
    [
        (25, 30000, 0.15, 0.336),
        (65, 200000, 0.15, 0.04875),
        (30, 40000, 0.15, 0.198),
        (25, 30000, 0.9, 1.0),
    ],
)
def test_below_default_demographic_share_and_cap(
    connection: duckdb.DuckDBPyConnection,
    age: int,
    income: int,
    share: float,
    expected: float,
) -> None:
    from planalign_orchestrator.config.participant_behavior import BelowDefaultSettings

    multipliers = BelowDefaultSettings().multipliers.model_dump()
    module = _macros(
        **{
            f"below_default_multipliers_{key}": value
            for key, value in multipliers.items()
        },
        below_default_share_tiers=[
            {"max_auto_enroll_default_rate": None, "share": share}
        ],
    )
    sql = module.below_default_effective_share(0.06, age, income)
    result = connection.execute(f"SELECT {sql}").fetchone()
    assert result is not None
    assert result[0] == pytest.approx(expected)
    fallback = _macros(
        neutral=False,
        below_default_share_tiers=[
            {"max_auto_enroll_default_rate": None, "share": share}
        ],
    ).below_default_effective_share(0.06, age, income)
    assert connection.execute(f"SELECT {fallback}").fetchone() == result


def test_below_default_neutral_choices_equal_legacy_sql(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    module = _macros(auto_enrollment_default_deferral_rate=0.06)
    actual = module.self_directed_enrollment_rate(
        0.06, 0.06, 1.0, "employee_id", 2025, False
    )
    draw = module.enrollment_behavior_draw("employee_id", 2025, "-below-default-")
    step = module.enrollment_behavior_draw("employee_id", 2025, "-below-default-step-")
    legacy = f"CASE WHEN {draw} < 0.15 THEN {module.below_default_rate(0.06, step)} ELSE 0.06 END"
    rows = connection.execute(
        f"SELECT {actual} = ({legacy}) FROM "
        "(SELECT 'employee-' || i AS employee_id FROM range(10000) t(i))"
    ).fetchall()
    assert all(row[0] for row in rows)


def test_below_default_demographics_drive_seeded_rate_choices(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    module = _macros(neutral=False, auto_enrollment_default_deferral_rate=0.06)
    rate = module.self_directed_enrollment_rate(
        0.06,
        0.06,
        1.0,
        "employee_id",
        2025,
        age="age",
        income="income",
    )
    draw = module.enrollment_behavior_draw("employee_id", 2025, "-below-default-")
    rows = connection.execute(
        f"SELECT age, {draw}, {rate} FROM "
        "(SELECT 'employee-' || i AS employee_id, age, income "
        "FROM range(10000) t(i) CROSS JOIN "
        "(VALUES (25, 30000), (65, 200000)) d(age, income))"
    ).fetchall()
    young = old = 0
    for age, choice, actual in rows:
        assert (actual < Decimal("0.06")) == (
            choice < (0.336 if age == 25 else 0.04875)
        )
        if actual < Decimal("0.06"):
            if age == 25:
                young += 1
            else:
                old += 1
    assert young > old > 0
