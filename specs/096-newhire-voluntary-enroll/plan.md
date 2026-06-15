# Implementation Plan: New Hires Voluntarily Enroll in Their Hire Year

**Branch**: `096-newhire-voluntary-enroll` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/096-newhire-voluntary-enroll/spec.md`

## Summary

Eligible new hires are currently excluded from voluntary enrollment in their hire year and only become
candidates the following simulation year, so they appear as `not_participating` with a zero deferral
rate and no employer match in their hire-year snapshot. Root cause (confirmed against the user's
scenario database): `int_voluntary_enrollment_decision` derives its candidate population solely from
`int_employee_compensation_by_year`, which does **not** include a new hire in their hire year. The
fix widens the voluntary enrollment decision's candidate population to include current-year new hires
(sourced from hire events / `int_new_hire_compensation_staging`), evaluates them at the same
demographic-based configured rate as everyone else, and dates any resulting enrollment event on the
employee's **eligibility date**. A permanent dbt data-quality test guards against regression.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8, dbt-duckdb 1.8.1), Python 3.11 (tests)
**Primary Dependencies**: DuckDB 1.0.0; existing temporal-accumulator pattern (E023) and feature-095
snapshot propagation
**Storage**: DuckDB (`dbt/simulation.duckdb`) — no schema migration; logic-only change to existing
models; `int_enrollment_events` remains incremental
**Testing**: dbt tests (`tag:data_quality`), pytest (`-m "fast and events"`, integration)
**Target Platform**: On-prem analytics server / work-laptop (single-threaded dbt, `--threads 1`)
**Project Type**: Data pipeline (dbt models + Python orchestrator)
**Performance Goals**: No regression; all added logic filtered by `{{ var('simulation_year') }}`
**Constraints**: No circular dependencies (read upstream hire events / staging, never `fct_*`);
deterministic & seed-reproducible; `{{ ref() }}` only
**Scale/Scope**: ~3–4 dbt models touched + 1 new test + tests; 100K+ employee scale unaffected

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ PASS | Fix changes the *year an enrollment event is generated in*, not event immutability; no events mutated/deleted. Determinism preserved via seeded `enrollment_random`/`deferral_random`. Existing `prior_year_enrollments` guard prevents duplicate/cross-year events. |
| II. Modular Architecture | ✅ PASS | Change localized to `int_voluntary_enrollment_decision` (+ one new test). New-hire candidate source is upstream (hire events / staging); no reverse/`fct_*` dependency; no new circular dep. |
| III. Test-First Development | ✅ PASS | New dbt regression test + pytest assertions written before/with the model change (tasks ordered test-first). |
| IV. Enterprise Transparency | ✅ PASS | Enrollment events retain demographic audit detail; regression test makes the defect detectable in CI. |
| V. Type-Safe Configuration | ✅ PASS | All references via `{{ ref() }}`; reuses `eligibility_waiting_days`/voluntary-rate vars; no raw SQL table concat. |
| VI. Performance & Scalability | ✅ PASS | Added candidate rows filtered by simulation year; single-threaded default unaffected. |

**Result**: PASS — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/096-newhire-voluntary-enroll/
├── plan.md              # This file
├── research.md          # Phase 0 — root cause + decisions (complete)
├── data-model.md        # Phase 1 — entities & column contracts
├── quickstart.md        # Phase 1 — reproduce + validate
├── contracts/
│   └── enrollment-model-contract.md   # Phase 1 — model/test contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 — created by /speckit.tasks (NOT here)
```

### Source Code (repository root)

```text
dbt/
├── models/
│   └── intermediate/
│       ├── int_voluntary_enrollment_decision.sql      # PRIMARY: widen candidate population to
│       │                                              #   include current-year eligible new hires;
│       │                                              #   effective date = eligibility date
│       ├── int_enrollment_events.sql                  # VERIFY: voluntary events flow + dedup/guard
│       │                                              #   keep exactly one event per enrollee
│       └── int_new_hire_compensation_staging.sql      # SOURCE (read-only): current-year new-hire
│                                                      #   demographics/compensation
│   └── marts/ (or tests/)
│       └── test_new_hire_voluntary_enrollment_hire_year.sql  # NEW: data_quality regression test
├── macros/
│   └── enrollment_eligibility.sql                     # REFERENCE: eligibility/window macros
└── seeds/ (no change)

tests/
└── test_new_hire_voluntary_enrollment.py              # NEW: pytest (fast + integration) assertions
```

**Structure Decision**: Existing dbt-centric layout. The fix is concentrated in
`int_voluntary_enrollment_decision.sql` with read-only use of `int_new_hire_compensation_staging`, a
verification pass on `int_enrollment_events.sql`'s dedup/guard, one new dbt data-quality test, and
pytest coverage. No new packages or directories.

## Phase 0: Outline & Research

**Status**: ✅ Complete — see [research.md](./research.md).

Root cause confirmed by direct query of the user's scenario database (0 hire-year new hires in
`int_employee_compensation_by_year`; every new-hire cohort's first enrollment is post-hire-year;
proactive new-hire path emits 0 rows due to auto-enrollment gating). All decisions resolved:
- Fix in the main voluntary decision engine (not the auto-enrollment-coupled proactive path, not the
  broadly-consumed compensation model).
- Effective date = eligibility date (`hire_date + eligibility_waiting_days`) per spec clarification.
- Eligibility gating excludes not-yet-eligible new hires.
- Reuse existing dedup/`prior_year_enrollments` guard; add a permanent regression test.

No NEEDS CLARIFICATION markers remain.

## Phase 1: Design & Contracts

**Status**: ✅ Complete.

- [data-model.md](./data-model.md) — logical new-hire candidate entity, column-contract change
  (effective date), validation rules VR-1…VR-5. No schema migration.
- [contracts/enrollment-model-contract.md](./contracts/enrollment-model-contract.md) — five contracts
  (candidate population, hire-year events, snapshot participation, regression test, determinism) with
  FR/SC traceability.
- [quickstart.md](./quickstart.md) — reproduce the defect and validate the fix end-to-end.

**Post-design Constitution re-check**: PASS — the design adds no new modules beyond one test, keeps
dependencies upstream-only, and preserves determinism and the immutability guard.

## Phase 2: Planning Approach (executed by /speckit.tasks)

The `/speckit.tasks` command will generate dependency-ordered tasks. Expected shape (test-first):

1. **Regression test first (Red)**: add `test_new_hire_voluntary_enrollment_hire_year.sql`
   (`tag:data_quality`) + pytest assertions encoding Contracts 1–5; confirm they FAIL on current code.
2. **Core fix**: widen `int_voluntary_enrollment_decision` candidate population to include current-year
   eligible new hires; set `proposed_effective_date` = eligibility date for them.
3. **Verify integration**: confirm `int_enrollment_events` emits exactly one hire-year voluntary event
   per new-hire enrollee and the `prior_year_enrollments`/dedup guard prevents Y+1 duplicates.
4. **Snapshot validation**: confirm hire-year `fct_workforce_snapshot` shows participation, deferral
   rate, and employer match for enrollees (leverages feature-095 propagation).
5. **Green + regression**: rerun `dbt test --select tag:data_quality` and `pytest -m "fast and events"`;
   validate determinism across two identical runs (SC-007).

## Complexity Tracking

No constitution violations — table intentionally omitted.
</content>
