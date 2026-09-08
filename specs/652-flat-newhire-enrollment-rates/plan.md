# Implementation Plan: Explicit New-Hire Enrollment Rates and Deferral Spread

**Branch**: `652-flat-newhire-enrollment-rates` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/652-flat-newhire-enrollment-rates/spec.md`
**Research**: [research.md](./research.md) | **Tracking Issue**: #652

## Summary

Give the analyst two flat, deterministic new-hire rates — voluntary enrollment % and opt-out % — and let the remainder auto-enroll, replacing a control that silently acted as a demographic multiplier.

The approach rests on one property established in research (R1): the existing multiplier is inert at its configured default of `1.0`, so it can be **deleted outright** from all three probability expressions without changing any scenario that leaves the rate unset. That reduces the change to three concrete pieces of work: a flat draw for hire-year new hires in `int_voluntary_enrollment_decision`, a new-hire-scoped flat opt-out branch in `int_enrollment_events`, and the config plus Studio surface for both rates. The set/unset convention agreed during specification means the demographic new-hire path stays in place to serve unset scenarios.

Runtime verification (research R6) narrowed the problem: the large "not enrolled" bucket in the issue's reproduction is the plan's three-month waiting period working correctly, not a missing enrollment path. Among **eligible** new hires the pipeline already produces a clean four-way split with no active unenrolled employees. The defect to fix is therefore only the uncontrollable ratio between voluntary (~73%) and auto (~20%) — a narrower and safer change than the issue implied.

## Decisions Taken

All open decisions are settled. Recorded here because several are behavior changes an implementer must not silently revisit.

| # | Decision | Consequence |
|---|---|---|
| D1 | Studio scenarios carrying the old default `0.30` are **allowed to change meaning**. | Those scenarios enroll 30% of new hires instead of ~17%. The field is renamed so the change is visible. No migration. |
| D2 | Closed by verification — no spec amendment needed (R6). | SC-004 measured over new hires active at year end, where the baseline is already 0%. |
| D3 | **Approximate selection** via the existing per-employee hash draw, not exact-count ranking. | SC-001's tolerance widened from ±1 to ±2 points. Realized shares wobble year to year by design. |
| D4 | Deferral spread built **alongside** this feature, not after. | Both land together. Phases C-F and G-H are separately verifiable so a wrong number can still be attributed. |
| D5 | Spread is **upward-only**: the table value is a floor, not a center. Weights 40 / 30 / 15 / 10 / 5 across +0 to +4 percentage points. | Average deferral rates rise ~1.1 points per affected cell. Accepted (D6). |
| D6 | **Let the average rise.** No re-calibration of table values to offset the spread. | Projected employer match cost increases. This is the point: today's averages are artificially low. |
| D7 | Maximum voluntary deferral rate raised **10% → 15%**. | ⚠️ Changes results *independently of the spread*. Four table cells (mature/executive 12%, senior/high 12%, senior/executive 15%) are currently clamped to 10% and will un-clamp. Must be called out in the changelog as its own change. |

## Technical Context

**Language/Version**: Python 3.11; dbt-core 1.8.8 / dbt-duckdb 1.8.1 (Jinja-templated SQL); TypeScript/React for Studio
**Primary Dependencies**: DuckDB 1.0.0, Pydantic v2, `planalign_orchestrator` pipeline
**Storage**: DuckDB event store — `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`, `int_enrollment_events`, `int_enrollment_state_accumulator`, `fct_yearly_events`, `fct_workforce_snapshot`
**Testing**: pytest (`-m fast` unit, `-m integration`), dbt schema tests, isolated-DB scenario runs
**Target Platform**: Local macOS / work-laptop CLI + local Studio web UI
**Project Type**: Data pipeline (dbt over DuckDB) with a Python orchestrator, a Typer CLI, and a React configuration UI
**Performance Goals**: No regression against the 38-command dbt invocation baseline; no new model materializations
**Constraints**: Single-threaded dbt (`--threads 1`); deterministic and reproducible for a fixed seed; validation must run in an isolated database, never the shared dev DB
**Scale/Scope**: ~870 eligible new hires per simulated year at the reproduction's census size; 5-year runs

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Event Sourcing & Immutability | **PASS** | No event is mutated. The flat draw replaces a probability threshold inside existing event-generation models; the deterministic hash idiom (R7) preserves seed reproducibility, which FR-005 and SC-005 test directly. |
| II. Modular Architecture | **PASS with a note** | No new modules and no layer inversion. `int_enrollment_events.sql` is already 856 lines and gains an opt-out branch; the plan keeps that growth to a branch inside the existing CTE rather than a new one. Flagged, not a violation — the constitution's ~600-line rule governs Python modules. |
| III. Test-First Development | **PASS** | Every acceptance criterion is expressed as a countable query. Config validation and export tests are unit-level and go in the fast suite; the distribution criteria are integration-level against an isolated DB. Tests precede implementation per phase ordering below. |
| IV. Enterprise Transparency | **PASS** | FR-011 is satisfied by the existing `event_category` labeling, which survives deduplication (R4). The plan additionally fixes the `proactive_voluntary` alias gap found in the accumulator so the labels are actually correct rather than correct by fallback. |
| V. Type-Safe Configuration | **PASS** | Both rates are Pydantic v2 fields with `ge=0, le=1`, matching the existing `voluntary_enrollment_rate` constraint. FR-008's validation requirement is satisfied by field constraints, which already produce field-named errors. |
| VI. Performance & Scalability | **PASS** | No new models, no new materializations, no added dbt invocations. The rank-based selection under consideration (R7/D3) adds one window function over the per-year new-hire cohort — a few thousand rows. |

**Gate result: PASS.** No violations to justify, so the Complexity Tracking table is omitted.

One constitutional tension worth naming rather than burying: Principle III sets a <10s budget for the fast suite, and issue #648 records that it currently runs ~4.5 minutes. This feature adds fast-suite tests and does not fix that; it also must not make it materially worse. The config and export tests here are pure-Python and cheap.

## Project Structure

### Documentation (this feature)

```text
specs/652-flat-newhire-enrollment-rates/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output — findings R1-R7 and open decisions D1-D3
├── data-model.md        # Phase 1 output — entities, fields, decision flow
├── quickstart.md        # Phase 1 output — verification recipe against an isolated DB
├── contracts/
│   ├── dbt-vars.md      # dbt variable contract
│   └── config-schema.md # Pydantic + Studio payload contract
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
dbt/
├── dbt_project.yml                                  # remove voluntary_enrollment_rate default; add new vars
├── macros/
│   └── enrollment_eligibility.sql                   # unchanged (scope macro verified correct)
└── models/
    ├── intermediate/
    │   ├── int_voluntary_enrollment_decision.sql    # flat new-hire draw; drop multiplier
    │   ├── int_proactive_voluntary_enrollment.sql   # suppress duplicate draw when flat rate set
    │   ├── int_enrollment_events.sql                # new-hire flat opt-out branch; drop YoY multiplier
    │   ├── int_enrollment_state_accumulator.sql     # fix proactive_voluntary category alias
    │   └── schema.yml                               # tests for the new columns
    └── marts/
        └── fct_workforce_snapshot.sql               # verify labeling unchanged (likely no edit)

