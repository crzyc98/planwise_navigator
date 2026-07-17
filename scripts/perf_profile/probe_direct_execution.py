"""Direct-execution probe (FR-005): EVENT_GENERATION via compiled SQL vs dbt.

Method: run a normal dev-census year-2025 simulation in an isolated DB with
the invocation recorder attached. Immediately before the first
EVENT_GENERATION dbt invocation the DB file is copied (state includes the
orchestrator's Python-side enrollment prep, so both paths start identically);
at POST_STAGE the DB is copied again as the reference result. The direct path
then replays dbt's own executed-SQL artifacts (``target/run``, snapshotted per
invocation) against the first copy through the duckdb client — identical SQL,
no subprocess/parse cost — and every produced table is compared against the
reference copy (row count + order-insensitive row-hash checksum).

The copies keep the filename stem ``probe_std`` because compiled SQL
fully qualifies relations with the DuckDB database alias derived from it.

Usage:
    python -m scripts.perf_profile.probe_direct_execution --year 2025
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb

from .dbt_timing import InvocationRecorder, attach_stage_tracking
from .profile_config import (
    CensusSize,
    DB_DIR,
    DEV_CENSUS_PARQUET,
    ROOT,
    SAMPLES_DIR,
    ProbeResult,
)
from .run_matrix import _load_config, database_environment

PROBE_DIR = DB_DIR / "probe"
STD_DB = PROBE_DIR / "probe_std.duckdb"
PRE_EG_DB = PROBE_DIR / "pre_eg" / "probe_std.duckdb"
POST_EG_DB = PROBE_DIR / "post_eg" / "probe_std.duckdb"
RUN_SQL_DIR = PROBE_DIR / "run_sql"
EG_STAGE = "event_generation"


class ProbeCapture:
    """Copies DB state around the EVENT_GENERATION stage during a live run."""

    def __init__(self, orchestrator, recorder: InvocationRecorder) -> None:
        self._orchestrator = orchestrator
        self._recorder = recorder
        self.pre_copied = False

    def before_invocation(self, command_args: List[str]) -> None:
        if self.pre_copied or self._recorder.current_stage != EG_STAGE:
            return
        self._copy(PRE_EG_DB)
        self.pre_copied = True

    def post_stage_hook(self, context: dict) -> None:
        stage = getattr(context.get("stage"), "value", None)
        if stage == EG_STAGE:
            self._copy(POST_EG_DB)

    def _copy(self, dest: Path) -> None:
        try:
            self._orchestrator.db_manager.close_all()
        except Exception as exc:  # non-fatal: file copy of a closed DB is the goal
            print(f"[probe] warning: close_all failed before copy: {exc}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STD_DB, dest)
        print(f"[probe] captured {dest.relative_to(ROOT)}")


def run_standard(year: int) -> List:
    """Run the standard path, capturing copies + per-invocation run SQL."""
    from planalign_orchestrator import create_orchestrator
    from planalign_orchestrator.pipeline.hooks import Hook, HookType

    if PROBE_DIR.exists():
        shutil.rmtree(PROBE_DIR)
    PROBE_DIR.mkdir(parents=True)
    RUN_SQL_DIR.mkdir(parents=True)

    config = _load_config(DEV_CENSUS_PARQUET, (year, year))
    with database_environment(STD_DB):
        orchestrator = create_orchestrator(config, db_path=STD_DB, threads=1)
        recorder = InvocationRecorder(
            orchestrator.dbt_runner, snapshot_run_sql_to=RUN_SQL_DIR
        )
        attach_stage_tracking(orchestrator, recorder)
        capture = ProbeCapture(orchestrator, recorder)
        recorder._before_invocation = capture.before_invocation
        orchestrator.hook_manager.register_hook(
            Hook(
                hook_type=HookType.POST_STAGE,
                callback=capture.post_stage_hook,
                name="probe_post_eg_copy",
            )
        )
        orchestrator.execute_multi_year_simulation(start_year=year, end_year=year)
        recorder.unwrap()

    if not capture.pre_copied or not POST_EG_DB.exists():
        raise SystemExit("probe: failed to capture pre/post EVENT_GENERATION copies")
    return recorder.invocations


def _load_manifest_nodes() -> Dict[str, dict]:
    manifest = json.loads((ROOT / "dbt" / "target" / "manifest.json").read_text())
    return manifest["nodes"]


def collect_eg_nodes(invocations) -> List[Tuple[int, str]]:
    """(invocation seq, node unique_id) for EVENT_GENERATION model nodes, in order."""
    ordered: List[Tuple[int, str]] = []
    for invocation in invocations:
        if invocation.stage != EG_STAGE:
            continue
        for model in invocation.models:
            if model.unique_id.startswith("model.") and model.status == "success":
                ordered.append((invocation.seq, model.unique_id))
    if not ordered:
        raise SystemExit("probe: no EVENT_GENERATION model nodes recorded")
    return ordered


def run_direct(nodes: List[Tuple[int, str]], manifest_nodes: Dict[str, dict]) -> float:
    """Replay dbt's executed SQL against the pre-EG copy; return wall seconds.

    dbt's run artifacts create ``<alias>__dbt_tmp`` relations; the swap into
    the real relation happens through adapter calls that are not in the file.
    In the probe the EG relations do not pre-exist (fresh single-year DB), so
    rewriting the tmp name to the real name executes the identical SELECT with
    the identical create-table cost and no extra copy step.
    """
    conn = duckdb.connect(str(PRE_EG_DB))
    start = time.perf_counter()
    try:
        for seq, unique_id in nodes:
            node = manifest_nodes[unique_id]
            sql_path = (
                RUN_SQL_DIR
                / f"invocation_{seq:03d}"
                / node["package_name"]
                / node["original_file_path"]
            )
            if not sql_path.exists():
                raise SystemExit(f"probe: missing run SQL for {unique_id}: {sql_path}")
            alias = node.get("alias") or node["name"]
            statements = sql_path.read_text().replace(f"{alias}__dbt_tmp", alias)
            _drop_existing(conn, alias)
            conn.execute(statements)
    finally:
        wall = time.perf_counter() - start
        conn.close()
    return wall


def _drop_existing(conn: duckdb.DuckDBPyConnection, alias: str) -> None:
    """Replicate dbt's pre-create drop (an adapter call not in the artifact)."""
    row = conn.execute(
        "SELECT table_type FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?",
        [alias],
    ).fetchone()
    if row is None:
        return
    kind = "VIEW" if row[0] == "VIEW" else "TABLE"
    conn.execute(f'DROP {kind} IF EXISTS main."{alias}"')


