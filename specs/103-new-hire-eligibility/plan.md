# Implementation Plan: Configurable New-Hire Eligibility Rate + Optional Per-Employee Census Eligibility

**Branch**: `103-new-hire-eligibility` | **Date**: 2026-06-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/103-new-hire-eligibility/spec.md`

## Summary

Let analysts model a sub-population of DC-plan-**ineligible** employees so participation, contributions, and employer match are suppressed for them. Three backward-compatible inputs, all defaulting to "everyone eligible":

1. **Analyst dial** — `new_hire_ineligible_pct` (0.0–1.0, default 0.0) marks a deterministic, reproducible fraction of each year's new-hire cohort ineligible.
2. **Optional census column** — `eligibility_override` (BOOLEAN, nullable) on `stg_census_data`, scaffolded with the same absent-column-defaults-to-NULL pattern as `auto_escalation_opt_out` (#316).
3. **Census matching** — `new_hire_eligibility_match_census` (bool, default false); when true the effective new-hire ineligible rate is computed from the census-observed ineligible share (ineligible ÷ **total census headcount**) instead of the dial's literal value.

**Technical approach**: Resolve a single per-employee `is_plan_ineligible_override` in one new intermediate model (`int_plan_eligibility_override`) — static census attribute for `EMP_*` read **directly from `stg_census_data`** (multi-year-correct, not via the prior-year snapshot), deterministic hash for `NH_*`. Then fold that flag into the existing eligibility gate in `int_enrollment_events`, `int_voluntary_enrollment_decision`, and `int_proactive_voluntary_enrollment` (`is_eligible AND NOT is_plan_ineligible_override`), and suppress the `DC_PLAN_ELIGIBILITY` event in `int_eligibility_events` for overridden-ineligible employees (annotating reason/source). Contributions and match cascade automatically from "never enrolled" — no changes there. Config flows through Pydantic → `to_dbt_vars` like other enrollment vars.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator/config), SQL via dbt-core 1.8.8 / dbt-duckdb 1.8.1; TypeScript/React (Studio UI, follow-up)
**Primary Dependencies**: DuckDB 1.0.0 (storage/engine), Pydantic v2 (config validation), FastAPI (workspace config API), React/Vite + Tailwind (Studio)
**Storage**: DuckDB (`dbt/simulation.duckdb` shared dev; validate in isolated DBs). No new tables — eligibility suppression flows through existing `int_*` models, `fct_yearly_events`, `fct_workforce_snapshot`
**Testing**: `pytest -m fast` (config validation), dbt schema tests (`not_null`/`accepted_values`), dbt data tests (ineligible → zero enrollment events), isolated multi-year `planalign simulate` for regression + behavior
**Target Platform**: On-prem analytics server / work laptop (single-threaded default)
**Project Type**: Data simulation pipeline (dbt + Python orchestrator + optional Studio web UI)
**Performance Goals**: No regression to existing simulation runtime; override resolution is one lightweight model + a hash expression; 100K+ employees without memory errors
**Constraints**: Single-threaded (`--threads 1`) default; deterministic/reproducible given seed; byte-for-byte identical output under default config
**Scale/Scope**: Multi-year workforce simulations; census populations to 100K+ employees

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance |
|-----------|-----------|
| **I. Event Sourcing & Immutability** | ✅ Suppression removes events that would never be valid; no event mutation. `DC_PLAN_ELIGIBILITY` suppression annotated with reason/source for audit. Deterministic hash keeps reproducibility given seed. |
| **II. Modular Architecture** | ✅ One new small `int_plan_eligibility_override` model with a single responsibility (resolve the flag once); gate folded into existing models via a shared macro. Respects staging → intermediate → marts. Reads `stg_census_data` (staging) and `int_hiring_events` (intermediate) — no reverse deps. |
| **III. Test-First Development** | ✅ dbt schema/data tests + fast config-validation tests authored before model edits; regression double-run per acceptance criteria. |
| **IV. Enterprise Transparency** | ✅ Suppressed eligibility annotated with `reason='ineligible_override'` + `source` in `event_details`; config version-controlled. |
| **V. Type-Safe Configuration** | ✅ New fields added to Pydantic `EligibilitySettings` with range validators (`ge=0, le=1`); exported via `to_dbt_vars`; SQL uses `{{ ref() }}`/`{{ var() }}`, no string concat. |
| **VI. Performance & Scalability** | ✅ Single extra lightweight model; no new heavy joins; filtered by `simulation_year`. Default path unchanged → no regression. |

**Result**: PASS. No violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/103-new-hire-eligibility/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (config-vars, census-schema, dbt-event)
│   ├── config-vars.md
│   ├── census-schema.md
│   └── dbt-event-contract.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
config/
└── simulation_config.yaml                       # add eligibility.new_hire_ineligible_pct + new_hire_eligibility_match_census

planalign_orchestrator/config/
├── workforce.py                                  # EligibilitySettings: + new_hire_ineligible_pct, new_hire_eligibility_match_census
└── export.py                                     # to_dbt_vars: export the two new vars

config/events/dc_plan.py                          # EligibilityPayload.reason enum: + "ineligible_override"; optional source (optional/parity)

dbt/models/staging/
├── stg_census_data.sql                           # schema-scaffold + COALESCE for eligibility_override (BOOLEAN, NULL→eligible)
└── schema.yml                                     # tests on eligibility_override (not_null after coalesce? accepted_values)

dbt/models/intermediate/
├── int_plan_eligibility_override.sql             # NEW: resolve is_plan_ineligible_override once (EMP_* census, NH_* hash, census-match rate)
├── int_enrollment_events.sql                     # gate: is_eligible AND NOT is_plan_ineligible_override
├── int_voluntary_enrollment_decision.sql         # same gate
├── int_proactive_voluntary_enrollment.sql        # same gate
├── events/int_eligibility_events.sql             # suppress DC_PLAN_ELIGIBILITY for overridden-ineligible; annotate reason/source
└── schema.yml                                     # document/test new model + flag

dbt/macros/
└── resolve_plan_ineligible_override.sql          # NEW (optional): reusable hash + join expression

dbt/tests/
└── assert_ineligible_no_enrollment.sql           # NEW: ineligible employees have zero enrollment events in fct_yearly_events

tests/
└── test_new_hire_eligibility_config.py           # NEW fast: Pydantic validation + to_dbt_vars export

planalign_studio/ (follow-up)
└── components/...                                 # DC-plan card: slider + "match census eligibility" toggle + ~X/year helper
```

**Structure Decision**: Existing data-pipeline layout. The feature adds **one** new intermediate model (`int_plan_eligibility_override`) as the single resolution point ("resolve once, gate everywhere"), one optional macro, edits to four existing models + staging scaffold, two Pydantic fields + their export, and tests. Studio UI is an optional follow-up that does not block the core (config + measurable output change) per the spec's P1.

## Complexity Tracking

> No Constitution Check violations. Section intentionally empty.
