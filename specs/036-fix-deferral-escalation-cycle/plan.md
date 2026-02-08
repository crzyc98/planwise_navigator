# Implementation Plan: Fix Deferral Rate Escalation Circular Dependency

**Branch**: `036-fix-deferral-escalation-cycle` | **Date**: 2026-02-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/036-fix-deferral-escalation-cycle/spec.md`

## Summary

The `int_deferral_rate_escalation_events` model is effectively disabled: the `.disabled` version returns empty sets due to a circular dependency with `fct_workforce_snapshot`, and the active `.sql` version (materialized as ephemeral) uses a direct table reference to break the cycle but has never been validated end-to-end.

This plan activates the existing corrected implementation by:
1. Validating the ephemeral model compiles and produces escalation events
2. Ensuring the `int_deferral_rate_state_accumulator_v2` temporal accumulation pattern works with real escalation data
3. Cleaning up the disabled model and placeholder stubs
4. Adding real tests to replace the placeholders

## Technical Context

**Language/Version**: Python 3.11, SQL (DuckDB 1.0.0 via dbt-core 1.8.8 + dbt-duckdb 1.8.1)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic v2.7.4, planalign_orchestrator
**Storage**: DuckDB (`dbt/simulation.duckdb`) - immutable event store
**Testing**: dbt tests (schema + singular), pytest (unit + integration)
**Target Platform**: Linux server / work laptop (single-threaded default)
**Project Type**: Single project (dbt + Python orchestrator)
**Performance Goals**: Escalation model executes in <2 seconds per simulation year for 100K+ employees
**Constraints**: No circular dependencies in dbt DAG; deterministic output for same seed; `--threads 1` default
**Scale/Scope**: ~100K employees, 5-year simulation horizon, ~7 dbt models affected

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Event Sourcing & Immutability | PASS | Escalation events are appended to `fct_yearly_events` via UNION ALL. Events are never modified. Deterministic output guaranteed by seed-based config. |
| II. Modular Architecture | PASS | Escalation model is a single-purpose ephemeral model (~293 lines). No circular dependencies introduced. Staging → intermediate → marts layer ordering respected. |
| III. Test-First Development | PASS | Plan includes replacing placeholder tests with real validation tests before considering the feature "enabled". |
| IV. Enterprise Transparency | PASS | Escalation events include audit trail fields (previous rate, new rate, escalation rate, eligibility details). State accumulator tracks lineage via `rate_source` column. |
| V. Type-Safe Configuration | PASS | Configuration flows through Pydantic models in `config/export.py` to typed dbt variables. Model uses `{{ ref() }}` for all standard dependencies; only the cycle-breaking reference uses direct table reference (documented and intentional). |
| VI. Performance & Scalability | PASS | Ephemeral materialization avoids table creation overhead. DuckDB vectorized processing with early year filtering. Target <2s execution per year. |

**dbt Development Patterns check**:
- No circular dependencies: PASS (direct table reference for `int_deferral_rate_state_accumulator_v2` breaks the cycle)
- Year filtering in heavy models: PASS (all CTEs filter by `simulation_year`)
- `--threads 1` default: PASS (orchestrator default)

## Project Structure

### Documentation (this feature)

```text
specs/036-fix-deferral-escalation-cycle/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
dbt/
├── models/
│   ├── intermediate/
│   │   ├── events/
│   │   │   ├── int_deferral_rate_escalation_events.sql        # MODIFY: validate & potentially adjust materialization
│   │   │   └── int_deferral_rate_escalation_events.sql.disabled  # DELETE: obsolete
│   │   ├── int_deferral_rate_state_accumulator_v2.sql         # VERIFY: works with real escalation data
│   │   ├── int_deferral_escalation_state_accumulator.sql      # EVALUATE: orphaned legacy model
│   │   ├── int_deferral_rate_state_accumulator.sql            # EVALUATE: orphaned legacy model
│   │   └── schema.yml                                         # MODIFY: re-enable escalation schema tests
│   ├── marts/
│   │   ├── fct_yearly_events.sql                              # VERIFY: UNION ALL leg receives real events
│   │   ├── fct_workforce_snapshot.sql                         # VERIFY: downstream reads escalation state
│   │   └── data_quality/
│   │       └── dq_deferral_escalation_validation.sql          # MODIFY: replace placeholder with real validation
│   └── tests/
│       ├── data_quality/
│       │   └── test_deferral_escalation.sql                   # MODIFY: replace placeholder with real test
│       └── analysis/
│           └── test_escalation_bug_fix.sql                    # VERIFY: existing bug-fix tests still pass
├── dbt_project.yml                                            # VERIFY: no var conflicts
└── simulation.duckdb                                          # Runtime artifact

planalign_orchestrator/
├── pipeline/
│   ├── workflow.py                                            # VERIFY: escalation model in correct stage position
│   └── year_executor.py                                       # VERIFY: full-refresh handling for escalation model
├── config/
│   └── export.py                                              # VERIFY: config vars exported correctly
└── registries.py                                              # VERIFY: DeferralEscalationRegistry post-year update