planalign_orchestrator/config/
├── workforce.py                                     # repurpose field; add new-hire opt-out field
└── export.py                                        # export both rates to dbt vars

planalign_studio/components/config/
├── constants.ts                                     # default '30' -> '' (see D1)
├── types.ts                                         # add opt-out form field
├── DCPlanSection.tsx                                # relabel; add opt-out input
├── buildConfigPayload.ts                            # emit both rates
└── ConfigContext.tsx                                # hydrate both rates

planalign_studio/components/
└── PlanDesignModal.tsx                              # relabel the read-only display

tests/
├── unit/orchestrator/test_config_export.py          # validation + export (fast)
└── integration/                                     # distribution + determinism (new file)
```

**Structure Decision**: This is an existing modular data pipeline, not a greenfield project, so none of the template's layout options apply. Work lands in four existing areas — the dbt enrollment models, the Pydantic config layer, its dbt-var export, and the Studio configuration form — with no new packages, models, or directories.

## Implementation Phases

Ordered so that each phase is independently verifiable and the risky decisions are settled before code is written.

### Phase A — Decisions (COMPLETE)

All settled; see the Decisions Taken table above. D2 is **closed** — the runtime verification (R6) showed the not-enrolled bucket is entirely the waiting period, and SC-004 needs no amendment. D1 (Studio's stored `0.30` default) and D3 (exact versus approximate selection) remain open and are both quick calls.

### Phase B — Config surface, test-first

Repurpose `voluntary_enrollment_rate`, add the new-hire opt-out field, update the export path and the field descriptions. Write the validation and export tests first. Fully verifiable by the fast suite with no simulation run.

### Phase C — Delete the inert multiplier

Remove `voluntary_enrollment_rate` from the three probability expressions (R1). Provably a no-op when unset; establishes the baseline that Phase D branches from. Verify by a byte-comparison run on an isolated DB against a pre-change baseline.

### Phase D — Flat new-hire voluntary draw

Add the set/unset branch to `int_voluntary_enrollment_decision` for hire-year new hires, and suppress the duplicate draw in `int_proactive_voluntary_enrollment` when the flat rate is set (R3). Fix the `proactive_voluntary` accumulator alias (R4). Delivers User Story 1.

### Phase E — Flat new-hire opt-out

Add the new-hire-scoped branch to the opt-out CTE (R5), leaving the demographic path intact for continuing employees. Delivers User Story 2 and, with Phase D, the full four-outcome distribution.

### Phase F — Studio surface

Relabel the voluntary field, add the opt-out field, change the default to unset. Delivers User Story 3.

### Phase G — Deferral spread

Add the upward-only spread with its own hash seed, applied after the table lookup and before the match-magnet snap so that existing match-maximizing behavior still works on top of it. Off by default (FR-020), so Phase C's byte-identical baseline still holds. Applies to all three sites that assign a demographic rate — `int_voluntary_enrollment_decision`, `int_proactive_voluntary_enrollment`, and the year-over-year CTE in `int_enrollment_events` (FR-023). Delivers User Story 5.

### Phase H — Raise the deferral cap

Change the `voluntary_max_deferral_rate` default from `0.10` to `0.15` (FR-022, D7). Kept as its own phase precisely because it moves numbers on its own — bundling it into Phase G would make the spread look responsible for a shift it did not cause.

### Phase I — Verification and documentation

Run the three acceptance configurations from `quickstart.md` on isolated databases, confirm the distributions and determinism, and update the enrollment documentation per FR-016.

## Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | ~~SC-004 may be unreachable.~~ **CLOSED by verification (R6).** The residual is the three-month waiting period, not a pipeline defect; no eligible, active new hire is unenrolled today. | None. | Measure SC-004 over new hires active at year end. The remaining 2-3% residual is hire-year terminations, which is correct behavior and must not be engineered away. |
| 2 | **Studio scenarios will flip behavior** despite the compatibility guarantee, because the form default is an explicit `'30'` (R2). | FR-012's promise is narrower than stated during specification; analysts may see saved scenarios change. | Decision D1. Whichever way it goes, state the limitation in FR-012 rather than leaving the guarantee overstated. |
| 3 | **Threshold draws will not hit ±1 point** on realistic cohort sizes (R7); expected deviation is ~±1.7 points at one sigma. | SC-001 fails intermittently and non-reproducibly across years — the worst kind of flaky acceptance test. | Decision D3: rank-based selection makes the share exact to within one employee. Otherwise widen SC-001 to ±2 points. |
| 4 | The demographic new-hire path stays alive to serve unset scenarios, so both paths need test coverage. | Ongoing maintenance of a path the feature was partly meant to retire. | Already recorded as an assumption in the spec. Retirement is scoped as follow-on work, not smuggled in here. |
| 5 | `int_enrollment_events.sql` is 856 lines and compiles near the sqlparse token ceiling that `fct_workforce_snapshot` already trips. | A large added CTE could push another model over the auto-patched 50,000-token limit. | Keep the opt-out change a branch inside the existing CTE. Confirm compilation during Phase E. |

## Verification Strategy

Each acceptance criterion maps to a countable query rather than a judgment call. Full queries are in `quickstart.md`.

| Criterion | Verification |
|---|---|
| SC-001, SC-002, SC-003 | Three isolated-DB runs at (P=0.6, Q=0.1), (P=1.0), (P=0.0, Q=0.0); group eligible new hires by `participation_status_detail` per year. |
| SC-004 | Same runs; count not-enrolled new hires, split by termination status per Risk 1. |
| SC-005 | Two runs at identical seed and config; assert the selected employee-ID sets are identical, not merely the counts. |
| SC-006, SC-009 | Pre-change baseline versus post-change run with both rates unset; assert identical counts. |
| SC-007, SC-008 | Reviewed against the Studio surface in Phase F. |
| SC-010, SC-011 | Spread-enabled run; per demographic cell, assert no single rate holds >45% of members and no rate falls below the cell's floor. |
| SC-012 | Spread-disabled run versus the Phase C baseline; deferral rates identical per employee. |

All runs use isolated databases per the project's standing rule; none touch `dbt/simulation.duckdb`.
