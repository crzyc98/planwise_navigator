"""Change-validation campaign — prove an uncommitted change is output-neutral.

Powers ``planalign validate-change``. Given the current working tree (candidate)
and ``HEAD`` (baseline, produced by stashing the working-tree change), it builds
both into **isolated** DuckDB files and compares them so a behavioral change can be
proven safe *before* it ships:

- **all-mart parity** — bidirectional, duplicate-preserving ``EXCEPT ALL`` over every
  ``fct_*``/``dim_*`` mart (audit-timestamps excluded);
- **invocation count** — the dbt command count each run recorded in
  ``run_execution_metadata`` (baseline vs candidate);
- **peak RSS + wall time** — single-run, directional;
- **shared-DB guard** — asserts ``dbt/simulation.duckdb`` is byte-unchanged.

Design notes:
- Baseline is built by ``git stash``-ing the tracked working-tree change, so the
  subprocess ``planalign simulate`` re-imports the committed code (this is why an
  editable install still measures the right thing). The stash is always restored.
- Every build runs in a fresh subprocess against an isolated ``--database``; the
  shared dev DB is never built into.
- Validating at a **large (≈60k) census** is what catches scale-dependent bugs that
  a dev-census check misses (e.g. feature 121 Tier C). The campaign warns loudly
  when the census is small.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import duckdb

from planalign_orchestrator.state_pipeline_validation import (
    CharacterizationRecord,
    ExclusionEntry,
    FileGuard,
    load_exclusion_manifest,
    verify_characterization_database,
)

DEFAULT_EXCLUDED: Tuple[str, ...] = ("created_at", "snapshot_created_at")
AUDIT_TABLES = frozenset({"run_metadata", "run_execution_metadata"})
SMALL_CENSUS_THRESHOLD = 20_000  # below this, warn that the scale gate wasn't exercised
DEFAULT_HORIZON = "2025-2027"
Logger = Callable[[str], None]


# --------------------------------------------------------------------------- #
# Mart parity (canonical implementation; tests/helpers re-export from here)
# --------------------------------------------------------------------------- #
def discover_marts(dbt_dir: str | Path) -> List[str]:
    """Enumerate ``fct_*``/``dim_*`` mart model names via ``dbt ls`` (never hardcoded)."""
    out = subprocess.run(
        [
            "dbt",
            "ls",
            "--select",
            "marts",
            "--resource-type",
            "model",
            "--output",
            "name",
        ],
        cwd=str(dbt_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    names = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    return [
        n
        for n in names
        if (n.startswith("fct_") or n.startswith("dim_")) and n not in AUDIT_TABLES
    ]


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True)
class RelationMetrics:
    row_count: int
    distinct_row_count: int
    duplicate_groups: int
    extra_duplicate_rows: int


@dataclass
class MartComparison:
    relation: str
    status: str
    baseline_schema: List[ColumnSchema] = field(default_factory=list)
    candidate_schema: List[ColumnSchema] = field(default_factory=list)
    compared_schema: List[ColumnSchema] = field(default_factory=list)
    baseline_minus_candidate: int = 0
    candidate_minus_baseline: int = 0
    baseline_metrics: Optional[RelationMetrics] = None
    candidate_metrics: Optional[RelationMetrics] = None
    baseline_group_counts: Dict[str, int] = field(default_factory=dict)
    candidate_group_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status in {"compared", "not_built_in_either"}


def _schema(
    con: duckdb.DuckDBPyConnection, catalog: str, table: str
) -> List[ColumnSchema]:
    rows = con.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_name = ? ORDER BY ordinal_position",
        [catalog, table],
    ).fetchall()
    return [
        ColumnSchema(name=row[0], data_type=row[1], nullable=row[2] == "YES")
        for row in rows
    ]


def _columns(con: duckdb.DuckDBPyConnection, catalog: str, table: str) -> List[str]:
    return [column.name for column in _schema(con, catalog, table)]


def _quoted_columns(columns: Sequence[ColumnSchema]) -> str:
    return ", ".join(
        f'"{column.name.replace(chr(34), chr(34) * 2)}"' for column in columns
    )


def _scalar_int(con: duckdb.DuckDBPyConnection, query: str) -> int:
    row = con.execute(query).fetchone()
    if row is None:
        raise RuntimeError("aggregate query returned no row")
    return int(row[0])


def _relation_metrics(
    con: duckdb.DuckDBPyConnection,
    catalog: str,
    table: str,
    columns: Sequence[ColumnSchema],
) -> RelationMetrics:
    projection = _quoted_columns(columns)
    if not projection:
        raise ValueError(f"{table} has no comparable columns")
    distinct_count = _scalar_int(
        con,
        f'SELECT COUNT(*) FROM (SELECT DISTINCT {projection} FROM {catalog}."{table}")',
    )
    total = _scalar_int(con, f'SELECT COUNT(*) FROM {catalog}."{table}"')
    duplicate_groups = _scalar_int(
        con,
        f"SELECT COUNT(*) FROM (SELECT {projection}, COUNT(*) AS multiplicity "
        f'FROM {catalog}."{table}" GROUP BY {projection} HAVING COUNT(*) > 1)',
    )
    return RelationMetrics(
        row_count=total,
        distinct_row_count=distinct_count,
        duplicate_groups=duplicate_groups,
        extra_duplicate_rows=total - distinct_count,
    )


def _group_counts(
    con: duckdb.DuckDBPyConnection,
    catalog: str,
    relation: str,
    columns: Sequence[ColumnSchema],
) -> Dict[str, int]:
    names = {column.name for column in columns}
    if relation == "fct_yearly_events":
        group_columns = (
            "scenario_id",
            "plan_design_id",
            "simulation_year",
            "event_type",
        )
    elif relation == "fct_workforce_snapshot" and "employment_status" in names:
        group_columns = (
            "scenario_id",
            "plan_design_id",
            "simulation_year",
            "employment_status",
        )
    else:
        return {}
    if not set(group_columns).issubset(names):
        return {}
    projection = ", ".join(f'"{name}"' for name in group_columns)
    rows = con.execute(
        f'SELECT {projection}, COUNT(*) FROM {catalog}."{relation}" '
        f"GROUP BY {projection} ORDER BY {projection}"
    ).fetchall()
    return {
        json.dumps(row[:-1], default=str, separators=(",", ":")): row[-1]
        for row in rows
    }


def _relation_exclusions(
    relation: str, exclusions: Sequence[ExclusionEntry]
) -> set[str]:
    return {entry.column for entry in exclusions if entry.relation == relation}


def compare_marts_detailed(
    baseline_db: str | Path,
    candidate_db: str | Path,
    marts: Sequence[str],
    exclusions: Sequence[ExclusionEntry] = (),
) -> Dict[str, MartComparison]:
    """Compare every mart with strict schema and duplicate-preserving semantics."""
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"ATTACH '{baseline_db}' AS base (READ_ONLY)")
        con.execute(f"ATTACH '{candidate_db}' AS cand (READ_ONLY)")
        results: Dict[str, MartComparison] = {}
        for relation in marts:
            baseline_schema = _schema(con, "base", relation)
            candidate_schema = _schema(con, "cand", relation)
            if not baseline_schema and not candidate_schema:
                results[relation] = MartComparison(
                    relation=relation, status="not_built_in_either"
                )
                continue
            if not baseline_schema or not candidate_schema:
                status = (
                    "missing_baseline" if not baseline_schema else "missing_candidate"
                )
                results[relation] = MartComparison(
                    relation=relation,
                    status=status,
                    baseline_schema=baseline_schema,
                    candidate_schema=candidate_schema,
                )
                continue
            excluded = _relation_exclusions(relation, exclusions)
            baseline_names = {column.name for column in baseline_schema}
            candidate_names = {column.name for column in candidate_schema}
            unknown = excluded - (baseline_names & candidate_names)
            if unknown:
                raise ValueError(
                    f"{relation} exclusion references unknown column(s): {sorted(unknown)}"
                )
            compared_baseline = [
                column for column in baseline_schema if column.name not in excluded
            ]
            compared_candidate = [
                column for column in candidate_schema if column.name not in excluded
            ]
            if compared_baseline != compared_candidate:
                results[relation] = MartComparison(
                    relation=relation,
                    status="schema_mismatch",
                    baseline_schema=baseline_schema,
                    candidate_schema=candidate_schema,
                    compared_schema=compared_baseline,
                )
                continue
            projection = _quoted_columns(compared_baseline)
            baseline_minus = _scalar_int(
                con,
                f'SELECT COUNT(*) FROM (SELECT {projection} FROM base."{relation}" '
                f'EXCEPT ALL SELECT {projection} FROM cand."{relation}")',
            )
            candidate_minus = _scalar_int(
                con,
                f'SELECT COUNT(*) FROM (SELECT {projection} FROM cand."{relation}" '
                f'EXCEPT ALL SELECT {projection} FROM base."{relation}")',
            )
            status = (
                "compared"
                if baseline_minus == candidate_minus == 0
                else "content_mismatch"
            )
            results[relation] = MartComparison(
                relation=relation,
                status=status,
                baseline_schema=baseline_schema,
                candidate_schema=candidate_schema,
                compared_schema=compared_baseline,
                baseline_minus_candidate=baseline_minus,
                candidate_minus_baseline=candidate_minus,
                baseline_metrics=_relation_metrics(
                    con, "base", relation, compared_baseline
                ),
                candidate_metrics=_relation_metrics(
                    con, "cand", relation, compared_candidate
                ),
                baseline_group_counts=_group_counts(
                    con, "base", relation, compared_baseline
                ),
                candidate_group_counts=_group_counts(
                    con, "cand", relation, compared_candidate
                ),
            )
        return results
    finally:
        con.close()


def compare_marts(
    baseline_db: str | Path,
    candidate_db: str | Path,
    marts: Sequence[str],
    excluded: Sequence[str] = DEFAULT_EXCLUDED,
) -> Dict[str, Tuple[object, object]]:
    """Return ``{mart: (baseline-candidate, candidate-baseline)}`` row-diff counts.

    A mart absent from one or both DBs yields the ``("absent", ...)`` sentinel so the
    caller can distinguish "not built by this workflow" from a real difference.
    """
    inspector = duckdb.connect(database=":memory:")
    try:
        inspector.execute(f"ATTACH '{baseline_db}' AS base (READ_ONLY)")
        inspector.execute(f"ATTACH '{candidate_db}' AS cand (READ_ONLY)")
        scoped = [
            ExclusionEntry(
                relation=relation,
                column=column,
                reason="legacy global exclusion",
            )
            for relation in marts
            for column in excluded
            if column in set(_columns(inspector, "base", relation))
            and column in set(_columns(inspector, "cand", relation))
        ]
    finally:
        inspector.close()
    detailed = compare_marts_detailed(baseline_db, candidate_db, marts, scoped)
    results: Dict[str, Tuple[object, object]] = {}
    for relation, result in detailed.items():
        if result.status == "not_built_in_either":
            results[relation] = ("absent", "absent")
        elif result.status == "missing_baseline":
            results[relation] = ("absent", "present")
        elif result.status == "missing_candidate":
            results[relation] = ("present", "absent")
        elif result.status == "schema_mismatch":
            results[relation] = ("schema-mismatch", "schema-mismatch")
        else:
            results[relation] = (
                result.baseline_minus_candidate,
                result.candidate_minus_baseline,
            )
    return results


def assert_all_marts_identical(
    baseline_db: str | Path,
    candidate_db: str | Path,
    marts: Sequence[str],
    excluded: Sequence[str] = DEFAULT_EXCLUDED,
) -> Dict[str, Tuple[object, object]]:
    """Assert every present mart is byte-identical (0/0 both directions)."""
    results = compare_marts(baseline_db, candidate_db, marts, excluded)
    diffs = {
        m: v
        for m, v in results.items()
        if v
        not in (
            (0, 0),
            ("absent", "absent"),
            ("no-shared-columns", "no-shared-columns"),
        )
    }
    assert not diffs, (
        "All-mart parity FAILED. mart -> (baseline-candidate, candidate-baseline): "
        f"{diffs}"
    )
    return results


# --------------------------------------------------------------------------- #
# Invocation schedule (canonical; tests/helpers re-export)
# --------------------------------------------------------------------------- #
def read_latest_schedule(db_path: str | Path) -> Optional[Dict[str, object]]:
    """Return the newest run's ``{invocation_count, steps}``, or None if unrecorded."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        exists = _scalar_int(
            con,
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'run_execution_metadata'",
        )
        if not exists:
            return None
        row = con.execute(
            "SELECT invocation_count, schedule_steps FROM run_execution_metadata "
            "ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    count, steps_json = row
    steps = json.loads(steps_json) if steps_json else []
    return {"invocation_count": count, "steps": steps}


def _first_index(steps: List[dict], needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in (step.get("command") or ""):
            return i
    return -1


def assert_invocation_count_at_most(db_path: str | Path, ceiling: int) -> Optional[int]:
    schedule = read_latest_schedule(db_path)
    if schedule is None:
        return None
    count = schedule["invocation_count"]
    if not isinstance(count, int):
        raise TypeError("recorded invocation_count is not an integer")
    assert count <= ceiling, f"invocation_count {count} exceeds ceiling {ceiling}"
    return count


def assert_accumulator_before_snapshot(steps: List[dict]) -> None:
    events_idx = _first_index(steps, "fct_yearly_events")
    snapshot_idx = _first_index(steps, "fct_workforce_snapshot")
    assert events_idx != -1, "fct_yearly_events not found in schedule"
    assert snapshot_idx != -1, "fct_workforce_snapshot not found in schedule"
    assert events_idx < snapshot_idx, (
        "event build must precede snapshot build "
        f"(fct_yearly_events at {events_idx}, fct_workforce_snapshot at {snapshot_idx})"
    )


# --------------------------------------------------------------------------- #
# Campaign
# --------------------------------------------------------------------------- #
@dataclass
class BuildMetrics:
    ok: bool
    wall_s: float
    peak_rss_mb: Optional[float]
    invocation_count: Optional[int]
    db_path: Path
    error: Optional[str] = None


@dataclass
class ScaleResult:
    census_label: str
    census_rows: Optional[int]
    baseline: BuildMetrics
    candidate: BuildMetrics
    mart_diffs: Dict[str, Tuple[object, object]] = field(default_factory=dict)
    small_census_warning: bool = False

    @property
    def parity_ok(self) -> bool:
        offenders = {
            m: v
            for m, v in self.mart_diffs.items()
            if v
            not in (
                (0, 0),
                ("absent", "absent"),
                ("no-shared-columns", "no-shared-columns"),
            )
        }
        return self.baseline.ok and self.candidate.ok and not offenders

    @property
    def parity_offenders(self) -> Dict[str, Tuple[object, object]]:
        return {
            m: v
            for m, v in self.mart_diffs.items()
            if v
            not in (
                (0, 0),
                ("absent", "absent"),
                ("no-shared-columns", "no-shared-columns"),
            )
        }

    @property
    def marts_compared(self) -> int:
        return sum(1 for v in self.mart_diffs.values() if isinstance(v[0], int))


@dataclass
class ValidationResult:
    scales: List[ScaleResult]
    shared_db_sha_before: Optional[str]
    shared_db_sha_after: Optional[str]

    @property
    def shared_db_unchanged(self) -> bool:
        return self.shared_db_sha_before == self.shared_db_sha_after

    @property
    def passed(self) -> bool:
        return (
            bool(self.scales)
            and all(s.parity_ok for s in self.scales)
            and self.shared_db_unchanged
        )


@dataclass
class FrozenValidationResult:
    baseline_id: str
    phase: str
    checkpoint: Optional[str]
    baseline_verified: bool
    comparisons: Dict[str, MartComparison]
    shared_db_before: FileGuard
    shared_db_after: FileGuard
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.baseline_verified
            and not self.failures
            and bool(self.comparisons)
            and all(result.passed for result in self.comparisons.values())
            and self.shared_db_before == self.shared_db_after
        )


def run_frozen_validation(
    *,
    repo_root: Path,
    baseline_db: Path,
    candidate_db: Path,
    characterization_path: Path,
    exclusions_path: Path,
    phase: str,
    checkpoint: Optional[str] = None,
) -> FrozenValidationResult:
    """Compare an explicit candidate to the immutable Feature 122 baseline."""
    for label, path in (
        ("baseline database", baseline_db),
        ("candidate database", candidate_db),
        ("characterization", characterization_path),
        ("exclusions", exclusions_path),
    ):
        if not path.is_file():
            raise ChangeValidationError(f"{label} not found: {path}")
    dbt_dir = repo_root / "dbt"
    shared_db = dbt_dir / "simulation.duckdb"
    before = FileGuard.capture("shared_dev_db", shared_db)
    characterization = CharacterizationRecord.model_validate_json(
        characterization_path.read_text(encoding="utf-8")
    )
    baseline_report = verify_characterization_database(baseline_db, characterization)
    marts = discover_marts(dbt_dir)
    manifest = load_exclusion_manifest(exclusions_path, known_relations=set(marts))
    comparisons = compare_marts_detailed(
        baseline_db,
        candidate_db,
        marts,
        exclusions=manifest.exclusions,
    )
    after = FileGuard.capture("shared_dev_db", shared_db)
    failures = list(baseline_report.failures)
    if before != after:
        failures.append("shared development database changed during validation")
    return FrozenValidationResult(
        baseline_id=characterization.baseline_id,
        phase=phase,
        checkpoint=checkpoint,
        baseline_verified=baseline_report.passed,
        comparisons=comparisons,
        shared_db_before=before,
        shared_db_after=after,
        failures=failures,
    )


def _sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo_root), capture_output=True, text=True
    )


