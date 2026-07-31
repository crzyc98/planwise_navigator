# Tasks: Social Security Integrated Employer Core Contribution

**Input**: Design documents from `/specs/126-ss-integrated-core/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [configuration/UI contract](contracts/configuration-and-ui.md), [quickstart.md](quickstart.md)

**Tests**: Required. The specification demands them (SC-006, SC-007) and Constitution Principle III mandates test-first. Write each listed test before the implementation it covers. Behavioral tests run **only** against isolated per-run DuckDB databases; the shared `dbt/simulation.duckdb` is never built into.

**Organization**: Grouped by user story. Phase order is **not** spec priority order — see the note below.

## Format: `[ID] [P?] [Story] Description`

- **[P]** marks work that can proceed in parallel once its dependencies are complete.
- **[US#]** maps a task to the corresponding user story in [spec.md](spec.md).

---

## Phase ordering note (deviation from priority order, with reason)

The spec ranks US1/US2/US3 as P1 and US5 as P2. Execution order differs because **US5 is a hard prerequisite for US1 and US3** — both need the wage base to exist before they can compute or validate anything. Ordering the phases by priority alone would produce a task list that cannot be executed in sequence.

Execution order is therefore: **US5 → US3 → US1 → US2 → US4**. US3 precedes US1 because it is pure Python over configuration plus a CSV, needs no database, and runs in the fast suite — so it gives the earliest feedback on the highest-uncertainty item in the feature (the §401(l) factor table). Every story remains independently testable once its predecessors land.

---

## Plan refinement: where the §401(l) logic lives

`plan.md` placed the new validation in `planalign_orchestrator/config/workforce.py`. That file is **already 618 lines**, over the ~600-line ceiling in Constitution Principle II, and this feature would add roughly 130 more. The factor table, the level resolver, the seed reader, and the validator therefore go in a **new module**, `planalign_orchestrator/config/permitted_disparity.py`.

This also serves the isolation `research.md` R8 argued for: the §401(l) table is the highest-uncertainty artifact in the feature, and giving it its own module with its own table-driven tests means a correction touches one file. `workforce.py` gains only the `CoreIntegrationSettings` model, keeping it beside the sibling `AgeCoreTier`.

---

## Phase 1: Setup

**Purpose**: Checked-in fixtures and config examples shared by implementation and isolated integration tests.

- [X] T001 [P] Create the integrated-core census fixture in `tests/fixtures/integrated_core/integrated_core.csv` with employees deliberately straddling the boundaries: below the wage base, exactly at it, above it, above the 401(a)(17) cap, and one mid-year hire whose prorated pay lands below the wage base.
- [X] T002 [P] Create paired scenario configs `tests/fixtures/integrated_core/{integrated_core.yaml,flat_core_baseline.yaml}` differing **only** in the `integration` block, so the cost delta is attributable per quickstart §5.
- [X] T003 [P] Create per-status integration configs `tests/fixtures/integrated_core/core_mode_{flat,graded_by_service,points_based,age_banded}_integrated.yaml` reusing the schedules from `tests/fixtures/age_banded_core/` so US2 varies only the base rate shape.
- [X] T004 [P] Document the `employer_core_contribution.integration` block with commented defaults and all three `level_mode` values in `config/simulation_config.yaml`, following the contract in `specs/126-ss-integrated-core/contracts/configuration-and-ui.md`.

---

## Phase 2: Foundational

**Purpose**: Nothing here. This feature has no shared infrastructure that precedes the first user story — the wage base data *is* User Story 5, and it is the first executed phase.

**⚠️ Note**: Deliberately empty rather than padded. Phase 3 is the blocking prerequisite.

---

## Phase 3: User Story 5 — Statutory Wage Base Available by Year (Priority: P2, executed first) 🔓 BLOCKING

**Goal**: Every simulated year exposes a Social Security taxable wage base, with published years correct and projected years flagged as estimates.

**Independent Test**: Query `config_irs_limits` for each simulated year and confirm a wage base is present, published years match published figures, and projected years carry `is_estimated = true`.

### Tests for User Story 5

- [X] T005 [P] [US5] Add a failing seed-integrity test asserting `social_security_wage_base` is present, positive, monotonically non-decreasing by year, and that published-year values match the published anchors, in `tests/unit/config/test_irs_limits_seed.py`.
- [X] T006 [P] [US5] Add a failing test that a database whose `config_irs_limits` table predates the new column is detected and refreshed rather than erroring, exercising `_ensure_seed_current`, in `tests/unit/api/test_ndt_seed_currency.py`.

### Implementation for User Story 5

- [X] T007 [US5] Add the `social_security_wage_base` column to `dbt/seeds/config_irs_limits.csv`: 2024 = 168600, 2025 = 176100, 2026 **verified against the SSA announcement** (FR-002), and 2027+ projected with a constant annual dollar increment matching the form of the other estimated columns. Do **not** copy the 2026 row's pattern from its neighbouring cells — see `research.md` R6 for why that row is unreliable.
- [X] T008 [P] [US5] Declare `social_security_wage_base: integer` in `dbt/seeds/schema.yml` under `config_irs_limits`.
- [X] T009 [P] [US5] Declare `social_security_wage_base: integer` in `dbt/dbt_project.yml` under the `config_irs_limits` seed config. Add only this column; do not reconcile the six pre-existing untyped columns (`research.md` R5, out of scope).
- [X] T010 [US5] Add `social_security_wage_base` to the `required_columns` tuple in `planalign_api/services/ndt_service.py` (`_ensure_seed_current`). The surrounding `count == len(required_columns)` check is sound as written and needs no restructuring (`research.md` R4).
- [X] T011 [US5] Run `cd dbt && dbt seed --select config_irs_limits --full-refresh --threads 1` against a scratch database and confirm the column loads as an integer with no CSV-sniffing warning.

**Checkpoint**: The wage base is queryable per year through the normal seed path, and stale databases self-heal. US3 and US1 are now unblocked.

---

## Phase 4: User Story 3 — An Illegal Disparity Rate Stops the Run (Priority: P1) 🎯 Earliest feedback

**Goal**: A configuration violating §401(l) fails at config load, before any simulation work, naming the applicable limit.

**Independent Test**: Configure a disparity rate above the permitted maximum and confirm the run fails immediately with an error naming the limit, the configured rate, and which constraint bound.

### Tests for User Story 3

- [X] T012 [P] [US3] Add failing table-driven tests for `permitted_disparity_factor` covering every row **and every boundary** in the FR-013 table — level above the wage base, exactly at it, exactly at 80%, inside each band, exactly at `max(20% × wage base, 10000)`, and a synthetic small wage base that makes the `$10,000` floor dominate — in `tests/unit/config/test_permitted_disparity.py`.
- [X] T013 [P] [US3] Add failing tests for `resolve_level` across all three `level_mode` values, including the round-half-up-to-whole-dollars rule from `research.md` R7, in `tests/unit/config/test_permitted_disparity.py`.
- [X] T014 [P] [US3] Add failing tests that the wage base is read from `dbt/seeds/config_irs_limits.csv` with no database connection, and that a missing year raises a clear error, in `tests/unit/config/test_permitted_disparity.py`.
- [X] T015 [US3] Add failing validation tests in `tests/unit/config/test_core_contribution_validation.py` for: the three worked examples in contract 4; a legal config passing silently; `level_value` missing when the mode requires it; a negative disparity rate; `disparity_rate = 0` with integration enabled being **allowed**; a zero base rate with a non-zero disparity being rejected; and a `fixed_dollar` multi-year config that is legal in the first year but illegal in a later year, asserting the **later** year is named (`research.md` R3).
- [X] T016 [US3] Add failing tests that the same illegal configuration is rejected through **both** the direct-YAML `employer_core_contribution.integration` shape and the Studio `dc_plan.core_integration_*` shape, in `tests/unit/config/test_core_contribution_validation.py`. #522's commit records a precedence bug where no Studio-configured design ever reached a check — this test exists to prevent the repeat.

### Implementation for User Story 3

- [X] T017 [US3] Create `planalign_orchestrator/config/permitted_disparity.py` with `wage_base_for(year)` (reads the seed CSV, no DuckDB), `resolve_level(mode, value, wage_base)`, and `permitted_disparity_factor(level, wage_base)` per `data-model.md` §2.
- [X] T018 [US3] Add `validate_core_integration(core_config, start_year, end_year)` to `planalign_orchestrator/config/permitted_disparity.py`, looping every year in range and raising on the first violation with the message contract from `contracts/configuration-and-ui.md` §4.
- [X] T019 [US3] Add the `CoreIntegrationSettings` Pydantic model with field constraints and structural rules to `planalign_orchestrator/config/workforce.py`, beside `AgeCoreTier`.
- [X] T020 [US3] Wire `validate_core_integration` into the existing `@model_validator(mode="after")` in `planalign_orchestrator/config/loader.py` for both config shapes, applying `dc_plan` precedence per contract 2, and rename the validator to reflect that it now covers schedules and integration.
- [X] T021 [US3] Implement `min_schedule_rate(core_config)` — the flat rate for `flat`, the lowest tier rate for the three schedule shapes — in `planalign_orchestrator/config/permitted_disparity.py` per `research.md` R8.
- [X] T022 [US3] Run `pytest -m fast tests/unit/config/test_permitted_disparity.py tests/unit/config/test_core_contribution_validation.py -q` and confirm the whole file completes in the fast suite budget with no database access.

**Checkpoint**: Illegal designs are refused before any simulation work, on both configuration surfaces, with the limit named. Independently demonstrable with no database.

---

## Phase 5: User Story 1 — Price an Integrated Core Design (Priority: P1) 🎯 MVP

**Goal**: An integrated design computes correctly and decomposes into base and disparity components that reconcile to the total.

**Independent Test**: Run a scenario with integration enabled in an isolated database and confirm each employee's amount equals `base_rate × recognized_comp + disparity_rate × excess_comp`, with both components reported.

### Tests for User Story 1

- [X] T023 [P] [US1] Add a failing isolated-DB integration test module `tests/integration/test_integrated_core_contributions.py`, modelled on `tests/integration/test_age_banded_core_contributions.py` (same `ConstructionSpec`/`build_orchestrator` harness, the `SHARED_DEV_DB` guard, and `pytest.mark.integration`).
- [X] T024 [P] [US1] Add failing test `test_employee_at_integration_level_receives_no_disparity` pinning that the boundary yields zero excess and zero disparity.
- [X] T025 [P] [US1] Add failing test `test_cap_applies_before_split` pinning FR-009 — an employee above the 401(a)(17) cap has disparity computed off the capped figure, not gross pay.
- [X] T026 [P] [US1] Add failing test `test_integration_level_not_prorated_for_mid_year_hire` pinning FR-010 — a mid-year hire compares partial-year pay against the **full-year** level and receives no disparity. Assert the zero explicitly; this result is counterintuitive and the test is the only thing preventing a future "fix".
- [X] T027 [P] [US1] Add failing invariant tests for the four SQL-assertable invariants in `data-model.md` §4 (components reconcile, no excess ⇒ no disparity, ineligible ⇒ all zero, excess within bounds).

### Implementation for User Story 1

- [X] T027a [US1] Add failing export tests for the four `employer_core_integration_*` dbt vars from the direct-YAML path, asserting rates cross as decimal fractions, in `tests/unit/orchestrator/test_config_export.py`.
- [X] T027b [US1] Export the four integration vars from the direct-YAML path in `_export_core_contribution_vars` in `planalign_orchestrator/config/export.py`. **This is a prerequisite for every SQL task below** — the model reads these vars, and without the export they resolve to their defaults and integration silently never activates.
- [X] T028 [US1] Add `social_security_wage_base` to the existing `irs_compensation_limits` CTE in `dbt/models/intermediate/int_employer_core_contributions.sql` — same seed, same row, no new join.
- [X] T029 [US1] Create `dbt/macros/get_integrated_core_amounts.sql` resolving the integration level from the level mode, wage base, and level value (applying the same round-half-up rule as `resolve_level`), and emitting the excess and the two rounded amount components.
- [X] T030 [US1] Add an integration CTE to `dbt/models/intermediate/int_employer_core_contributions.sql` that lifts `LEAST(prorated_annual_compensation, irs_401a17_limit)` into a named `recognized_compensation` column, so the cap-before-split ordering is visible rather than implied inside the amount expression.
- [X] T031 [US1] Gate the amount expression on `employer_core_integration_enabled` in `dbt/models/intermediate/int_employer_core_contributions.sql`: when disabled, emit today's single-`ROUND` expression **verbatim, character for character**; when enabled, emit `ROUND(base,2) + ROUND(disparity,2)` (`research.md` R1). Do not emit `+ 0` on the disabled path.
- [X] T032 [US1] Add the five audit columns (`ss_wage_base`, `integration_level_applied`, `excess_compensation`, `base_core_amount`, `disparity_core_amount`) to the model output, with `integration_level_applied` as `NULL` — not `0` — when integration is disabled.
- [X] T033 [US1] Confirm the integration level is **not** threaded through the mid-year proration block at `dbt/models/intermediate/int_employer_core_contributions.sql` (~lines 103-128); that block continues to prorate compensation only.
- [X] T034 [US1] Run `pytest -m integration tests/integration/test_integrated_core_contributions.py -v` against isolated per-run databases and confirm every ordering test passes.

**Checkpoint**: MVP. An integrated design can be priced end to end and reconciled line-by-line against a plan document.

---

## Phase 6: User Story 2 — Integration Composes With Every Core Rate Shape (Priority: P1)

**Goal**: Integration behaves identically under `flat`, `graded_by_service`, `points_based`, and `age_banded`, varying only through the resolved base rate.

**Independent Test**: Run the same integration settings against each of the four shapes and confirm the disparity component is computed identically in every case.

### Tests for User Story 2

- [X] T035 [P] [US2] Add failing test `test_disparity_composes_with_every_core_status` parameterised over the four fixtures from T003, asserting the disparity component depends only on excess compensation and the disparity rate — never on the shape.
- [X] T036 [P] [US2] Add a failing test that two employees in different bands of a graded schedule, both above the integration level, receive their own band's base rate and the **same** disparity rate.
- [X] T037 [US2] Add failing disabled-parity tests asserting byte-identical results across all four shapes (SC-002), comparing full result sets with `EXCEPT` per quickstart §6 — not aggregates.

### Implementation for User Story 2

- [X] T038 [US2] Verify no per-status branching exists in the integration path in `dbt/macros/get_integrated_core_amounts.sql` or the model's integration CTE; the only status-dependent input is the already-resolved `core_rate_expr`. Refactor if any leaked in during Phase 5.
- [X] T039 [US2] Run the four-shape parity and composition suite and confirm both the composition tests and the byte-identical disabled-parity checks pass.

**Checkpoint**: The central design claim (FR-005 — integration is a modifier, not a status) is demonstrated, not merely asserted.

---

## Phase 7: User Story 4 — Configure and Review an Integrated Design in Studio (Priority: P2)

**Scoped down**: only the *cost comparison* half of the original story was removed — running two scenarios and comparing employer cost is existing functionality. Configuring the design and describing it correctly remain in scope.

**Goal**: Integration is configurable in Studio for every contribution type, round-trips through save/reopen, reaches the engine, and is described accurately wherever it is rendered.

**Independent Test**: Configure integration in Studio, save and reopen, confirm the settings round-trip and both prose surfaces name the level and disparity rate.

- [X] T040 [P] [US4] Add failing export tests for the Studio `dc_plan` integration path in `tests/unit/orchestrator/test_config_export.py`: vars reach dbt, a percentage rate converts to a decimal fraction, and a payload silent about integration does not enable it.
- [X] T041 [US4] Export the four integration vars from the Studio `dc_plan` path in `planalign_orchestrator/config/export.py`, and merge `integration` into the nested `employer_core_contribution` shape.
- [X] T042 [US4] Extract `normalize_dc_plan_integration` into `planalign_orchestrator/config/permitted_disparity.py` and use it from **both** `loader.py` validation and `export.py`, so an illegal rate cannot arrive under a key one of them ignores. Add the bypass regression test in `tests/unit/config/test_core_contribution_validation.py`.
- [X] T043 [P] [US4] Add the four integration form fields, the `CoreIntegrationLevelMode` type, defaults (off), config hydration, and percentage-to-decimal payload serialization in `planalign_studio/components/config/{types.ts,constants.ts,ConfigContext.tsx,buildConfigPayload.ts}`.
- [X] T044 [US4] Add the integration editor — enable toggle, level-mode select, conditional level-value input, disparity-rate input, and the §401(l) note — to `planalign_studio/components/config/DCPlanSection.tsx`, rendered for **every** contribution type and placed after the status editors so it visibly modifies rather than replaces them.
- [X] T045 [P] [US4] Add the integration block and `formatIntegrationLevel` to the read-only core contribution view in `planalign_studio/components/PlanDesignModal.tsx`.
- [X] T046 [P] [US4] `derivePlanSummary` integration clause in `planalign_studio/components/ScenarioCostComparison.tsx` (already shipped; see T050).
- [ ] T047 [US4] Manually verify in Studio: the save/reopen round-trip, integration shown for all four contribution types, both prose surfaces, and that an illegal disparity rate is refused with the limit named.

**Checkpoint**: An integrated design can be built, saved, reviewed, and run entirely from Studio.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T049 [P] Run the full disabled-parity verification from quickstart §6 across all four core shapes against isolated databases and record the row counts in the PR description as evidence for SC-002.
- [X] T050 [P] Append the integration clause to every branch of `derivePlanSummary` in `planalign_studio/components/ScenarioCostComparison.tsx` per contract 5, so an integrated design is never rendered as `"Flat 3% of eligible compensation."` (FR-020). With integration off, the wording must be byte-identical to today's.
- [X] T051 [P] Run the flat-vs-integrated cost reconciliation from quickstart §5 and confirm `cost_delta = disparity_total` exactly (SC-008). This is an engine check across two isolated scenario databases, not a UI check.
- [X] T052 [P] Add the `integration` block and the §401(l) constraint to the employer core contribution documentation in `CLAUDE.md` §10, following the existing feature entries.
- [X] T053 [P] Confirm `planalign_orchestrator/config/permitted_disparity.py` stays within the ~600-line Principle II ceiling and that `workforce.py` did not grow beyond its current 618 lines by more than the `CoreIntegrationSettings` model.
- [ ] T054 Run the full fast suite (`pytest -m fast`) and confirm it still completes within the <10s budget with the new validation tests included.
- [X] T055 Verify the four new dbt vars participate in the Feature 109 config fingerprint, so changing an integration setting registers as config drift rather than silently reusing a stale database.

---

## Dependencies

```
Phase 1 (Setup: T001-T004)
   ↓
