# Implementation Plan: Voluntary Enrollment Events Reflected in Annual Snapshot

**Branch**: `095-fix-enrollment-snapshot` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/095-fix-enrollment-snapshot/spec.md`

## Summary

Voluntary enrollment events are generated correctly and reach `fct_yearly_events`, but a subset of voluntary enrollees do not appear as participating (with their deferral rate and employer match) in `fct_workforce_snapshot`. Root cause has been confirmed against live data: `int_deferral_rate_state_accumulator` drops employees who were present-but-unenrolled in a prior simulation year and then newly enroll, because its subsequent-year `is_enrolled_flag` logic — `COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false)` — returns the stale prior-year `false` instead of recognizing the current-year new enrollment. These employees are filtered out of the accumulator entirely (`WHERE ... is_enrolled_flag = true`), so every downstream model that reads the accumulator (contributions → match, and the snapshot's participation/deferral fields) treats them as non-participants with a 0% rate.

**Technical approach**: Fix the enrollment-flag precedence in the accumulator's subsequent-year branch so a current-year enrollment (`ne`) overrides a stale prior-year unenrolled flag, and an opt-out (`oo`) overrides both. Because contributions, match, and the snapshot all derive from this one accumulator, the single fix propagates to all three reported symptoms (deferral rate, participation status, match). Add a permanent dbt data-quality test that fails the build when a voluntary enrollee is missing from snapshot participation (FR-010). The same-year enroll-then-opt-out *prorated contribution* refinement (FR-008) is scoped separately because the contribution model currently prorates by employment window only, not by enrollment window.

## Technical Context

**Language/Version**: SQL (dbt-core 1.8.8, dbt-duckdb 1.8.1), Python 3.11 (orchestrator + tests)
**Primary Dependencies**: DuckDB 1.0.0, dbt-duckdb 1.8.1; existing temporal-accumulator pattern (E023)
**Storage**: DuckDB (`dbt/simulation.duckdb`) — no schema migration; incremental accumulator model, fix is logic-only
**Testing**: dbt schema/data tests (`dbt test`), pytest (`pytest -m fast`) for any orchestrator-level assertions
**Target Platform**: On-prem analytics server / work-laptop (single-threaded dbt, `--threads 1`)
**Project Type**: Event-sourced workforce simulation (dbt models + Python orchestrator) — single project
**Performance Goals**: No regression to STATE_ACCUMULATION stage runtime; accumulator remains incremental delete+insert by year
**Constraints**: MUST NOT `--full-refresh` temporal accumulators mid-simulation; fix must be backward-compatible with existing accumulator output schema; deterministic given the same seed
**Scale/Scope**: 100K+ employee records; change is confined to one model's subsequent-year CASE/WHERE logic plus one new test

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | No event data is altered; events already exist correctly in `fct_yearly_events`. Fix only corrects derived state in an accumulator. Determinism preserved (same seed → same output). |
| II. Modular Architecture | ✅ Pass | Change is localized to `int_deferral_rate_state_accumulator` (intermediate layer). No new circular dependency: it already legitimately reads `fct_yearly_events` (sanctioned exception) and its own `{{ this }}` prior-year rows. No layer reversal introduced. |
| III. Test-First Development | ✅ Pass | A failing dbt data-quality test reproducing the 2026 voluntary-enrollee drop is written before the model fix (Red → Green). Test becomes the permanent FR-010 guard. |
| IV. Enterprise Transparency | ✅ Pass | The accumulator's `rate_source` audit column already distinguishes `enrollment_event` vs `carried_forward`; fix keeps it accurate. Test failure rows identify offending employee/year. |
| V. Type-Safe Configuration | ✅ Pass | No config/schema change. SQL uses `{{ ref() }}` exclusively; no raw string table refs. |
| VI. Performance & Scalability | ✅ Pass | Logic-only change to existing CASE/WHERE; no new joins or scans. Stays incremental, single-threaded default. |

**Result**: PASS — no violations, Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/095-fix-enrollment-snapshot/
├── plan.md              # This file (/speckit.plan)
├── research.md          # Phase 0 output — root cause + decisions
├── data-model.md        # Phase 1 output — accumulator state semantics
├── quickstart.md        # Phase 1 output — reproduce, fix, verify
├── contracts/
│   └── data-quality-tests.md   # dbt test contracts (FR-009/FR-010 reconciliation)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
dbt/
├── models/
│   ├── intermediate/
│   │   ├── int_deferral_rate_state_accumulator.sql   # PRIMARY FIX (subsequent-year is_enrolled_flag precedence)
│   │   └── schema.yml                                # Add/extend tests for accumulator participation
│   └── marts/
│       └── data_quality/
│           └── dq_voluntary_enrollment_snapshot.sql  # NEW: reconciliation test model (FR-009/FR-010)
└── ...

tests/
└── test_voluntary_enrollment_snapshot.py             # OPTIONAL: pytest integration assertion over a built DB
```

**Structure Decision**: Single-project dbt + orchestrator layout (existing). The fix lives entirely in the intermediate layer (`int_deferral_rate_state_accumulator.sql`); the permanent regression guard is a new data-quality model under `marts/data_quality/` registered as a dbt test, consistent with the E080 "validation model → dbt test" pattern. No frontend, API, or config changes.

## Phasing

- **Phase A (P1 — core fix, FR-001/002/003/004/005/006/007)**: Correct `is_enrolled_flag` precedence in the accumulator's subsequent-year branch so new enrollment overrides stale prior-year unenrolled state (opt-out still wins). Verify deferral rate, participation status, and match populate for the 2026 voluntary cohort and that carry-forward across years (FR-007) is unaffected.
- **Phase B (P1 — regression guard, FR-009/FR-010)**: Add the permanent dbt data-quality test reconciling voluntary enrollees (net of opt-outs) to snapshot participation; it must fail on the pre-fix database and pass on the post-fix database.
- **Phase C (P2/edge — FR-008 prorated window)**: Same-year enroll-then-opt-out contribution/match proration by enrollment window. Scoped separately and flagged for design review because the contribution model currently prorates by employment window only. Year-end participation status (opt-out wins) is already correct after Phase A; only the *partial-window contribution crediting* is outstanding.

## Complexity Tracking

> No constitution violations. Section intentionally left empty.