def _census_rows(parquet: Path) -> Optional[int]:
    try:
        row = duckdb.sql(f"SELECT count(*) FROM read_parquet('{parquet}')").fetchone()
        return int(row[0]) if row is not None else None
    except Exception:
        return None


def _write_effective_config(
    base_config: Path, census: Optional[Path], horizon: Tuple[int, int], dest: Path
) -> Path:
    """Write a config YAML with census (if given) + horizon injected, like run_matrix.

    The wrapper seam loads config from a path exactly as ``planalign simulate --config``
    does, so we point it at this materialized file rather than mutating a config object.
    """
    import yaml

    data = yaml.safe_load(base_config.read_text()) or {}
    if census is not None:
        setup = data.setdefault("setup", {})
        setup["census_parquet_path"] = str(census)
    simulation = data.setdefault("simulation", {})
    simulation["start_year"] = horizon[0]
    simulation["end_year"] = horizon[1]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(data, sort_keys=False))
    return dest


class _PeakRssMonitor:
    """Sample a subprocess tree's RSS on a background thread; report the peak (MiB)."""

    def __init__(self, pid: int) -> None:
        self._pid = pid
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self.peak_bytes = 0
        try:
            import psutil  # noqa: F401

            self._enabled = True
        except ImportError:
            self._enabled = False

    def start(self) -> None:
        if self._enabled:
            self._thread.start()

    def stop(self) -> Optional[float]:
        if not self._enabled:
            return None
        self._stop.set()
        self._thread.join(timeout=2)
        return self.peak_bytes / (1024 * 1024)

    def _sample(self) -> None:
        import psutil

        try:
            proc = psutil.Process(self._pid)
        except psutil.Error:
            return
        while not self._stop.wait(0.15):
            try:
                tree = [proc, *proc.children(recursive=True)]
                total = 0
                for p in tree:
                    try:
                        total += p.memory_info().rss
                    except psutil.Error:
                        continue
                self.peak_bytes = max(self.peak_bytes, total)
            except psutil.Error:
                break


