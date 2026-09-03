# Implementation Plan: Per-Design Contribution Formula Families

**Branch**: `633-per-design-formula-families` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/633-per-design-formula-families/spec.md`

## Summary

Let each plan design in a run declare its own **match** formula family and its own **core** formula
family, so a grandfathered cohort keeps the contribution formulas of the design it sits on. Today
both are compile-time Jinja scalars, so exactly one shape of each is compiled into a run and a
two-design grandfathering scenario is impossible.

The two sides need different techniques, and this is the central finding of Phase 0:

- **Match** (`int_employee_match_calculations`) already computes each family as a *row-producing CTE*
  joined `INNER` to a tier relation, unioned into `all_matches`. Multi-family is a union over the
  families the run references, and the failure mode is a missing or duplicated row — loud, once a
  coverage guard exists.
- **Core** (`int_employer_core_contributions`) computes the rate as a *scalar expression*
  (`core_rate_expr`, lines 56-69) inlined into one `integration_basis` CTE, with `ELSE flat_rate`
  fallback in every band macro. There are no arms to count. A band gap silently pays the default
  rate, and overlapping graded bands duplicate rows that `rn = 1` then silently discards.

So core is not a second instance of the match problem. It needs family dispatch *and* the conversion
of two silent fallbacks into loud failures, *and* the per-design parameter work #632 deliberately
deferred. That is why this plan sequences core behind match rather than beside it.

## Technical Context

**Language/Version**: Python 3.11; dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated SQL)
**Primary Dependencies**: DuckDB 1.0.0, Pydantic v2, `planalign_orchestrator` pipeline
**Storage**: DuckDB event store; `int_employee_match_calculations`, `int_employer_core_contributions`, `fct_employer_match_events`, `fct_workforce_snapshot`; additive `run_metadata.design_formula_families_json`
**Testing**: pytest (`-m fast`, `-m integration`), dbt singular + schema tests; #632 parity harness as the canonical deterministic-equality vehicle
**Target Platform**: macOS / Linux, single-threaded dbt (`--threads 1`)
**Project Type**: Data pipeline — Jinja-templated SQL over a Python orchestrator
**Performance Goals**: single-design runs within 5% of baseline at 60k census (SC-005); default single-threaded 100k run without memory errors (SC-010)
**Constraints**: canonical equality across deterministic single-design columns (SC-001); no partial publication on guard failure (FR-005/006); isolated DBs for behavioral validation (SC-006)
**Scale/Scope**: 7.5k and 60k parity/performance census, 100k capacity census, multi-year horizons; 5 production models; 4 match families × 4 core families

### Resolved unknowns

All spec clarifications are resolved; see [spec.md](./spec.md) Clarifications and research.md D1-D12.
No `NEEDS CLARIFICATION` markers remain.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| I. Event Sourcing & Immutability | **Pass.** No event schema change, no mutation of `fct_yearly_events`. Reproducibility under seed is preserved; SC-001 is a stronger check than the principle requires. |
| II. Modular Architecture | **At risk — see Complexity Tracking.** Both models grow when families coexist. Mitigated by extracting arms into macro files so the model bodies shrink. No layer inversion: all reads stay staging → intermediate → marts. |
| III. Test-First Development | **Pass when task order is followed.** Config, parity, compiled-SQL, audit, and guard tests all fail before any family arm/rate extraction or dispatch implementation. The complete `pytest -m fast` suite is timed below 10 seconds before handoff. |
| IV. Enterprise Transparency | **Pass, and strengthened.** FR-012 records both families per design in canonical audit metadata; every formula-resolution diagnostic includes correlation ID, execution context, and a resolution hint. |
| V. Type-Safe Configuration | **Pass.** Both families and the core schedules are Pydantic-validated (FR-007, FR-017); no raw SQL table-name concatenation is introduced. |
| VI. Performance & Scalability | **Pass with two gates.** FR-008 excludes unreferenced families, the 60k comparison enforces the 5% regression boundary, and a separate 100k single-threaded full-horizon run proves no-memory-error capacity. Multi-design cost grows with families referenced; accepted and unbudgeted per spec Assumptions. |

**Post-Phase-1 re-check**: unchanged. The only risk carried forward is II, mitigated and tracked below.

## Project Structure

### Documentation (this feature)

```text
specs/633-per-design-formula-families/
├── plan.md              # This file
├── research.md          # Phase 0 — D1-D12
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1 — validation procedure
├── contracts/
│   ├── audit-metadata.md      # canonical persisted family map
│   ├── config-schema.md       # Pydantic surface
│   └── relation-contracts.md  # design-keyed dbt relations
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
dbt/
├── models/intermediate/
│   ├── int_employee_match_calculations.sql      # match arms → union, + coverage guard
│   ├── int_employer_core_contributions.sql      # core family dispatch, + fallback guard
│   ├── events/int_deferral_match_response_events.sql # per-design family resolution
│   ├── int_voluntary_enrollment_decision.sql    # per-design family resolution
│   └── int_proactive_voluntary_enrollment.sql   # per-design family resolution
├── macros/
│   ├── match_family_arms/                       # NEW — one file per match family
│   ├── core_family_rates/                       # NEW — one file per core family
│   ├── get_plan_design_parameters.sql           # + core family, integration cols
│   ├── get_plan_design_match_tiers.sql
│   ├── get_plan_design_core_graded_schedule.sql
│   ├── get_plan_design_core_age_schedule.sql    # NEW — closes DBT_VAR_DEFERRED
│   └── get_plan_design_core_points_schedule.sql # NEW — closes DBT_VAR_DEFERRED
└── tests/data_quality/
    ├── test_match_formula_arm_coverage.sql      # NEW
    └── test_core_rate_band_resolution.sql       # NEW

