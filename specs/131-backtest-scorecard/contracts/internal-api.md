# Contract: Internal API

The public surface of `planalign_backtest`, plus the additive changes to existing packages. Everything not listed is private.

---

## `planalign_backtest` public surface

```python
from planalign_backtest import (
    BacktestOptions,
    BacktestError,
    BacktestRun,
    MetricThresholds,
    Scorecard,
    run_backtest,
    load_scorecard,
    write_scorecard,
)
```

### `run_backtest(snapshots_dir, options=None) -> BacktestRun`

Executes one backtest end to end. Nothing is written to disk except the isolated run databases under `options.workdir` — the caller writes the pack and the scorecard, mirroring how `fit_parameter_pack` leaves materialization to `write_pack` (`planalign_fit/runner.py:66`). This keeps a backtest inspectable before it becomes an artifact.

`BacktestRun` carries the `ParameterPack`, the `Scorecard`, the `SnapshotSplit`, the `SeedRun`s, and diagnostics.

Raises `BacktestError` for every rejection in the CLI contract's exit-code-3 class, and `SimulationFailure` (a `BacktestError` subclass carrying `seed` and `year`) for exit code 4.

### `write_scorecard(scorecard, pack_dir, *, force=False) -> tuple[Path, Path]`

Writes `scorecard.json` and `scorecard.md` into `<pack_dir>/backtest/`. Refuses to overwrite without `force` (FR-029). Returns both paths.

### `load_scorecard(pack_dir) -> Scorecard | None`

Returns `None` when the pack has no scorecard. Raises `BacktestError` on a corrupt or unknown-schema-version file.

### `scorecard_is_current(scorecard, pack) -> bool`

`True` when `scorecard.provenance.pack_fingerprint` equals the pack's recomputed fingerprint (FR-026). Mirrors `verify_pack`'s role for packs.

### Module responsibilities

| Module | Public function(s) | Responsibility |
|---|---|---|
| `split.py` | `plan_split(snapshot_set, holdout_years) -> SnapshotSplit` | Partition and validate. Pure. |
| `actuals.py` | `extract_actuals(snapshot_set, split, bands) -> dict[MetricValue, float \| None]` | Actual metrics from held-out snapshots via a scoring-only `TransitionSet`. |
| `predicted.py` | `extract_predicted(database, split) -> dict[MetricValue, float \| None]` | Predicted metrics from one isolated run database. |
| `scoring.py` | `score(actuals, predicted_by_seed, thresholds) -> tuple[MetricComparison, ...]`, `classify(percent_error, threshold) -> Status`, `lower_median(values)` | Pure. All arithmetic and status derivation. |
| `simulate.py` | `run_seed(applied_pack, split, seed, workdir) -> SeedRun` | One isolated simulation. |
| `runner.py` | `run_backtest` | Orchestration only. |
| `report.py` | `render_markdown(scorecard) -> str`, `to_json(scorecard) -> str` | Rendering. Pure. |

`scoring.py` and `split.py` import nothing from `planalign_orchestrator` — they are pure functions over the models, which is what lets the fast test suite cover the arithmetic without touching a database.

---

## Additive changes to `planalign_fit`

Both are additive and default to current behavior; no existing caller changes.

### `FitOptions.only_years: Optional[tuple[int, ...]] = None`

When set, `fit_parameter_pack` subsets the loaded `SnapshotSet` to these years **immediately after `load_snapshots`** and before `build_transitions`. Everything downstream — transitions, estimators, and the pack manifest — sees only the retained snapshots.

```python
# planalign_fit/runner.py, inside fit_parameter_pack
snapshot_set = load_snapshots(snapshots_dir, conn)
if options.only_years is not None:
    snapshot_set = snapshot_set.subset(options.only_years)
transitions = build_transitions(conn, snapshot_set, bands)
```

This is the FR-003 seam (research R1). Its correctness properties:

- `build_pack` receives the subset set, so `manifest.snapshot_years` and `manifest.source_digest` cover fitted years only. A leak is visible in pack provenance, not merely in the scorecard.
- `register_snapshots` registers only retained snapshots, so no view over a held-out year exists on the fitting connection. Leakage would require a table that was never created.

Unknown years in `only_years` raise `SnapshotError` naming the requested and available years.

### `SnapshotSet.subset(years: Sequence[int]) -> SnapshotSet`

Returns a new set with only the named years, preserving order, then re-runs `_validate_set` — so a subset that is too small or non-consecutive is rejected by the same rules as any snapshot set. Raises `SnapshotError` on an unknown year or an invalid resulting set.

---

## Additive changes to `planalign_orchestrator`

### `EntryPoint` literal

Add `"backtest"` to the literal in `planalign_orchestrator/construction/spec.py:32`, alongside the existing harness values `invariant_test` and `perf_harness`. Makes backtest runs identifiable in `run_metadata` without inference.

### `run_metadata.backtest_score_ref`

One nullable `VARCHAR` column added in `_evolve_provenance_schema` (`planalign_orchestrator/run_metadata.py:376`), which already uses `ADD COLUMN IF NOT EXISTS` — no migration, and old databases converge on read.

Populated from a `backtest` sub-block that `apply_pack` adds to the `param_pack` provenance block when the pack carries a current scorecard:

```python
{
  "pack_id": ...,
  "fingerprint": ...,
  "backtest": {
    "scorecard_fingerprint": "…",
    "verdict": "pass",
    "holdout_years": [2024],
  },
}
```

Serialized compactly into the column. The `param_pack` block is an untyped config extra that `to_dbt_vars` ignores, so this reaches `run_metadata` without perturbing the config fingerprint — exactly the mechanism #458 established (`planalign_fit/apply.py:70`).

When a pack has no scorecard, or its scorecard is stale, the sub-block is omitted and the column stays `NULL`. A stale scorecard must never be reported as a current score.

---

## Invariants any implementation must preserve

1. **No held-out year influences any fitted parameter.** The only path from snapshots to estimators runs through the subset set (`test_backtest_leakage.py`).
2. **The fitting connection and the scoring connection are distinct DuckDB connections.** The scoring connection is never passed to `planalign_fit` code.
3. **`planalign_fit` does not import `planalign_backtest` or `planalign_orchestrator`.** The fitter stays free of simulation dependencies.
4. **Backtesting never changes a pack's fingerprint** (FR-028) — guaranteed by writing only under `<pack>/backtest/`.
5. **`scoring.py` and `split.py` remain pure** — no I/O, no clock, no randomness. Reproducibility is testable without a database.
6. **Every registry metric appears in `comparisons`** for every held-out year and for `cumulative`, even when not observable (SC-003).