Phase 3 (US5: wage base) ──── BLOCKING for US3 and US1
   ↓
   ├──→ Phase 4 (US3: §401(l) validation)   [no DB; independent of US1]
   └──→ Phase 5 (US1: export → computation)
                    ↓
           Phase 6 (US2: four-shape composition)
                    ↓
           Phase 8 (Polish, incl. the derivePlanSummary label fix)
```

- **US5 blocks US3 and US1** — both need the wage base.
- **US3 and US1 are independent of each other** and may proceed in parallel once US5 lands.
- **Within Phase 5, T027b (var export) blocks T028-T034.** The SQL cannot see the config until the vars are exported; skipping ahead produces a run that succeeds while computing no integration at all.
- **US2 depends on US1** — it exercises the computation across shapes.
- **Phase 7 is removed.** Nothing depends on it.

## Parallel Opportunities

| Group | Tasks | Why safe |
|---|---|---|
| Fixtures | T001, T002, T003, T004 | Four separate new files |
| US5 typing | T008, T009 | `schema.yml` and `dbt_project.yml` are separate files |
| US3 unit tests | T012, T013, T014 | Same new test file, disjoint test functions — write together, or serialize if editing conflicts |
| US1 tests | T023-T027 | Disjoint test functions in one new module |
| Polish | T049-T053 | Unrelated files: isolated-DB runs, one TSX file, one MD file, a line-count check |

## Implementation Strategy

**MVP = Phases 1 + 3 + 4 + 5** (T001-T034, including the rescued T027a/T027b). That delivers a correct, legally-guarded integrated core contribution priced end to end with full audit decomposition — everything the spec marks P1 except four-shape verification. Phase 6 verifies a property Phase 5 should already have.

**Highest-risk item first**: Phase 4 (the §401(l) factor table) runs before the SQL because it is pure Python, needs no database, and is the artifact the spec checklist flags for expert review. Discovering the table is wrong after building the SQL would waste the integration-test cycles.

**The two tasks that must not be skipped or deferred**: T031 (verbatim disabled expression) and T037 (byte-identical parity across four shapes). FR-007 is the requirement most likely to be quietly broken by a reasonable-looking refactor, and it is the one that would silently change every existing client's numbers.