planalign_orchestrator/config/
├── export.py            # DBT_VAR_PER_DESIGN / DBT_VAR_DEFERRED reclassification
└── plan_design.py       # per-design match_family, core_family, integration settings

planalign_orchestrator/
└── run_metadata.py      # canonical design_formula_families_json audit map

tests/
├── test_dbt_var_coverage.py                          # disposition assertions
├── test_run_metadata.py                              # family-map audit contract
└── integration/
    └── test_plan_design_formula_families.py          # NEW — parity + multi-family
```

**Structure Decision**: no new project or package. The feature is a change in shape of existing dbt
models plus a widening of the existing per-design config surface. The one new structural element is
the two macro directories that hold the extracted family arms, which exist so that Principle II's
module-size guidance is respected rather than violated.

## Phase Sequencing

Sequenced so each phase is independently reviewable and canonical parity is re-verified at every step.

| Phase | Content | Gate |
|---|---|---|
| **0. Baselines and red tests** | Capture pre-change baselines at 7.5k and 60k, then write config, parity, compiled-SQL, audit, and guard tests before implementation. | Baselines stored; focused tests fail for the intended missing behavior. |
| **1. Match dispatch** | Extract match arms to macros and compile only referenced families. | Canonical parity for all 4 match families. |
| **2. Match multi-family** | Two-design, two-match-family run; hand-verify ≥10 employees per design. | SC-002 match half. |
| **3. Core parameters** | Close `DBT_VAR_DEFERRED`: design-keyed age and points core schedule relations; reclassify the two vars; FR-017 rejection. | SC-008; canonical parity for all 4 core families. |
| **4. Core dispatch** | Per-design `core_formula_family`; convert `core_rate_expr` to a CASE over referenced families reading design-keyed relations. | SC-001 for all 4 core families. |
| **5. Resolution guards** | Add the exactly-one match-arm guard (D3); convert the core `ELSE flat_rate` fallback into a loud failure (D8); add `plan_design_id` to the dedup key; and assert band multiplicity before dedup (D11, FR-019). | SC-003 on both sides; full diagnostic contract. |
| **6. Integration per-design** | Move the four `employer_core_integration_*` vars into the design relation (FR-018). | Canonical parity with integration on and off. |
| **7. Cross-cutting** | FR-003 family resolution in the three enrollment/response models; FR-012 audit metadata. | Full matrix green. |

**Natural review split point**: phases 0-2 isolate the match-dispatch half and are reviewable alone;
phases 3-7 add core and the shared release guards. If the change is too large for one review, stack a
second PR at the phase-2 boundary. The first PR is not independently releasable until the match guard
and complete P1 acceptance gates are present.

## Validation Strategy

Three tiers, because SC-001 asks for 7.5k/60k, the constitution requires 100k capacity, and the pytest suite must stay fast:

- **In-suite**: extend the #632 parity harness (`tests/integration/test_plan_design_parameters.py:45-60`,
  `EXCEPT ALL` both directions + ordered row-hash, `:218-256`) at census 40 and 149, as
  `tests/integration/test_plan_design_formula_families.py`. Covers all 4 match and all 4 core
  families single-design, plus multi-design combinations.
- **Out-of-band, pre-merge**: full multi-year runs at 7.5k and 60k in isolated DuckDB files, one per
  family per side, baseline vs. branch, `EXCEPT ALL` both directions, timed for SC-005. Procedure in
  [quickstart.md](./quickstart.md).
- **Capacity**: one default single-threaded full multi-year run at 100k in its own isolated DuckDB
  file, with peak memory and completion status recorded for SC-010.

The SC-004 matrix is 4 match × 4 core = 16 single-design cells plus the multi-design pairs. Not every
cell needs a 60k run: the in-suite tier covers the full matrix structurally; the out-of-band tier runs
the 8 single-family cells and the two-design grandfathering scenario.

Never validate in `dbt/simulation.duckdb`. Every run uses `DATABASE_PATH` or
`planalign batch --scenarios ... --clean`.

Canonical parity compares all deterministic columns with `EXCEPT ALL` in both directions and an
ordered row hash. `created_at` is the only currently permitted exclusion; any additional exclusion
requires an explicit spec change rather than an ad hoc comparison edit.

Before implementation handoff, time the complete `pytest -m fast` suite and require it to finish in
under 10 seconds. Test data is sourced from checked-in builders/files under `tests/fixtures/`, including
the inputs rendered into dbt relation and guard tests.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `int_employee_match_calculations.sql` and `int_employer_core_contributions.sql` grow when multiple families coexist, pressing on Principle II's ~600-line guidance | Multiple families must coexist in one compiled query; that is the entire feature | Keeping one family per run is the status quo the feature exists to remove. Mitigation: arms move into `macros/match_family_arms/` and `macros/core_family_rates/`, so each model body becomes a compile-time loop over referenced families plus shared cap/guard/final-select logic — net smaller than today for single-design runs. |
| The in-model coverage guard aborts via a deliberate runtime cast failure | dbt SQL cannot raise, and the VALIDATION stage runs *after* `fct_workforce_snapshot` is built (`workflow.py:241-247`), so a dbt test alone lets wrong numbers reach published tables — violating FR-005 | A dbt singular test is kept as a second net but cannot satisfy "no partial results published" on its own. See research.md D3. |
| Two different dispatch mechanisms — union-of-arms for match, CASE-over-families for core | The two models compute at different grains: match arms produce rows and aggregate, core produces one rate per employee-row | Forcing core into the match union shape would restructure a model that has no correctness problem with its current shape, enlarging the canonical-parity risk surface for no behavioural gain. See research.md D7. |
| This feature absorbs the `DBT_VAR_DEFERRED` scope #632 deliberately left open | Per-design core *family* selection is meaningless while two of four core families cannot carry per-design *rates* | Shipping core family selection over a half-per-design parameter layer would make two of the four families silently run-global — exactly the silent-wrong-number class this feature exists to eliminate. |
