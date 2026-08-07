# Phase 0 Research: Plan-Design Optimizer

No `NEEDS CLARIFICATION` markers remain in the Technical Context — all resolved directly from the spec's own Clarifications session or from direct inspection of the existing codebase. This document records the decisions and the evidence behind them.

## 1. Package placement: new `planalign_optimizer/`, not `planalign_orchestrator/`

**Decision**: New standalone package `planalign_optimizer/`, sibling to `planalign_fit/` and `planalign_ensemble/`.

**Rationale**: `planalign_orchestrator/calibration_optimizer.py` already exists and is unrelated — it is the E077-era algebraic solver behind `planalign calibrate`'s COLA/merit tuning, not a design-space search. Reusing the name "optimizer" inside `planalign_orchestrator` would collide conceptually and in tests/imports. `planalign_fit` and `planalign_ensemble` establish the precedent: a feature that (a) has its own Pydantic spec model, (b) drives `ScenarioRunPool` for isolated evaluation, and (c) produces its own artifact directory gets its own top-level package, importing `planalign_orchestrator` as a library rather than living inside it.

**Alternatives considered**:
- Extending `calibration_optimizer.py` — rejected: that module solves a closed-form algebraic problem (single lever, deterministic formula) with no search loop, no isolation model, and no constraint concept. Wrong shape entirely.
- A submodule of `planalign_orchestrator/` — rejected: would grow the orchestrator package past its role as construction/execution plumbing, and none of `planalign_fit`/`planalign_ensemble` set this precedent either.

## 2. Candidate execution: reuse `ScenarioRunPool` verbatim

**Decision**: Every candidate becomes a `ScenarioJob` (name, resolved config, isolated `db_path`, seed) submitted to the existing `planalign_orchestrator.run_pool.ScenarioRunPool`. Worker sizing reuses `resolve_worker_count` unmodified.

**Rationale**: The module's own docstring already names this as forward-looking design: *"the small pool that `planalign batch` uses today and that the seed-ensemble runner and optimizer submit to later."* `ScenarioRunPool` already provides process isolation, per-job failure containment (`JobResult.status`), and Ctrl+C-safe teardown — exactly what FR-006 (isolated, independently re-runnable candidate runs) and FR-016 (failed candidates recorded distinctly, no silent drop) require, with zero new concurrency code.

**Alternatives considered**: A dedicated optimizer-specific pool — rejected as pure duplication; `JobResult`'s `succeeded`/`error`/`traceback` fields already map directly onto the spec's "failed" candidate status.

## 3. Metric vocabulary and evaluation: reuse `planalign_ensemble`'s extraction, not a new metrics engine

**Decision**: The objective/constraint metric vocabulary (FR-004) is exactly `planalign_ensemble.models.CANONICAL_METRICS` (`active_headcount`, `total_compensation`, `employer_match_cost`, `total_employer_plan_cost`, `participation_rate`, `avg_deferral_rate`) plus IRS-compliance pass/fail sourced from the existing `dq_compliance_monitoring` mart. Point-estimate evaluation (the default per the spec's Clarifications) reads a single candidate's own `fct_workforce_snapshot` using the same query logic as `planalign_ensemble.extract.extract_seed_metrics` — a candidate scenario run *is* structurally identical to one ensemble seed run (one isolated `.duckdb`, same snapshot mart). Percentile-based evaluation (only when the user explicitly names a percentile per FR-015) reads `fct_metric_distributions` from a pre-existing ensemble aggregate database for that metric/year, following the exact query pattern documented in `docs/guides/seed_ensembles.md`.

**Rationale**: `extract_seed_metrics` already solves "read headline metrics from one completed scenario database, treating missing columns as absent rather than zero" — the identical requirement FR-007 states for objective/constraint non-evaluability. Reimplementing this for the optimizer would fork metric definitions across two features that must agree (a metric named `total_employer_plan_cost` must mean the same thing whether it comes from an ensemble seed or an optimizer candidate). No new SQL is required for the point-estimate path; percentile evaluation is a read against an existing table that the user must already have produced via `planalign simulate --seeds N`.

**Alternatives considered**: Defining a separate, optimizer-specific metric vocabulary — rejected, directly contradicts the spec's own instruction that the vocabulary is "the headline metrics from #460." Computing percentiles inline from scratch — rejected: `fct_metric_distributions` already exists, is tested, and is the authoritative percentile source; recomputing would risk drift from the ensemble system's percentile method (NumPy `linear`).

## 4. Config delta resolution: overlay declared levers on the baseline, diff via existing config export

**Decision**: A candidate's effective config is the baseline `SimulationConfig` with only the declared, searchable lever fields overridden (e.g. `employer_match.tiers[0].match_rate`, `enrollment.auto_enrollment.default_deferral_rate`). The config delta shown per candidate (FR-007) is derived by comparing `to_dbt_vars(baseline)` and `to_dbt_vars(candidate)` and reporting only the keys that differ — which, by construction (FR-001's pinning guarantee), are exactly the declared levers.

