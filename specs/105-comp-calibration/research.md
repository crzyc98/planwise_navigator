# Phase 0 Research: Fast Compensation Calibration Mode

All Technical Context items were resolvable from the codebase and the spec's engineering notes; there were no open `NEEDS CLARIFICATION` markers. This document records the design decisions that shape Phase 1.

## Decision 1 — Reuse validated SQL (not pure Python)

- **Decision**: Calibration rebuilds the existing comp/workforce dbt subgraph and reads the existing S051 mart. No re-implementation of the workforce solver or compensation math.
- **Rationale**: The full comp-growth math is already implemented and validated — the E077 deterministic hire/termination solver (`int_workforce_needs`, `int_workforce_needs_by_level`), mid-year proration (`prorated_annual_compensation`), band-aware merit/COLA/promotion hazards, and `fct_compensation_growth` (per-year avg comp, YoY growth %, target status, required adjustment across 3 methodologies). Reusing it makes comp columns **exact by construction**, satisfying SC-002/FR-003. A Python/NumPy port (issue #280's Option A) could only ever be "within ±1%" and a directionally-wrong calibration tool is worse than none.
- **Alternatives considered**: Pure Python/NumPy projection (issue's Option A) — rejected: must re-derive proration + E077 rounding/apportionment, any drift breaks the accuracy AC.

## Decision 2 — Stale-but-present DC tables (Design 1), defer lean snapshot (Design 2)

- **Decision**: For v1, calibration runs against a database that has had **at least one full build**, so the DC tables that `fct_workforce_snapshot` and `fct_yearly_events` `ref()` already exist. Per year, calibration rebuilds only the comp subgraph + `fct_yearly_events` + `fct_workforce_snapshot`; the stale DC rows remain but never feed comp columns. A fail-fast guard rejects DBs missing those prerequisites.
- **Rationale**: Confirmed against the build graph: `fct_workforce_snapshot.sql` `ref()`s `int_employee_contributions`, `int_employee_match_calculations`, `int_employer_core_contributions`, `int_employer_eligibility`, `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`; `fct_yearly_events.sql` `ref()`s `int_enrollment_events`, `int_eligibility_events`, deferral events. A dbt `--select` of only comp models + these two marts **compiles and runs** as long as those DC tables physically exist (dbt resolves `ref()` to the existing relation; we simply don't rebuild it). This is the lowest-effort path and adds zero new dbt models. Commit #367 already removed a dead eligibility join from the snapshot, so the DC coupling is actively shrinking — favoring Design 1 short-term.
- **Alternatives considered**: Design 2 (a lean comp-only snapshot/mart that drops the DC `ref()`s entirely) — cleaner and removes the prerequisite, but heavier (new parallel snapshot model to maintain). **Deferred**; revisit only if Design 1 proves brittle (e.g. a future snapshot change makes a DC column actually influence a comp column).
- **Exactness guarantee under Design 1**: The comp columns read by `fct_compensation_growth` (`prorated_annual_compensation`, `detailed_status_code`, headcount) are computed entirely from the comp subgraph + events, with no functional dependence on the stale DC columns. Verification asserts this empirically (Decision 6).
- **Immutability scope (Constitution I)**: Per-year rebuilds of `fct_yearly_events` re-materialize event rows, which would violate event-store immutability on a production DB. This is acceptable here because calibration only ever writes to a **disposable, isolated calibration DB** (Decision 4), never the shared/production store. Calibration introduces no new event types and produces no separate audit trail (FR-014); the rebuilt events are a reused build dependency, not a deliverable.

## Decision 3 — Calibration workflow variant

- **Decision**: Add `WorkflowBuilder.build_calibration_year_workflow(year, start_year)` that returns the same stage shape as `build_year_workflow` but with DC models removed from EVENT_GENERATION and STATE_ACCUMULATION, while keeping `fct_yearly_events`, `int_workforce_snapshot_optimized`, and `fct_workforce_snapshot`.
- **Comp-only model set per year** (from lineage trace, ~17 models):
  - *Initialization/Foundation*: `int_baseline_workforce` (Y1) or `int_active_employees_prev_year_snapshot` + `int_prev_year_workforce_summary` + `int_prev_year_workforce_by_level` (Y2+); `int_employee_compensation_by_year`, `int_effective_parameters`, `int_workforce_needs`, `int_workforce_needs_by_level`
  - *Events*: `int_hazard_termination`, `int_hazard_promotion`, `int_hazard_merit`, `int_termination_events`, `int_hiring_events`, `int_new_hire_termination_events`, `int_promotion_events`, `int_merit_events`
  - *State/marts*: `fct_yearly_events`, `int_workforce_snapshot_optimized`, `fct_workforce_snapshot`, `fct_compensation_growth`
  - **Dropped** (DC, irrelevant to comp): `int_employer_eligibility`, `int_eligibility_determination`, `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`, `int_enrollment_events`, `int_deferral_*`, `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`, `int_employee_contributions`, `int_employer_core_contributions`, `int_employee_match_calculations`, `fct_employer_match_events`, `int_synthetic_baseline_enrollment_events`, `int_plan_eligibility_determination`, `int_workforce_pre_enrollment`, `int_workforce_active_for_events`.
- **Rationale**: Mirrors the proven stage ordering for determinism; uses dbt `--select` with an explicit model list (the runner already supports `--select`/`--exclude`/`--vars`). Keeping the explicit *include* list (rather than `--exclude` of DC) is safer because it can't accidentally pull a newly-added DC model.
- **Open validation for Phase 1/impl**: Confirm `fct_compensation_growth` is built by the full pipeline or add it to the calibration build set (it is referenced as the S051 mart but is not in the current `build_year_workflow` STATE_ACCUMULATION list — calibration must build it explicitly).

## Decision 4 — Isolated database by default

- **Decision**: With no `--database`, calibration writes to an isolated `<calibration>.duckdb` (timestamped dir, mirroring `scenario_batch_runner._run_isolated_scenario`), seeded from / pointed at a DB that already has the full DC layer. `get_database_path()` honors `DATABASE_PATH`, so the runner sets the target explicitly.
- **Rationale**: FR-006/SC-004 — never mutate the shared dev DB. Reuses the established batch isolation pattern.
- **Alternatives considered**: Default to the shared DB — rejected (violates FR-006 and the CLAUDE.md isolated-DB rule).

## Decision 5 — Parameter plumbing & interactive re-tune

- **Decision**: Calibration accepts the same comp params as the full sim via `--config` and CLI overrides, flowing through `CompensationSettings` → `config/export.py:to_dbt_vars()`. Interactive mode reuses `PipelineOrchestrator.update_compensation_parameters(cola_rate, merit_budget)` (re-execs `int_effective_parameters`) then re-runs the comp subgraph for the range.
- **Rationale**: FR-002/FR-009 — identical params, no re-typing, minimal rebuild between iterations.

## Decision 6 — Exactness verification strategy

- **Decision**: Integration test builds one full isolated baseline DB (`planalign simulate 2025-2029`), runs `calibrate 2025-2029` against it, and asserts `fct_compensation_growth` (avg comp, YoY growth %) matches **exactly**; repeats under a non-default edge config (higher COLA + fixed new-hire level distribution).
- **Rationale**: SC-002 — proves exactness empirically and that stale DC data doesn't leak into comp columns, per CLAUDE.md's isolated-DB + edge-config rule.

## Decision 7 — Studio surface

- **Decision**: New `POST /api/calibration/run` returns per-year results; a `CalibrationPanel.tsx` exposes four sliders (target growth, COLA, merit, new-hire mix) and renders per-year avg-comp + growth-vs-target charts. Per-level comp ranges are config/CLI-only in v1.
- **Rationale**: FR-012/FR-013/SC-006; matches the spec's v1 slider scope.
