"""Exact two-engine parity: schemas plus row multisets (#470, research R11).

Ordinary ``EXCEPT`` collapses duplicates — baseline ``(x,x,y)`` vs candidate
``(x,y,y)`` pass a set comparison while being different tables. This
comparator checks ordered schema metadata first, then symmetric
``EXCEPT ALL`` over the projected values, and reports grouped multiplicity
diagnostics for divergences. Timestamp exemptions apply to values only; the
columns must still exist with equal schema.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import duckdb

AUTHORITATIVE_TABLES: Dict[str, Tuple[str, ...]] = {
    "fct_yearly_events": ("created_at",),
    "fct_workforce_snapshot": ("snapshot_created_at",),
}
DIAGNOSTIC_LIMIT = 20


@dataclass
class TableParity:
    table: str
    rows_a: int = 0
    rows_b: int = 0
    a_only_all: int = 0
    b_only_all: int = 0
    schema_mismatch: List[str] = field(default_factory=list)
    multiplicity_diffs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def identical(self) -> bool:
        return (
            self.error is None
            and not self.schema_mismatch
            and self.rows_a == self.rows_b
            and self.a_only_all == 0
            and self.b_only_all == 0
        )


def _schema(conn, db: str, table: str) -> List[Tuple[str, str, str]]:
    return conn.execute(
        f"SELECT column_name, data_type, is_nullable "
        f"FROM {db}.information_schema.columns "
        f"WHERE table_catalog = ? AND table_schema = 'main' AND table_name = ? "
        f"ORDER BY ordinal_position",
        [db, table],
    ).fetchall()


def compare_table_multisets(
    db_a: Path,
    db_b: Path,
    *,
    table: str,
    exclude_columns: Sequence[str] = (),
) -> TableParity:
    result = TableParity(table=table)
    conn = duckdb.connect()
    try:
        conn.execute(f"ATTACH '{db_a}' AS a (READ_ONLY)")
        conn.execute(f"ATTACH '{db_b}' AS b (READ_ONLY)")
        schema_a = _schema(conn, "a", table)
        schema_b = _schema(conn, "b", table)
        if not schema_a or not schema_b:
            result.error = f"table missing (a={bool(schema_a)}, b={bool(schema_b)})"
            return result
        if schema_a != schema_b:
            for col_a, col_b in zip(schema_a, schema_b):
                if col_a != col_b:
                    result.schema_mismatch.append(f"{col_a} != {col_b}")
            extra = abs(len(schema_a) - len(schema_b))
            if extra:
                result.schema_mismatch.append(f"column count differs by {extra}")
            return result

        columns = [c[0] for c in schema_a if c[0] not in set(exclude_columns)]
        projection = ", ".join(f'"{c}"' for c in columns)
        result.rows_a = conn.execute(f"SELECT COUNT(*) FROM a.main.{table}").fetchone()[
            0
        ]
        result.rows_b = conn.execute(f"SELECT COUNT(*) FROM b.main.{table}").fetchone()[
            0
        ]
        result.a_only_all = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {projection} FROM a.main.{table} "
            f"EXCEPT ALL SELECT {projection} FROM b.main.{table})"
        ).fetchone()[0]
        result.b_only_all = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT {projection} FROM b.main.{table} "
            f"EXCEPT ALL SELECT {projection} FROM a.main.{table})"
        ).fetchone()[0]

        if result.a_only_all or result.b_only_all:
            rows = conn.execute(
                f"WITH ga AS (SELECT {projection}, COUNT(*) AS a_count "
                f"FROM a.main.{table} GROUP BY ALL), "
                f"gb AS (SELECT {projection}, COUNT(*) AS b_count "
                f"FROM b.main.{table} GROUP BY ALL) "
                f"SELECT {', '.join('COALESCE(ga.' + chr(34) + c + chr(34) + ', gb.' + chr(34) + c + chr(34) + ') AS ' + chr(34) + c + chr(34) for c in columns)}, "
                f"COALESCE(ga.a_count, 0) AS a_count, COALESCE(gb.b_count, 0) AS b_count "
                f"FROM ga FULL JOIN gb USING ({projection}) "
                f"WHERE COALESCE(ga.a_count, 0) <> COALESCE(gb.b_count, 0) "
                f"LIMIT {DIAGNOSTIC_LIMIT}"
            ).fetchall()
            for row in rows:
                values = dict(zip(columns, row[: len(columns)]))
                result.multiplicity_diffs.append(
                    {
                        "row": {k: str(v) for k, v in values.items()},
                        "baseline_count": row[len(columns)],
                        "candidate_count": row[len(columns) + 1],
                        "delta": row[len(columns)] - row[len(columns) + 1],
                    }
                )
        return result
    finally:
        conn.close()


@dataclass
class ParityReport:
    baseline_database: str
    candidate_database: str
    input_fingerprint: str = ""
    tables: List[TableParity] = field(default_factory=list)
    unexpected_fallback_count: int = 0
    error: Optional[str] = None

    @property
    def verdict(self) -> str:
        if self.error:
            return "ERROR"
        if (
            all(t.identical for t in self.tables)
            and self.unexpected_fallback_count == 0
        ):
            return "IDENTICAL"
        return "DIVERGED"

    def to_json(self) -> str:
        payload = {
            "schema_version": 1,
            "input_fingerprint": self.input_fingerprint,
            "baseline_engine": "dbt",
            "candidate_engine": "compiled",
            "verdict": self.verdict,
            "baseline_database": self.baseline_database,
            "candidate_database": self.candidate_database,
            "unexpected_fallback_count": self.unexpected_fallback_count,
            "error": self.error,
            "tables": [
                {
                    "name": table.table,
                    "schema_equal": not table.schema_mismatch,
                    "rows_baseline": table.rows_a,
                    "rows_candidate": table.rows_b,
                    "baseline_only_all": table.a_only_all,
                    "candidate_only_all": table.b_only_all,
                    "schema_mismatch": table.schema_mismatch,
                    "multiplicity_samples": table.multiplicity_diffs,
                    "error": table.error,
                    "identical": table.identical,
                }
                for table in self.tables
            ],
        }
        return json.dumps(payload, indent=2)


def run_parity(
    *,
    start_year: int,
    end_year: int,
    config_path: Path,
    census_path: Path,
    seed: Optional[int] = None,
    workdir: Optional[Path] = None,
) -> ParityReport:
    """Run the identical scenario under both engines in fresh isolated DBs."""
    import os
    import tempfile

    from planalign_orchestrator import create_orchestrator
    from planalign_orchestrator.config import load_simulation_config

    shared_dev = Path(__file__).resolve().parents[2] / "dbt" / "simulation.duckdb"
    root = Path(workdir or tempfile.mkdtemp(prefix="parity-"))
    root.mkdir(parents=True, exist_ok=True)

    census = Path(census_path)
    if census.suffix == ".csv":
        parquet = root / "census.parquet"
        with duckdb.connect() as conn:
            conn.read_csv(str(census)).write_parquet(str(parquet))
        census = parquet

    def _run(engine: str, db_path: Path):
        if db_path.resolve() == shared_dev.resolve():
            raise RuntimeError("parity refuses to target the shared dev database")
        config = load_simulation_config(config_path, env_overrides=False)
        config.setup["census_parquet_path"] = str(census)
        config.simulation.start_year = start_year
        config.simulation.end_year = end_year
        if seed is not None:
            config.simulation.random_seed = seed
        config.optimization.execution_engine = engine
        previous = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(db_path)
        try:
            orchestrator = create_orchestrator(config, db_path=db_path, threads=1)
            orchestrator.execute_multi_year_simulation(
                start_year=start_year, end_year=end_year
            )
        finally:
            if previous is None:
                os.environ.pop("DATABASE_PATH", None)
            else:
                os.environ["DATABASE_PATH"] = previous
        return orchestrator

    baseline_db = root / "baseline_dbt.duckdb"
    candidate_db = root / "candidate_compiled.duckdb"
    input_fingerprint = _input_fingerprint(
        config_path=Path(config_path),
        census_path=Path(census_path),
        seed=seed,
        start_year=start_year,
        end_year=end_year,
    )
    shared_before = _file_digest_if_present(shared_dev)
    try:
        _run("dbt", baseline_db)
        candidate = _run("compiled", candidate_db)
    except Exception as exc:  # surfaced as ERROR verdict with context
        report = ParityReport(
            baseline_database=str(baseline_db),
            candidate_database=str(candidate_db),
            input_fingerprint=input_fingerprint,
        )
        report.error = f"{type(exc).__name__}: {exc}"
        return report

    if _file_digest_if_present(shared_dev) != shared_before:
        return ParityReport(
            baseline_database=str(baseline_db),
            candidate_database=str(candidate_db),
            input_fingerprint=input_fingerprint,
            error="shared development database changed during parity run",
        )

    record_log = getattr(candidate.dbt_runner, "record_log", None)
    unexpected = record_log.fallback_count if record_log is not None else 0
    report = compare_databases(
        baseline_db, candidate_db, unexpected_fallbacks=unexpected
    )
    report.input_fingerprint = input_fingerprint
    return report


def compare_databases(
    baseline: Path, candidate: Path, *, unexpected_fallbacks: int = 0
) -> ParityReport:
    report = ParityReport(
        baseline_database=str(baseline),
        candidate_database=str(candidate),
        unexpected_fallback_count=unexpected_fallbacks,
    )
    for table, exempt in AUTHORITATIVE_TABLES.items():
        report.tables.append(
            compare_table_multisets(
                baseline, candidate, table=table, exclude_columns=exempt
            )
        )
    return report


def _file_digest_if_present(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_fingerprint(
    *,
    config_path: Path,
    census_path: Path,
    seed: Optional[int],
    start_year: int,
    end_year: int,
) -> str:
    payload = {
        "config": _file_digest_if_present(config_path),
        "census": _file_digest_if_present(census_path),
        "seed": seed,
        "start_year": start_year,
        "end_year": end_year,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
