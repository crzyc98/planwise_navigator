# Implementation Plan: Post-Termination Event Integrity

**Branch**: `112-post-termination-integrity` | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/112-post-termination-integrity/spec.md`

## Summary

The supplied archived run contains 459 genuine post-termination events: 315 eligibility events, 118 enrollment events, and 26 `enrollment_change` (opt-out) events. Of these, 451 belong to same-year new hires and eight to experienced employees. The affected generators treat employees as active at the start of the year or at hire but do not compare candidate event dates with termination dates already generated earlier in the same pipeline stage.

The boundary relation is current-year-scoped by design: prior-year terminated employees are already excluded from every affected generator's state source (generators read start-of-year active workforce state and current-year hires, per research.md), so FR-008's later-year prevention is satisfied by existing state filtering and is protected by regression tests (T011 prior-year cases, T024 non-resurrection) rather than a new filter. If those tests fail against the pre-correction baseline for a prior-year cohort, the boundary relation extends to lifetime-earliest termination within scenario/plan scope before generator consumers are modified.

Add one shared, ephemeral current-year termination-boundary model sourced from experienced and new-hire termination events. Apply its earliest termination date inside eligibility, enrollment, promotion, merit, and configurable deferral generators, retaining events on or before termination and filtering enrollment candidates before category prioritization. Keep the authoritative fact union free of a blanket cleanup so defective generators remain observable. Strengthen the independent validation rule and dbt integrity test to use the earliest termination across years within scenario/plan scope, preserve exact error counts in provenance, and validate the complete 2026–2030 behavior twice in isolated databases.

## Technical Context

**Language/Version**: Python >=3.11; SQL/Jinja compatible with dbt Core 1.8.8
**Primary Dependencies**: Existing PlanAlign orchestrator, dbt Core 1.8.8, dbt DuckDB 1.8.1, DuckDB 1.0.0, Pydantic v2 provenance models, and pytest 7.4; no new dependency
**Storage**: Existing scenario-isolated DuckDB event tables plus one ephemeral intermediate termination-boundary relation; no new persisted table, public mart, archive format, or configuration field
**Testing**: Fast pytest rule/provenance tests, dbt compile and singular integrity tests, synthetic isolated DuckDB integration fixtures, two complete isolated 2026–2030 simulations, and one copied-workspace Studio provenance acceptance run
**Target Platform**: Local/on-premises PlanAlign CLI and Studio simulation engine on supported macOS and Linux workstations
**Project Type**: Event-sourced simulation pipeline with dbt transformations and Python orchestration/validation
**Performance Goals**: Corrected equivalent five-year simulation remains within 10% of the 183.42-second archived baseline under comparable conditions; set-based cutoff joins remain suitable for 100K+ employees
**Constraints**: Deterministic outputs; immutable authoritative events and archived reports; no employee-level diagnostics outside the isolated database; same-day events retained; no inferred rehire; no `int_*` read of current-year `fct_*`; dbt `--threads 1`; behavioral validation never writes to `dbt/simulation.duckdb` or a live/archive database
**Scale/Scope**: Five affected years, 6,764–7,841 annual workforce, 459 baseline violations across three event types, all current supported SQL event-generation paths, and regression protection for the 100K+ employee target

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Plan evidence |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | Invalid candidates are removed before authoritative event creation; no existing event or archive is updated. Identical inputs and seed are executed twice and compared using deterministic aggregates. |
| II. Modular Architecture | PASS | One focused ephemeral boundary relation is consumed by event generators in the existing EVENT_GENERATION direction. No `int_*` model reads the current-year fact, and accumulator/fact ordering is unchanged. |
| III. Test-First Development | PASS | Work begins with synthetic rule, producer, provenance-disposition, and singular integrity failures, then proceeds to isolated multi-year acceptance and determinism checks. |
| IV. Enterprise Transparency | PASS | Privacy-safe root-cause aggregates reconcile all 459 baseline records. Validation remains independent and error-severity failures continue into the tamper-evident run report with exact counts. |
| V. Type-Safe Configuration | PASS | No configuration field is added. Existing typed configuration remains authoritative; legacy Polars settings continue resolving to the supported SQL mode. SQL dependencies use explicit `ref()` relationships. |
| VI. Performance & Scalability | PASS | A year-filtered set-based aggregation and joins replace repeated ad hoc logic. No per-employee Python loop, new subprocess, or persisted registry is introduced; full-run regression is capped at 10%. |

**Pre-design gate result**: PASS. No constitutional exception is required.

**Post-Phase-1 re-check**: PASS. The data model keeps termination boundaries internal and ephemeral, the design fixes producers rather than masking validation, the external CLI/Studio/provenance contracts remain unchanged, and the quickstart writes only to disposable databases and copied workspaces.

## Project Structure

### Documentation (this feature)

```text
specs/112-post-termination-integrity/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── tasks.md                         # Created by /speckit.tasks, not this command
```

No external interface contract is added. This feature changes an internal event-stream invariant while preserving the existing CLI, Studio API, archive, and provenance-report schemas.

### Source Code (repository root)

```text
dbt/
├── models/intermediate/
│   ├── events/
│   │   ├── int_employee_termination_dates.sql       # NEW: shared earliest current-year cutoff
│   │   ├── int_eligibility_events.sql               # MODIFY: date-bound eligibility candidates
│   │   ├── int_merit_events.sql                     # MODIFY: consume shared cutoff
│   │   ├── int_promotion_events.sql                 # MODIFY: date-bound promotions
│   │   └── int_deferral_rate_escalation_events.sql  # MODIFY: date-bound escalation
│   ├── int_enrollment_events.sql                    # MODIFY: filter candidates before deduplication
│   └── schema.yml                                   # MODIFY: model/column contracts and tests
└── tests/data_quality/
    └── test_integrity_violations.sql                # MODIFY: earliest scoped termination semantics

