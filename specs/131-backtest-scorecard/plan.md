# Implementation Plan: Backtest Scorecard

**Branch**: `131-backtest-scorecard` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/131-backtest-scorecard/spec.md`

## Summary

`planalign backtest <snapshots_dir>` holds out the most recent 1–2 census snapshot years, fits a parameter pack on the earlier years **only**, simulates the held-out span forward from the last fitted year's census in isolated databases across a small seed set, and scores predicted vs. actual into a scorecard stored with the pack.

The technical shape follows from three facts about what #458 already shipped:

1. `fit_parameter_pack()` loads **every** snapshot in a directory (`planalign_fit/runner.py:78`). The holdout split must therefore be a first-class filter inside the fitter, not a caller-side convention — otherwise held-out years leak into the fit and the whole feature is worthless. This is the single highest-risk seam in the plan.
2. `build_transitions()` (`planalign_fit/transitions.py:218`) already classifies hires, terminations, and promotions across a snapshot pair with band assignment. Actuals reuse it verbatim, so both sides of the comparison share one definition of every transition.
3. A pack's fingerprint covers only `parameters.yaml`, `seeds/*.csv`, and `source_digest` (`planalign_fit/pack.py:471`). A `backtest/` subdirectory inside the pack is invisible to it, so storing a score cannot change pack identity — FR-028 is satisfied structurally rather than by discipline.

New Python package `planalign_backtest/`, one new CLI command, one new `EntryPoint` literal, and a narrow additive change to `planalign_fit`. No dbt model changes.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: `planalign_fit` (#458 fitter, transitions, bands), `planalign_orchestrator` (`build_orchestrator`/`ConstructionSpec`, `run_metadata`), `duckdb` Python client, Typer + Rich (CLI), Pydantic v2 (scorecard models), PyYAML. No new third-party dependencies.
**Storage**: Isolated per-seed DuckDB files under `var/backtests/<run>/`; an in-memory DuckDB for actuals extraction. The shared `dbt/simulation.duckdb` is never opened. Artifacts are files under the parameter pack directory.
**Testing**: pytest with existing markers (`fast`, `integration`); fixtures from `tests/fixtures/`. Scoring, splitting, and rendering are pure-function unit tests; the harness self-test (FR-030) and reference example (FR-031) are integration tests.
**Target Platform**: macOS/Linux work laptop, single-threaded dbt by default.
**Project Type**: CLI tool + library package, matching `planalign_fit`.
**Performance Goals**: No latency target — a backtest is deliberately expensive (holdout_years × seeds full simulations). The requirement is progress reporting (FR-033), not speed. Default 3 seeds × 1 held-out year ≈ 3 single-year simulations.
**Constraints**: Peak RSS must stay within one simulation's measured ~1296 MiB budget — seeds run **serially**, so only one simulation is resident at a time. Per-run dbt artifact directories prevent `target/` collisions even though runs are serial, so a later move to the #457 pool needs no rework.
**Scale/Scope**: 2–5 snapshots, 1–2 held-out years, 1–5 seeds, censuses up to ~100k employees.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Event Sourcing & Immutability** | The backtest reads `fct_yearly_events` and `fct_workforce_snapshot`; it writes no events and mutates no event store. Determinism (FR-008) rests on the existing seed-reproducibility guarantee. Scorecards are write-once absent explicit overwrite (FR-029). | PASS |
| **II. Modular Architecture** | New `planalign_backtest/` package, 8 modules, each single-responsibility and well under 600 lines. Dependency direction is one-way: `planalign_backtest` → `planalign_fit` / `planalign_orchestrator`. Neither dependency imports the new package. | PASS |
| **III. Test-First Development** | Splitting, scoring, median/spread, and rendering are pure functions specified before implementation. The self-test (FR-030) is itself a mutation test — it must fail when comparison logic is broken. Fast suite stays under 10s: every simulation-driving test carries `integration`. | PASS |
| **IV. Enterprise Transparency** | The scorecard *is* an audit artifact: snapshot content hashes, fit/holdout split, seed set, thresholds, and pack fingerprint all recorded (FR-025). Failures name the year and seed (FR-032). The provenance chain closes through `run_metadata` (FR-027). | PASS |
| **V. Type-Safe Configuration** | Scorecard and configuration entities are Pydantic v2 models; the JSON artifact is serialized from them, so the documented schema and the code cannot drift. No raw SQL table-name concatenation beyond the parameterized patterns `planalign_fit` already uses. | PASS |
| **VI. Performance & Scalability** | Serial seeds keep peak memory at one simulation. dbt stays single-threaded. No new hot path. | PASS |

**Result: PASS, no violations.** The Complexity Tracking table is therefore omitted.

One constitutional note carried into design: Principle IV's audit requirement is why the holdout split is recorded in the **pack manifest** (via the fitter's own snapshot list) rather than only in the scorecard. If the split lived only in the scorecard, a leaked fit and an honest fit would be indistinguishable after the fact.

## Project Structure

### Documentation (this feature)

```text
specs/131-backtest-scorecard/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions and rejected alternatives
├── data-model.md        # Phase 1: entities, fields, validation rules
├── quickstart.md        # Phase 1: analyst-facing walkthrough
├── contracts/
│   ├── cli.md                 # `planalign backtest` command contract
│   ├── scorecard.schema.json  # Machine-readable scorecard JSON Schema (FR-024)
│   └── internal-api.md        # Public surface of planalign_backtest + fitter change
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
planalign_backtest/              # NEW package — mirrors planalign_fit's shape
├── __init__.py                 # Public surface: run_backtest, BacktestOptions, Scorecard
├── models.py                   # Pydantic v2: Scorecard, MetricComparison, SeedSpread, thresholds
├── split.py                    # Holdout split + validation (FR-002, FR-004)
├── actuals.py                  # Actual metrics from held-out snapshots via build_transitions
├── predicted.py                # Predicted metrics from an isolated run DB
├── scoring.py                  # Errors, thresholds, statuses, median, seed spread
├── simulate.py                 # Drives isolated per-seed simulations
├── runner.py                   # Orchestrates one backtest end to end
└── report.py                   # scorecard.md + scorecard.json rendering

planalign_fit/
├── runner.py                   # MODIFIED: FitOptions.only_years — the leakage seam
└── snapshots.py                # MODIFIED: SnapshotSet.subset(years)

planalign_cli/commands/
└── backtest.py                 # NEW: `planalign backtest` (mirrors fit.py)

planalign_orchestrator/
├── construction/spec.py        # MODIFIED: add "backtest" to the EntryPoint literal
└── run_metadata.py             # MODIFIED: backtest score reference column (FR-027)

tests/
├── test_backtest_split.py      # fast — split, validation, rejection messages
├── test_backtest_scoring.py    # fast — errors, zero-actual, thresholds, median/spread
├── test_backtest_report.py     # fast — rendering, schema conformance, md/json agreement
├── test_backtest_leakage.py    # fast — held-out years never reach the fit
└── test_backtest_harness.py    # integration — self-test (FR-030), end-to-end, determinism

docs/guides/
└── backtesting.md              # Guide + reference example (FR-031)
```

**Structure Decision**: A separate `planalign_backtest/` package rather than a module inside `planalign_fit`. Backtesting *consumes* fitting and additionally drives simulations — folding it into `planalign_fit` would make the fitter depend on the orchestrator, inverting a dependency that is currently clean (the fitter touches no simulation database at all, `planalign_fit/runner.py:74`). Keeping them separate preserves that property, which is what lets the fitter stay fast and side-effect-free.

## Phase 0: Research

See [research.md](./research.md). Nine decisions resolved, no open NEEDS CLARIFICATION. The load-bearing ones:

- **R1 Leakage seam**: add `FitOptions.only_years`; the split happens inside `fit_parameter_pack` immediately after `load_snapshots`, so the pack manifest records only the fitted snapshots and a leak becomes visible in provenance.
- **R2 Actuals**: reuse `build_transitions` over the full snapshot set in an in-memory DuckDB, used solely for scoring. Reading held-out data to *score* is not leakage; the isolation that matters is that this connection never reaches an estimator.
- **R3 Comparability**: both sides band with the same `BandDefinitions` seeds; predicted metrics read `fct_workforce_snapshot`'s `age_band`/`tenure_band`/`level_id` columns, and a test asserts the two band sources agree.
- **R5 Median**: lower median for even seed counts, keeping counts integral and the result order-independent.

## Phase 1: Design

See [data-model.md](./data-model.md), [contracts/](./contracts/), and [quickstart.md](./quickstart.md).

**Entities**: `SnapshotSplit`, `BacktestOptions`, `MetricThresholds`, `SeedRun`, `MetricComparison`, `SeedSpread`, `Scorecard`, `BacktestProvenance`.

**Contracts**:
- `contracts/cli.md` — arguments, options, exit codes, and the exact rejection messages required by SC-010.
- `contracts/scorecard.schema.json` — versioned JSON Schema satisfying FR-024, generated from the Pydantic models so schema and code cannot drift.
- `contracts/internal-api.md` — `planalign_backtest`'s public functions plus the two additive `planalign_fit` changes.

**Post-design Constitution re-check**: PASS. The design introduces no module over 600 lines, no circular dependency, and no dbt model change. The one addition worth flagging for review is the new `run_metadata` column for the backtest score reference — additive and nullable, consistent with how #458 added `param_pack_*` (`planalign_orchestrator/run_metadata.py:376`), so it needs no migration.

## Risks

| Risk | Mitigation |
|---|---|
| **Held-out data leaks into the fit**, silently invalidating every scorecard | The split lives inside the fitter (R1); `test_backtest_leakage.py` asserts the pack manifest lists only fitted years and that no estimator observes a held-out year. This is the feature's correctness core. |
| **Predicted and actual bands diverge**, producing errors that measure a definitional gap rather than model error | Both sides derive from the same seed CSVs; an explicit test compares band assignment across the two paths for the same employee population. |
| **Compensation basis mismatch** (census annual rate vs. prorated simulation compensation) | R4 fixes the basis to the annualized rate on both sides and states it on the scorecard; a mismatch would appear as a systematic error the self-test catches. |
| **Self-test passes vacuously**, certifying a broken harness | FR-030 requires the self-test to fail under a deliberately introduced comparison defect; implemented as an explicit mutation assertion, not merely a tolerance check. |
| **Backtest runtime frustrates analysts** (up to 10 simulations at 5 seeds × 2 years) | Progress reporting per seed and year (FR-033); serial-by-design documented; the #457 pool is a later drop-in that must not change values. |

## Out of Scope for This Plan

Per the spec: statistical inference, backtest-driven auto-tuning, Studio presentation, cross-pack benchmarking, per-employee reconciliation. Parallel seed execution is explicitly deferred, and the design keeps it a pure substitution.