def _table_signature(db: Path, table: str) -> Optional[Tuple[int, int]]:
    """Row count + order-insensitive row hash over non-TIMESTAMP columns.

    TIMESTAMP columns are execution-time audit stamps (``created_at``) in this
    schema — behavioral dates are DATE-typed — so they necessarily differ
    between two executions and are excluded from the equivalence checksum.
    """
    with duckdb.connect(str(db), read_only=True) as conn:
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "AND data_type NOT LIKE 'TIMESTAMP%' ORDER BY ordinal_position",
            [table],
        ).fetchall()
        if not columns:
            return None
        row_expr = ", ".join(f'"{name}"' for (name,) in columns)
        count = conn.sql(f'SELECT COUNT(*) FROM main."{table}"').fetchone()[0]
        checksum = conn.sql(
            f'SELECT COALESCE(sum(hash(ROW({row_expr}))), 0) FROM main."{table}"'
        ).fetchone()[0]
        return count, int(checksum) if checksum is not None else 0


def compare(nodes: List[Tuple[int, str]], manifest_nodes: Dict[str, dict]) -> List[str]:
    diffs: List[str] = []
    seen: set[str] = set()
    for _, unique_id in nodes:
        node = manifest_nodes[unique_id]
        if node.get("config", {}).get("materialized") == "view":
            continue
        alias = node.get("alias") or node["name"]
        if alias in seen:
            continue
        seen.add(alias)
        direct = _table_signature(PRE_EG_DB, alias)
        reference = _table_signature(POST_EG_DB, alias)
        if direct is None or reference is None:
            diffs.append(
                f"{alias}: missing table (direct={direct is not None}, "
                f"reference={reference is not None})"
            )
        elif direct != reference:
            diffs.append(
                f"{alias}: rows {direct[0]} vs {reference[0]}, "
                f"checksum {'match' if direct[1] == reference[1] else 'MISMATCH'}"
            )
    return diffs


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025)
    args = parser.parse_args(argv)

    print("[probe] running standard path (dev census, single year)...", flush=True)
    invocations = run_standard(args.year)
    eg_invocations = [i for i in invocations if i.stage == EG_STAGE]
    standard_wall = sum(i.wall_s for i in eg_invocations)
    print(
        f"[probe] standard EVENT_GENERATION: {standard_wall:.1f}s over "
        f"{len(eg_invocations)} dbt invocation(s)"
    )

    manifest_nodes = _load_manifest_nodes()
    nodes = collect_eg_nodes(invocations)
    print(f"[probe] replaying {len(nodes)} node executions directly...", flush=True)
    direct_wall = run_direct(nodes, manifest_nodes)
    print(f"[probe] direct EVENT_GENERATION: {direct_wall:.1f}s")

    diffs = compare(nodes, manifest_nodes)
    result = ProbeResult(
        stage=EG_STAGE,
        year=args.year,
        census_size=CensusSize.DEV,
        standard_wall_s=standard_wall,
        direct_wall_s=direct_wall,
        equivalent=not diffs,
        diffs=diffs,
        nodes_executed=len(nodes),
    )
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    (SAMPLES_DIR / "probe.json").write_text(result.model_dump_json(indent=2))
    verdict = "EQUIVALENT" if result.equivalent else f"DIVERGED ({len(diffs)} diffs)"
    print(f"[probe] speedup {result.speedup:.1f}x, results {verdict} -> probe.json")
    return 0 if result.equivalent else 3


if __name__ == "__main__":
    sys.exit(main())
