# Implementation Plan: Prorate Contributions & Match for Same-Year Enroll → Opt-Out Window

**Branch**: `101-enroll-window-proration` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/101-enroll-window-proration/spec.md` (issue #307)

## Summary

An employee who voluntarily enrolls partway through a simulation year and opts out later **in the same year** is currently credited **$0** in employee contributions, because `int_employee_contributions` multiplies the **year-end** deferral rate (0, post-opt-out) against the employment-prorated compensation. This understates contributions, employer match, balances, and cost for anyone who churns through enrollment within a year.

Fix: in `int_employee_contributions`, detect same-year enroll→opt-out employees from `fct_yearly_events`, compute their **active-enrollment window** (enrollment effective date → opt-out effective date, intersected with the employment window), credit a contribution proportional to that window using the **enrollment-event deferral rate** (recoverable from the event), and let the employer match follow. Year-end participation status (not-participating, rate 0) is unchanged (already correct from feature 095). A data-quality guard makes the behavior permanent and enforcing.

## Technical Context

**Language/Version**: SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1; Python 3.11 (orchestrator); DuckDB 1.0.0
**Primary Dependencies**: dbt models in STATE_ACCUMULATION stage; `fct_yearly_events` as the event source (sanctioned `int_*`→`fct_yearly_events` read)
**Storage**: DuckDB (`dbt/simulation.duckdb` shared dev; validate in isolated DBs)
**Testing**: dbt schema/data tests + a singular guard test; isolated-DB multi-year `planalign simulate`
**Target Platform**: On-prem analytics workstation; single-threaded dbt default
**Project Type**: Existing monorepo — dbt-only change (no Python/UI changes required)
**Performance Goals**: No multi-year runtime regression; window logic is set-based CASE/joins, vectorized
**Constraints**: Deterministic/reproducible; **zero regression** for the non-opt-out path and for year-end status (feature 095); no change to `prorated_annual_compensation` semantics for downstream comp consumers
**Scale/Scope**: 100K+ employees; change confined to contribution crediting + match base + one guard

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Status |
|-----------|------------|--------|
| I. Event Sourcing & Immutability | Reads enrollment/opt-out events from `fct_yearly_events`; no event mutation. Crediting is a deterministic function of events + comp + seed. | ✅ Pass |
| II. Modular Architecture | Logic localized to `int_employee_contributions` (+ one source change in `int_employee_match_calculations`); window math extracted into a CTE/macro. No new layer crossings. | ✅ Pass |
| III. Test-First Development | Guard test (`assert_same_year_enroll_optout_window.sql`) authored first at `warn`, then enforcing; isolated-DB scenario validates non-zero active-window contribution. | ✅ Pass |
| IV. Enterprise Transparency | Adds audit columns (`active_enrollment_days`, `enrollment_window_deferral_rate`, `contribution_window_category`) so crediting is explainable. | ✅ Pass |
| V. Type-Safe Configuration | No new config; rates parsed from event payload as today. dbt `ref()` only. | ✅ Pass |
| VI. Performance & Scalability | Year-filtered set-based CTE; no full scans, no new full-refresh of accumulators. | ✅ Pass |

**Result**: PASS — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/101-enroll-window-proration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── contribution-model.md
├── checklists/requirements.md
└── spec.md
```

### Source Code (repository root)

```text
dbt/models/intermediate/events/
├── int_employee_contributions.sql          # add enroll→opt-out window CTE; window-scaled base + window rate
└── int_employee_match_calculations.sql      # source eligible_compensation from the window-adjusted base column

dbt/models/intermediate/
└── schema.yml                               # document/test new columns

dbt/tests/
└── assert_same_year_enroll_optout_window.sql # NEW guard (does not exist yet; 095 Phase 6 was deferred)
```

**Structure Decision**: dbt-only change. No Python, API, or Studio work. The single integration seam is the contribution-model output columns consumed by the match model and the snapshot.

## Phase 0 — Research

See [research.md](./research.md). Key decisions:

- **Active-window deferral rate is recoverable** from the enrollment event's `event_details` (`REGEXP_EXTRACT(... '([0-9.]+)%\s*deferral')`), exactly as `int_deferral_rate_state_accumulator` already parses it — so we are not blocked by the year-end rate being 0.
- **Do NOT scale `prorated_annual_compensation`** (overriding the spec's Assumption-A). It has 15+ downstream consumers (comp growth, core contributions, snapshot, DQ); scaling it would corrupt compensation reporting. Instead scale only the **contribution base** (`total_contribution_base_compensation`) and set the **effective deferral rate** to the window rate; point the match model at that base. Non-opt-out employees are unaffected (base == comp for them).
- **The guard must be created**, not merely flipped — feature 095 deferred Phase 6, so `assert_same_year_enroll_optout_window.sql` does not exist.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — active-enrollment window entity, new/changed columns, validation rules.
- [contracts/contribution-model.md](./contracts/contribution-model.md) — the contribution-model output contract (columns, semantics, match consumption).
- [quickstart.md](./quickstart.md) — isolated-DB validation recipe (construct an enroll→opt-out employee; assert non-zero windowed contribution + match; regression checks).

## Complexity Tracking

> No constitution violations — table intentionally omitted.