**Rationale**: `planalign_orchestrator/config/export.py::to_dbt_vars` is already the single source of truth translating Pydantic config into the dbt vars every simulation run consumes (used identically by `planalign calibrate`, `planalign fit --params` overlays, and Studio's calibration panel). Building candidates this way makes "every other config value not declared searchable remains pinned to baseline" (FR-001) a structural guarantee rather than something to test for separately: only mutating declared fields on a deep copy of the baseline config, before export, cannot touch anything else.

**Alternatives considered**: Hand-rolling a parallel dbt-var diffing function — rejected as duplicate logic prone to drifting from the real export path candidates will actually run under.

## 5. Vesting schedule as a lever: a named-choice string, not a numeric range

**Decision**: `vesting_schedule` is modeled as a **discrete-choice lever** (a `vesting_schedule` name string, e.g. `immediate`, `qaca_2_year`, matching the strings already accepted under `employer_match_formulas.*.vesting_schedule` in `config/simulation_config.yaml`), not a bounded continuous range.

**Rationale**: Direct inspection of `config/simulation_config.yaml` (E084 match formula blocks) and the codebase shows there is no standalone Pydantic `VestingSettings` model with numeric fields — vesting is a named schedule reference attached to a match formula, resolved against seed-defined schedules. A "vesting schedule choice" lever is therefore inherently the discrete-choice case the design-space spec already supports (FR-001), not a new lever type.

**Alternatives considered**: Introducing a new parametric vesting model (e.g. cliff years as a continuous lever) — rejected as out of scope; the spec's v1 lever list mirrors existing config-driven structures exactly, and vesting's existing structure is discrete by nature.

## 6. Search strategy: grid seeding + coordinate-descent local refinement, bounded by the mandatory run-budget cap

**Decision**: v1 search combines (a) an initial grid/Latin-hypercube-style seed set spread across the declared design space (discrete levers enumerated, continuous levers sampled), consuming an initial fraction of the run budget, followed by (b) coordinate-descent local refinement around the best feasible/least-infeasible points found so far, consuming the remaining budget. No exotic optimizer (Bayesian optimization, genetic search, etc.) is introduced.

**Rationale**: Directly follows the spec's Clarifications: v1 supports ~6-8 levers, exhaustive grid is impractical at that scale, so *"budget-bounded sampling (grid seeding + local refinement) is required, not optional"* — but nothing beyond that is warranted, matching the source issue's explicit guidance that *"the engine is cheap now and the space is low-dimensional... No exotic optimizers."* This is also the same class of problem `planalign sweep` (#433, one lever) already handles as a special case — the optimizer generalizes it rather than replacing it with a fundamentally different technique.

**Alternatives considered**: A single fixed grid with no refinement — rejected: wastes budget on a coarse grid when 6-8 mixed discrete/continuous levers make any single practical grid resolution too coarse to find a good optimum. Bayesian optimization / surrogate modeling — rejected as unjustified complexity for a low-dimensional, moderately expensive-to-evaluate (~90-120s/candidate) search space; explicitly out of scope per the source issue.

## 7. Reproducibility: a dedicated search RNG, seeded independently of scenario seeds

**Decision**: The optimizer's own search process (which candidates get sampled, in what order) is driven by a single seed supplied at invocation, deterministic and separate from the per-candidate scenario simulation seed (which stays pinned to whatever seed policy the baseline config/CLI already uses for reproducible simulation runs).

**Rationale**: FR-010 requires that "the same spec plus the same seed reproduces the same sequence of evaluated candidates and the same reported results." This mirrors `planalign_ensemble`'s existing separation of concerns — the ensemble planner's seed selection is deterministic and independent from within-simulation randomness — and keeps the two seed roles (which configs get tried vs. how one config's simulation resolves stochastic events) cleanly separated, avoiding a single seed silently controlling both.

**Alternatives considered**: Reusing the simulation's own random seed to also drive candidate sampling — rejected: conflates two independent sources of randomness and would make search-path reproducibility fragile to unrelated simulation-seed changes.

## 8. Persistence and export: pack-directory convention, not a new database schema

**Decision**: An optimizer run writes an output directory (mirroring `planalign_fit`'s parameter-pack directory and `planalign_ensemble`'s timestamped ensemble directory): the resolved spec, a candidate ledger (structured, e.g. Parquet/CSV or a small DuckDB file — decided in Phase 1 data model), a human-readable `report.md`, an Excel/JSON export (FR-013), and one retained subdirectory per candidate holding that candidate's full `.duckdb` (FR-014). No new tables are added to `dbt/simulation.duckdb` or any shared database.

**Rationale**: Matches the codebase's established convention (`planalign_fit/pack.py`, `planalign_ensemble` aggregate directories, `planalign batch`'s timestamped scenario directories) of self-contained, timestamped output directories rather than a shared mutable store — directly consistent with the one-database-per-scenario isolation invariant this whole platform already enforces, and avoids inventing a new persistence pattern for a feature whose entities (candidates, a run) are naturally a small, bounded, run-scoped dataset.

**Alternatives considered**: A shared `run_metadata`-style append-only table across all optimizer runs — rejected: `run_metadata` exists to detect config/seed drift across runs *of the same scenario database*, which is a different problem; a fresh, self-contained directory per optimizer run is simpler and matches what every comparable prior feature already does.
