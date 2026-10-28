"""The engine upgrade must preserve seeded draws and census decimal rounding."""

from pathlib import Path
import re
from decimal import Decimal
from collections.abc import Iterator

import duckdb
from hypothesis import given, settings, strategies as st
from jinja2 import Environment
import pytest

ROOT = Path(__file__).resolve().parents[2]
MACROS = ROOT / "dbt/macros/utils"
MASK = (1 << 64) - 1
MULTIPLIER = 0xC6A4A7935BD1E995


def _reference_hash(value: str) -> int:
    """Independent integer implementation of the frozen UTF-8 hash contract."""
    data = value.encode("utf-8")
    state = 0xE17A1465 ^ ((len(data) * MULTIPLIER) & MASK)
    whole_bytes = len(data) // 8 * 8
    for offset in range(0, whole_bytes, 8):
        block = int.from_bytes(data[offset : offset + 8], "little")
        block = (block * MULTIPLIER) & MASK
        block ^= block >> 47
        block = (block * MULTIPLIER) & MASK
        state = ((state ^ block) * MULTIPLIER) & MASK
    if whole_bytes < len(data):
        state ^= int.from_bytes(data[whole_bytes:], "little")
        state = (state * MULTIPLIER) & MASK
    state ^= state >> 47
    state = (state * MULTIPLIER) & MASK
    return state ^ (state >> 47)


@pytest.fixture(scope="module")
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect() as connection:
        module = (
            Environment().from_string((MACROS / "stable_hash.sql").read_text()).module
        )
        connection.execute(module.install_stable_hash())
        yield connection


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", 11239542818895821884),
        ("EMP001", 12968045015873968436),
        ("INV_EMP_0001", 15561625596448271575),
        ("abcdefgh", 17294501757292903523),
        ("abcdefghijklmnop", 11618864109608327030),
        ("😀", 16835687959374608085),
        ("你好", 7787670556540481301),
        (None, 13787848793156543929),
    ],
)
def test_hash_matches_duckdb_113_golden_values(
    connection: duckdb.DuckDBPyConnection,
    value: str | None,
    expected: int,
) -> None:
    assert (
        connection.execute("SELECT planalign_hash(?)", [value]).fetchone()[0]
        == expected
    )


@settings(max_examples=75, deadline=None)
@given(value=st.text(max_size=256))
def test_hash_matches_reference_for_utf8(
    connection: duckdb.DuckDBPyConnection,
    value: str,
) -> None:
    actual = connection.execute("SELECT planalign_hash(?)", [value]).fetchone()[0]
    assert actual == _reference_hash(value)


def test_hash_vectorized_byte_boundaries_and_nulls(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    values = [
        None,
        "",
        "a\x00b",
        *["x" * n for n in (7, 8, 9, 15, 16, 17, 513)],
        "你" * 7,
        "😀" * 33,
    ]
    values += [f"EMP_{i:08d}|2025|TERMINATION|42" for i in range(2049)]
    actual = connection.execute(
        "SELECT planalign_hash(value), typeof(planalign_hash(value)) "
        "FROM unnest(?::VARCHAR[]) AS inputs(value)",
        [values],
    ).fetchall()
    expected = [
        13787848793156543929 if v is None else _reference_hash(v) for v in values
    ]
    assert actual == [(value, "UBIGINT") for value in expected]


@pytest.mark.parametrize(
    "expression", ["42", "-7", "12.30::DECIMAL(8,2)", "DATE '2025-01-01'", "true"]
)
def test_hash_preserves_varchar_conversion(
    connection: duckdb.DuckDBPyConnection, expression: str
) -> None:
    value, actual = connection.execute(
        f"SELECT ({expression})::VARCHAR, planalign_hash({expression})"
    ).fetchone()
    assert actual == _reference_hash(value)


def test_hash_join_nested_lambdas_and_repeat_install(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    module = Environment().from_string((MACROS / "stable_hash.sql").read_text()).module
    connection.execute(module.install_stable_hash())
    rows = connection.execute(
        "WITH inputs AS (SELECT unnest(['abc', '你好', '123456789']) AS value) "
        "SELECT a.value, list_transform([a.value], lambda item: planalign_hash(item || '|42')) "
        "FROM inputs a JOIN inputs b ON planalign_hash(a.value) = planalign_hash(b.value) "
        "ORDER BY a.value"
    ).fetchall()
    assert rows == [
        (v, [_reference_hash(v + "|42")]) for v in sorted(["abc", "你好", "123456789"])
    ]


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("100.005::DOUBLE", Decimal("100.00")),
        ("100.015::DOUBLE", Decimal("100.02")),
        ("-100.005::DOUBLE", Decimal("-100.00")),
        ("0.025::DOUBLE", Decimal("0.02")),
        ("100.005::DECIMAL(6,3)", Decimal("100.01")),
        ("'100.005'", Decimal("100.01")),
        ("NULL::DOUBLE", None),
    ],
)
def test_census_decimal_rounding_preserves_input_type(
    connection: duckdb.DuckDBPyConnection,
    expression: str,
    expected: Decimal | None,
) -> None:
    module = (
        Environment().from_string((MACROS / "stable_decimal.sql").read_text()).module
    )
    sql = module.stable_decimal(expression, 12, 2)
    assert connection.execute("SELECT " + sql).fetchone()[0] == expected


def test_escalation_percentage_preserves_half_even_rounding(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    module = (
        Environment().from_string((MACROS / "stable_decimal.sql").read_text()).module
    )
    sql = module.stable_decimal("0.15625::DOUBLE", 8, 4)
    assert connection.execute("SELECT " + sql).fetchone()[0] == Decimal("0.1562")


def test_simulation_sql_does_not_use_version_dependent_hash() -> None:
    violations = []
    for folder in (ROOT / "dbt/models", ROOT / "dbt/macros"):
        for path in folder.rglob("*.sql"):
            sql = re.sub(
                r"\{#.*?#\}|/\*.*?\*/|--[^\n]*", "", path.read_text(), flags=re.S
            )
            if re.search(r"\bhash\s*\(", sql, re.I):
                violations.append(str(path.relative_to(ROOT)))
    assert (
        not violations
    ), f"Use PLANALIGN_HASH for stable simulation behavior: {violations}"