planalign_orchestrator/
├── validation.py                                    # MODIFY: lifetime earliest-term, scoped yearly check
└── pipeline/
    ├── workflow.py                                  # MODIFY: explicit dependency/order parity
    └── event_generation_executor.py                 # MODIFY: explicit model-list parity

planalign_api/services/provenance/
└── capture.py                                       # MODIFY: aggregate yearly validation disposition

tests/
├── fixtures/
│   └── post_termination_events.py                   # NEW: synthetic, PII-free event cases
├── integration/
│   ├── test_post_termination_event_integrity.py     # NEW: producer and multi-year behavior
│   └── test_run_provenance_report.py                # MODIFY: corrected archived-run PASS/0 case
├── test_validation_framework.py                     # MODIFY: full sequence semantics
├── test_telemetry_emitter.py                        # MODIFY: exact safe counts remain stable
└── unit/
    ├── test_provenance_capture.py                   # MODIFY: monotonic overall disposition
    └── orchestrator/
        ├── test_config_export.py                    # MODIFY: legacy mode resolves to SQL
        └── test_post_termination_workflow.py        # NEW: workflow/executor ordering parity
```

**Structure Decision**: Preserve the existing dbt/orchestrator boundary. Termination selection remains earlier in EVENT_GENERATION; a small ephemeral model normalizes both termination sources; every affected event producer applies the boundary before emitting rows; `fct_yearly_events` remains a transparent union; Python and dbt validators independently inspect the resulting authoritative stream. This avoids circular dependencies, late destructive cleanup, duplicated cutoff SQL, and a new persisted state table.

**Correction boundary**: Contribution and deferral-state events are downstream derivations of enrollment/eligibility state, so correcting those producers corrects them transitively; no contribution generator is modified. The independent validator (T006) and non-resurrection assertions (T024) inspect the full authoritative stream, so any contribution-path violation surviving the producer fixes would still fail validation rather than pass silently. T012/T020/T021 also fix an observed workflow/executor model-list drift (eligibility and match-response entries) opportunistically; this parity fix is expected to produce no event-aggregate delta and is called out here so FR-015's explainable-delta audit accounts for it.

## Complexity Tracking

No constitution violations; table intentionally omitted.
