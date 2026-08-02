#!/usr/bin/env python3
"""Run the Feature 132 all-marts parity and determinism gate."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import duckdb

from planalign_orchestrator.change_validation import compare_marts, discover_marts

EXCLUDED_COLUMNS = ("created_at", "snapshot_created_at", "cache_built_at")
EXCLUDED_TABLES = ("run_metadata", "run_execution_metadata")
EXPECTED_CENSUS_ROWS = 60_040
EXPECTED_HORIZON_YEARS = 5


@dataclass(frozen=True)
class DatabaseShape:
    census_rows: int
    horizon_years: int


def _database_shape(path: Path) -> DatabaseShape:
    with duckdb.connect(str(path), read_only=True) as connection:
        census_rows = connection.execute(
            "SELECT COUNT(*) FROM stg_census_data"
        ).fetchone()[0]
        horizon_years = connection.execute(
            "SELECT COUNT(DISTINCT simulation_year) FROM fct_workforce_snapshot"
        ).fetchone()[0]
    return DatabaseShape(int(census_rows), int(horizon_years))


def _validate_database(path: Path) -> DatabaseShape:
    if not path.is_file():
        raise ValueError(f"database does not exist: {path}")
    shape = _database_shape(path)
    expected = DatabaseShape(EXPECTED_CENSUS_ROWS, EXPECTED_HORIZON_YEARS)
    if shape != expected:
        raise ValueError(f"{path} has workload {shape}; expected {expected}")
    return shape


def _columns(path: Path, relation: str) -> set[str]:
    with duckdb.connect(str(path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [relation],
        ).fetchall()
    return {str(row[0]) for row in rows}


def _applied_exclusions(
    baseline: Path, candidate: Path, marts: Sequence[str]
) -> dict[str, list[str]]:
    return {
        mart: sorted(
            set(EXCLUDED_COLUMNS) & _columns(baseline, mart) & _columns(candidate, mart)
        )
        for mart in marts
    }


def _is_clean(result: tuple[object, object]) -> bool:
    return result in ((0, 0), ("absent", "absent"))


def _assert_coverage(
    enumerated: Sequence[str], compared: dict[str, tuple[object, object]]
) -> None:
    if set(enumerated) != set(compared):
        missing = sorted(set(enumerated) - set(compared))
        unexpected = sorted(set(compared) - set(enumerated))
        raise ValueError(
            f"mart coverage mismatch: missing={missing}, unexpected={unexpected}"
        )


def _render_report(
    marts: Sequence[str],
    parity: dict[str, tuple[object, object]],
    determinism: dict[str, tuple[object, object]],
    exclusions: dict[str, list[str]],
    shape: DatabaseShape,
) -> str:
    clean = all(_is_clean(value) for value in [*parity.values(), *determinism.values()])
    lines = [
        "# All-marts parity gate",
        "",
        f"- Result: **{'PASS' if clean else 'FAIL'}**",
        "- Mart set source: `dbt ls --select marts --resource-type model --output name`",
        f"- Enumerated marts: {len(marts)}",
        f"- Census rows: {shape.census_rows:,}",
        f"- Horizon: {shape.horizon_years} years",
        f"- Excluded tables: {', '.join(f'`{name}`' for name in EXCLUDED_TABLES)}",
        "",
        "| Mart | Baseline − candidate | Candidate − baseline | "
        "Candidate − rerun | Rerun − candidate | Excluded columns |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for mart in marts:
        forward, reverse = parity[mart]
        deterministic_forward, deterministic_reverse = determinism[mart]
        excluded = ", ".join(f"`{name}`" for name in exclusions[mart]) or "—"
        lines.append(
            f"| `{mart}` | {forward} | {reverse} | {deterministic_forward} | "
            f"{deterministic_reverse} | {excluded} |"
        )
    lines.extend(
        [
            "",
            "Compared mart set exactly equals the runtime-enumerated mart set.",
            "Audit exclusions are shown per mart; no other columns were omitted.",
            "",
        ]
    )
    return "\n".join(lines)


def run_gate(baseline: Path, candidate: Path, determinism: Path, output: Path) -> bool:
    shapes = [_validate_database(path) for path in (baseline, candidate, determinism)]
    if len(set(shapes)) != 1:
        raise ValueError(f"database workload mismatch: {shapes}")
    marts = discover_marts(Path(__file__).resolve().parents[1] / "dbt")
    if not marts:
        raise ValueError("dbt ls enumerated no marts")
    parity = compare_marts(baseline, candidate, marts, EXCLUDED_COLUMNS)
    determinism_result = compare_marts(candidate, determinism, marts, EXCLUDED_COLUMNS)
    _assert_coverage(marts, parity)
    _assert_coverage(marts, determinism_result)
    report = _render_report(
        marts,
        parity,
        determinism_result,
        _applied_exclusions(baseline, candidate, marts),
        shapes[0],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report)
    return all(
        _is_clean(value) for value in [*parity.values(), *determinism_result.values()]
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--determinism", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        clean = run_gate(args.baseline, args.candidate, args.determinism, args.out)
    except (duckdb.Error, OSError, ValueError) as error:
        print(f"parity gate failed: {error}", file=sys.stderr)
        return 2
    print(f"parity report: {args.out} ({'PASS' if clean else 'FAIL'})")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
