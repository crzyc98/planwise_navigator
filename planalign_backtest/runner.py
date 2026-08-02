"""End-to-end backtest orchestration."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import logging

import duckdb

from _version import __version__
from planalign_backtest.actuals import extract_actuals
from planalign_backtest.models import (
    BacktestOptions,
    BacktestProvenance,
    Scorecard,
    SeedRun,
    SnapshotRef,
    SnapshotSplit,
)
from planalign_backtest.predicted import extract_predicted
from planalign_backtest.scoring import score
from planalign_backtest.simulate import (
    configure_seed,
    prepare_boundary_census,
    run_seed,
)
from planalign_backtest.split import plan_split
from planalign_fit.apply import apply_pack
from planalign_fit.pack import ParameterPack, write_pack
from planalign_fit.runner import fit_parameter_pack
from planalign_fit.snapshots import load_snapshots

logger = logging.getLogger(__name__)


@dataclass
class BacktestRun:
    pack: ParameterPack
    scorecard: Scorecard
    split: SnapshotSplit
    seed_runs: tuple[SeedRun, ...]
    diagnostics: dict[str, object]


def run_backtest(
    snapshots_dir: Path | str, options: Optional[BacktestOptions] = None
) -> BacktestRun:
    options = options or BacktestOptions()
    with duckdb.connect(":memory:") as conn:
        snapshot_set = load_snapshots(snapshots_dir, conn)
    split = plan_split(snapshot_set, options.holdout_years)
    fit_options = replace(options.fit_options, only_years=split.fit_years)
    if options.output is not None and fit_options.pack_id is None:
        fit_options = replace(fit_options, pack_id=options.output.name)
    fit_run = fit_parameter_pack(snapshots_dir, fit_options)

    # Absolute: the orchestrator invokes dbt with the dbt project as its working
    # directory, so a relative workdir (the default is `var/backtests/...`) would
    # resolve against `dbt/` and the overlay project would appear to not exist.
    root = (
        options.workdir or _default_workdir(fit_run.pack.manifest.pack_id)
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)
    scratch_pack = root / "parameter_pack"
    write_pack(fit_run.pack, scratch_pack)
    base_config = options.base_config or Path("config/simulation_config.yaml")
    applied = apply_pack(
        scratch_pack,
        base_config,
        workdir=root / "applied_pack",
    )
    boundary = next(
        snapshot for snapshot in snapshot_set if snapshot.year == split.boundary_year
    )
    boundary_path = prepare_boundary_census(boundary, root)

    actuals = extract_actuals(snapshot_set, split, fit_run.bands)
    seed_runs: list[SeedRun] = []
    predictions = []
    for seed in options.seeds:
        logger.info(
            "Backtest seed %s: simulating %s",
            seed,
            ", ".join(str(year) for year in split.holdout_years),
        )
        seeded = configure_seed(applied, split, seed, boundary_path, root)
        completed = run_seed(seeded, split, seed, root)
        seed_runs.append(completed)
        predictions.append(extract_predicted(completed.database, split))
        if not options.keep_databases:
            completed.database.unlink(missing_ok=True)

    comparisons = score(actuals, predictions, options.thresholds)
    provenance = _provenance(snapshot_set, split, fit_run.pack)
    scorecard = Scorecard(
        split=split,
        seeds=options.seeds,
        seed_runs=tuple(
            run.model_copy(update={"database": Path(run.database.name)})
            for run in seed_runs
        ),
        thresholds=options.thresholds,
        overridden_thresholds=options.overridden_thresholds,
        comparisons=comparisons,
        provenance=provenance,
        notes=options.notes,
    )
    return BacktestRun(
        pack=fit_run.pack,
        scorecard=scorecard,
        split=split,
        seed_runs=tuple(seed_runs),
        diagnostics={"workdir": str(root), "metric_count": len(comparisons)},
    )


def _default_workdir(pack_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("var/backtests") / f"{stamp}-{pack_id}"


def _provenance(snapshot_set, split, pack: ParameterPack) -> BacktestProvenance:
    refs = tuple(
        SnapshotRef(
            year=snapshot.year,
            filename=snapshot.path.name,
            sha256=snapshot.sha256,
            row_count=snapshot.row_count,
            role="fit" if snapshot.year in split.fit_years else "holdout",
        )
        for snapshot in snapshot_set
    )
    # Always compensation_band: by-level headcount is scored on the basis the
    # SIMULATOR uses, and int_baseline_workforce derives level from compensation
    # ranges regardless of what the census carries. Reporting census_level_id
    # whenever the column merely exists described only the actual side.
    level_basis = "compensation_band"
    return BacktestProvenance(
        snapshots=refs,
        source_digest=pack.manifest.source_digest,
        pack_id=pack.manifest.pack_id,
        pack_fingerprint=pack.manifest.fingerprint,
        promotion_basis=pack.manifest.promotion_basis,
        level_basis=level_basis,
        compensation_basis="annualized rate for active employees at year end",
        backtest_date=datetime.now(timezone.utc).isoformat(),
        tool_version=__version__,
    )
