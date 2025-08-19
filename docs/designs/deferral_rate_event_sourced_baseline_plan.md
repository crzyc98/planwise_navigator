# Deferral Rate Event-Sourced Baseline Plan

Status: Draft for review
Owner: Data/Modeling
Related epics: E023 (Enrollment), E035 (Escalation), S042-02 (Temporal Accumulator)

## Context
- Large mass at 6% arises from hard-coded pre-enrolled fallback (6%) and/or auto-enrollment default set to 6%.
- Contributions source deferral rates from the accumulator, not `fct_yearly_events` or census.
- Escalations apply inconsistently when baseline is not event-sourced.

## Goals
- Use census deferral for pre-enrolled participants to remove the artificial 6% mass.
- Keep the system fully event-sourced for auditability and explainability.
- Make default rates, caps, and maturity windows configurable and consistent.
- Ensure accumulator ↔ contributions parity with strong tests.

## High-Level Plan
- Generate synthetic baseline enrollment events from census for pre-2025 enrollees.
- Rebuild `int_deferral_rate_state_accumulator_v2` purely from events (real + synthetic + escalations).
- Introduce macros for defaults/caps; clamp and type rates consistently.
- Add maturity guard to prevent same-year escalation after a synthetic baseline.
- Replace `NOT IN` anti-joins with `NOT EXISTS` to avoid NULL pitfalls.
- Add lineage columns and robust tests/monitors.
- Materialize escalation events as a table; unify on a single target DuckDB per run.

## Detailed Changes

### 1) Synthetic Baseline Events (from census)
- New model: `dbt/models/intermediate/events/int_synthetic_baseline_enrollment_events.sql`.
- Input: `int_baseline_workforce` (requires normalized `employee_deferral_rate`).
- Emit one `enrollment` event for each pre-2025 enrollee:
  - `event_type='enrollment'`, `event_source='synthetic_baseline'`.
  - `effective_date='{{ var("start_year", 2025) }}-01-01'`.
  - `employee_deferral_rate` from census, normalized to unit [0,1].
  - `parameter_scenario_id`, `created_at`, `data_quality_flag`.
- Feed events into the pipeline by UNION with `int_enrollment_events` (preferred) or as an additional CTE in `fct_yearly_events`.

### 2) Event-Driven Accumulator
- Update `int_deferral_rate_state_accumulator_v2`:
  - Remove hard-coded pre-enrolled fallback (6%).
  - Base initial state exclusively on event stream (real or synthetic).
  - Apply current-year escalations to previous-year carried state.
  - Add columns:
    - `rate_source` (`synthetic_baseline|auto_enroll|manual_event|carry_forward`).
    - `no_escalation_reason` (`anniversary|at_or_above_cap|opt_out|ineligible|missing_baseline_event`).

### 3) Defaults/Caps Macros + Scenario Snapshot
- Macros (new, under `dbt/macros`):
  - `default_deferral_rate()` → `var('auto_enrollment_default_deferral_rate', 0.02)`.
  - `plan_deferral_cap()` → `var('plan_deferral_cap', 0.15)`.
- Use macros in:
  - `int_enrollment_events` (auto-enroll default), synthetic baseline fallback (only if census missing), tests.
- Snapshot resolved values at run start to a small `scenario_config_snapshot` table for reproducibility.

### 4) Same-Year Escalation Guard
- In `int_deferral_rate_escalation_events`:
  - If `event_source='synthetic_baseline'` and `enrollment_year == simulation_year`, set `eligible_for_escalation=false` (or require `months_since_enrollment >= 12`).
  - Keep `enrollment_maturity_years` configurable via var (default 0) and honor the guard.

### 5) Anti-Join Hygiene
- Replace `NOT IN` with `NOT EXISTS` for historical enrollment anti-joins in accumulator and related models.
- When anti-joining, filter subquery by `enrollment_date < '{{ simulation_year }}-01-01'` to avoid excluding future-year events.

### 6) Types and Clamps
- Normalize all deferral rates to unit interval and store as `DECIMAL(5,4)`.
- Clamp to `[0, plan_deferral_cap()]` in accumulator, enrollment events, escalations, and contributions.
- Add staging for census deferral (`stg_census_deferral_rates`) to normalize units (e.g., 1.3% vs 0.013).

### 7) Lineage + Parity
- Add lineage fields:
  - In accumulator and contributions: `rate_source`, `no_escalation_reason`.
- Ensure `int_employee_contributions.final_deferral_rate` equals accumulator `current_deferral_rate` per employee/year.

### 8) Materialization & One DB
- Materialize `int_deferral_rate_escalation_events` as a table in dbt DuckDB.
- Ensure orchestrator and dbt target the same DuckDB per run; avoid mixing `simulation.duckdb` and `dbt/simulation.duckdb`.

### 9) Tests & Monitors
- Schema tests:
  - `accepted_range` on all deferral rates: `[0, plan_deferral_cap()]`.
  - `not_null` on `(employee_id, simulation_year, current_deferral_rate)`.
  - `unique` on `(employee_id, simulation_year)` in accumulator and contributions.
- Parity test:
  - Join accumulator ↔ contributions; fail if any rate mismatch.
- Coverage test:
  - For rows with `had_escalation_this_year=1`, assert a corresponding escalation event exists.
  - For any enrolled employee, assert a real enrollment event or a synthetic baseline exists before/at their first simulated year.
- Spike detector:
  - Alert if `> X%` contributors are exactly `default_deferral_rate()` with `rate_source != 'auto_enroll'`.

## Validation Plan
- 2025:
  - Distribution aligns with census (no 6% mass), mean/median match within tolerance.
  - Share at exactly 2% equals the number of auto-enrolled new hires (± tolerance).
  - Event coverage passes.
- 2026+:
  - CDF shifts ~1% per year for eligible, non-capped, non-opt-outs.
  - Plateaus near `plan_deferral_cap()` for high deferrers.
  - Escalation coverage passes; same-year guard prevents double bumps.
- Parity: zero mismatches between accumulator and contributions.

## Rollout Steps (Minimal Diffs First)
1) Add macros + scenario config snapshot table.
2) Add `stg_census_deferral_rates` and propagate normalized `employee_deferral_rate` to `int_baseline_workforce`.
3) Implement `int_synthetic_baseline_enrollment_events` and union into `int_enrollment_events`/`fct_yearly_events`.
4) Update accumulator to be events-only; add lineage fields and clamps.
5) Add same-year escalation guard and materialize escalation events as table.
6) Add tests (parity, coverage, spike detector, accepted_range, uniqueness).
7) Run 2025–2027; publish short validation summary (distribution, spike %, coverage, parity=clean).

## Open Questions
- Census field: confirm it reflects employee deferral (pre-tax + Roth) only (exclude after-tax/match). If multiple fields, define precedence.
- Missing census baseline: fail loud vs fallback to `default_deferral_rate()` or `fallback_pre_enrolled_rate` var?
- Cap policy: retain 10% or align to plan-specific cap?

## Out of Scope (Now)
- Changing escalation increment/cap by demographic beyond existing levers.
- Reworking enrollment probability models.
- Migrating historical runs; focus on forward compatibility and clear lineage.

## Appendix: Notes
- Keep `auto_enrollment_scope='new_hires_only'` semantics strict via registry/state so pre-2025 synthetic baselines do not escalate when scope is limited to new hires.
- Consider embedding numeric `previous_rate` and `new_rate` in `event_details` JSON for easy downstream use (optional).