def _planalign_exe() -> str:
    return shutil.which("planalign") or "planalign"


def _run_build(
    *, years: str, config_path: Path, db_path: Path, repo_root: Path, log: Logger
) -> BuildMetrics:
    """Run one ``planalign simulate`` into an isolated DB; capture wall/RSS/count."""
    if db_path.exists():
        db_path.unlink()
    env = dict(os.environ)
    env["DATABASE_PATH"] = str(db_path)
    cmd = [
        _planalign_exe(),
        "simulate",
        years,
        "--config",
        str(config_path),
        "--database",
        str(db_path),
    ]
    start = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    monitor = _PeakRssMonitor(proc.pid)
    monitor.start()
    out, _ = proc.communicate()
    peak = monitor.stop()
    wall = time.time() - start
    if proc.returncode != 0:
        tail = (out or b"").decode("utf-8", "replace")[-1200:]
        log(f"[build FAILED rc={proc.returncode}] {db_path.name}")
        return BuildMetrics(False, wall, peak, None, db_path, error=tail)
    schedule = read_latest_schedule(db_path)
    count = schedule["invocation_count"] if schedule else None
    if count is not None and not isinstance(count, int):
        raise TypeError("recorded invocation_count is not an integer")
    return BuildMetrics(True, wall, peak, count, db_path)