config/
└── simulation_config.yaml                                     # VERIFY: escalation config enabled and correct

tests/
└── test_escalation_events.py                                  # CREATE: pytest integration test
```

**Structure Decision**: This is a fix/enablement within the existing dbt + orchestrator architecture. No new directories or packages are created. Changes are confined to existing models, tests, and configuration.

## Complexity Tracking

No constitution violations to justify. All changes follow existing patterns.

## Implementation Approach

### Key Insight: The Fix Already Exists

The codebase already contains two versions of the escalation model:

1. **`.sql.disabled`** (256 lines, `materialized='table'`): Original implementation that references `fct_workforce_snapshot` for prior-year state, causing the circular dependency. Returns empty result sets via `WHERE FALSE`.

2. **`.sql`** (293 lines, `materialized='ephemeral'`): Corrected implementation that:
   - Uses `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` (direct table reference) for Year 2+ prior-year rates (line 160)
   - Uses `int_enrollment_events` and `int_synthetic_baseline_enrollment_events` for initial enrollment rates (lines 88-117)
   - Uses `int_employee_compensation_by_year` for enrollment status (lines 120-130)
   - Has proper eligibility checks, cap enforcement, and timing logic

**The primary work is validation, testing, and cleanup** -- not reimplementation.

### Dependency Chain (Validated)

```
EVENT_GENERATION stage (ordered):
  ...
  int_enrollment_events
  int_deferral_rate_escalation_events (ephemeral, last in stage)

STATE_ACCUMULATION stage (ordered):
  fct_yearly_events (consumes escalation events via UNION ALL)
  ...
  int_deferral_rate_state_accumulator_v2 (consumes escalation events, provides Year N-1 state)
  int_deferral_escalation_state_accumulator (legacy, orphaned)
  ...
  fct_workforce_snapshot (reads from accumulator, NOT from escalation events directly)
```

**Cycle-breaking mechanism**: `int_deferral_rate_escalation_events` reads Year N-1 state from `int_deferral_rate_state_accumulator_v2` via direct table reference (`{{ target.schema }}.int_deferral_rate_state_accumulator_v2`). This means dbt's dependency graph does not see the dependency, so no cycle is created. The orchestrator ensures correct execution order by placing escalation events in EVENT_GENERATION (which runs before STATE_ACCUMULATION where the accumulator is built).

**Risk**: The direct table reference means dbt cannot enforce that the accumulator is built before the escalation model. However, this is mitigated by:
- Year 1: No prior-year state needed (handled by `{% if simulation_year == start_year %}` branch)
- Year 2+: Orchestrator ensures STATE_ACCUMULATION from Year N-1 completes before EVENT_GENERATION of Year N
- The `year_executor.py` already special-cases this model for `--full-refresh`

### Implementation Phases

**Phase A: Validate & Enable (P1 - Core Fix)**
1. Verify `dbt compile` succeeds with the existing `.sql` model
2. Run a single-year simulation with escalation enabled and confirm non-zero events
3. Verify `fct_yearly_events` receives escalation events
4. Remove the `.disabled` file (it's obsolete)
5. Re-enable the commented-out schema tests in `intermediate/schema.yml`

**Phase B: Multi-Year Validation (P2 - State Accumulation)**
1. Run a 3-year simulation and verify rate accumulation (6% -> 7% -> 8%)
2. Verify `int_deferral_rate_state_accumulator_v2` correctly carries forward escalated rates
3. Verify cap enforcement across years (stops at 10%)
4. Verify new hires enrolled mid-simulation receive escalation after delay period

**Phase C: Test Infrastructure (P3 - Regression Protection)**
1. Replace `dq_deferral_escalation_validation.sql` placeholder with real validation queries
2. Replace `test_deferral_escalation.sql` placeholder with real assertions
3. Add a pytest integration test that runs a simulation and checks escalation event counts
4. Verify existing bug-fix tests (`test_escalation_bug_fix.sql`) still pass

**Phase D: Cleanup (Housekeeping)**
1. Delete `.disabled` file
2. Evaluate orphaned legacy models (`int_deferral_escalation_state_accumulator`, `int_deferral_rate_state_accumulator`) for removal
3. Update schema.yml to document the escalation model properly

## Constitution Re-Check (Post-Design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No design changes affect immutability. Escalation events flow into `fct_yearly_events` unchanged. |
| II. Modular Architecture | PASS | No new modules created. Existing model (~293 lines) is within the ~600 line limit. Direct table reference is the only non-standard pattern, documented and justified. |
| III. Test-First Development | PASS | Phase C (test infrastructure) replaces all placeholder tests with real assertions. pytest integration test added. |
| IV. Enterprise Transparency | PASS | Audit trail maintained. `rate_source` column in accumulator tracks data lineage. |
| V. Type-Safe Configuration | PASS | All configuration flows through existing Pydantic-validated export pipeline. No new untyped references. |
| VI. Performance & Scalability | PASS | Ephemeral materialization means no additional table scans. Year filtering in all CTEs. |

**Post-design gate**: PASS. No new violations introduced.