def _tracked_change_summary(repo_root: Path) -> Tuple[List[str], List[str]]:
    """Return (tracked_changed_paths, untracked_paths) from porcelain status."""
    res = _git(repo_root, "status", "--porcelain")
    tracked, untracked = [], []
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.append(path)
        else:
            tracked.append(path)
    return tracked, untracked


def run_validation_campaign(
    *,
    repo_root: Path,
    config_path: Path,
    censuses: Sequence[Optional[Path]],
    years: str = DEFAULT_HORIZON,
    workdir: Path,
    keep_dbs: bool = False,
    log: Optional[Logger] = None,
) -> ValidationResult:
    """Stash the working-tree change, build baseline+candidate per census, compare.

    Raises ``ChangeValidationError`` on setup problems (not a git repo, clean tree,
    failed stash/pop). Build failures are captured in the result, not raised.
    """
    log = log or (lambda _m: None)
    horizon = _parse_horizon(years)
    workdir.mkdir(parents=True, exist_ok=True)
    dbt_dir = repo_root / "dbt"
    shared_db = dbt_dir / "simulation.duckdb"

    if not (repo_root / ".git").exists():
        raise ChangeValidationError(f"{repo_root} is not a git repository.")
    tracked, untracked = _tracked_change_summary(repo_root)
    if not tracked:
        raise ChangeValidationError(
            "No uncommitted tracked changes to validate. Make your change first "
            "(or commit the baseline and check out the change)."
        )
    if untracked:
        log(
            f"WARNING: {len(untracked)} untracked file(s) are NOT stashed and will NOT "
            f"be part of the baseline/candidate diff: {', '.join(untracked[:5])}"
            + (" ..." if len(untracked) > 5 else "")
        )

    marts = discover_marts(dbt_dir)
    log(f"Discovered {len(marts)} fct_*/dim_* marts to compare.")
    sha_before = _sha256(shared_db)

    scale_dbs: List[Tuple[str, Optional[Path], Optional[int], Path, Path, Path]] = []
    for idx, census in enumerate(censuses):
        label = census.name if census else "config-default"
        rows = _census_rows(census) if census else None
        eff = _write_effective_config(
            config_path, census, horizon, workdir / f"config_{idx}.yaml"
        )
        scale_dbs.append(
            (
                label,
                census,
                rows,
                eff,
                workdir / f"baseline_{idx}.duckdb",
                workdir / f"candidate_{idx}.duckdb",
            )
        )

    # ---- Baseline: stash the change, build, always restore ----
    stash_res = _git(repo_root, "stash", "push", "-m", "planalign-validate-change")
    if "No local changes" in (stash_res.stdout + stash_res.stderr):
        raise ChangeValidationError("git stash saved nothing; aborting.")
    if stash_res.returncode != 0:
        raise ChangeValidationError(f"git stash failed: {stash_res.stderr.strip()}")

    baselines: Dict[str, BuildMetrics] = {}
    try:
        for label, _census, _rows, eff, base_db, _cand_db in scale_dbs:
            log(f"[baseline] building {label} -> {base_db.name}")
            baselines[label] = _run_build(
                years=years,
                config_path=eff,
                db_path=base_db,
                repo_root=repo_root,
                log=log,
            )
    finally:
        pop = _git(repo_root, "stash", "pop")
        if pop.returncode != 0:
            raise ChangeValidationError(
                "CRITICAL: 'git stash pop' failed after building the baseline; your "
                f"change is still stashed. Recover with 'git stash pop'. Detail: {pop.stderr.strip()}"
            )

    # ---- Candidate: working tree restored, build + compare ----
    scales: List[ScaleResult] = []
    for label, _census, rows, eff, base_db, cand_db in scale_dbs:
        log(f"[candidate] building {label} -> {cand_db.name}")
        cand = _run_build(
            years=years, config_path=eff, db_path=cand_db, repo_root=repo_root, log=log
        )
        base = baselines[label]
        diffs: Dict[str, Tuple[object, object]] = {}
        if base.ok and cand.ok:
            diffs = compare_marts(base_db, cand_db, marts)
        scales.append(
            ScaleResult(
                census_label=label,
                census_rows=rows,
                baseline=base,
                candidate=cand,
                mart_diffs=diffs,
                small_census_warning=(
                    rows is not None and rows < SMALL_CENSUS_THRESHOLD
                ),
            )
        )

    sha_after = _sha256(shared_db)
    if not keep_dbs:
        for _l, _c, _r, _e, base_db, cand_db in scale_dbs:
            for p in (base_db, cand_db):
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass

    return ValidationResult(
        scales=scales, shared_db_sha_before=sha_before, shared_db_sha_after=sha_after
    )


def _parse_horizon(years: str) -> Tuple[int, int]:
    s = years.strip()
    if "-" in s:
        a, b = s.split("-", 1)
        return int(a), int(b)
    y = int(s)
    return y, y


class ChangeValidationError(RuntimeError):
    """Setup/precondition failure for a change-validation campaign."""
