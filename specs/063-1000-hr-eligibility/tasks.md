# Tasks: ERISA 1,000-Hour Eligibility Rules

**Input**: Design documents from `/specs/063-1000-hr-eligibility/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Organization**: Tasks are grouped by user story. US1 (IECP computation periods) and US2 (1,000-hour threshold) are combined into a single phase because they are both P1 and implemented in the same model file (`int_eligibility_computation_period.sql`). US3 (eligibility vs. vesting independence) is a separate phase (P2) with its own model.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration extension and reusable macro creation

- [X] T001 Add `erisa_eligibility` config section to `config/simulation_config.yaml` with keys: `enabled`, `hour_counting_method` (only `"prorated"` this iteration), `plan_year_start_month`, `plan_year_start_day`, `eligibility_threshold_hours`, `vesting_computation_period` (see data-model.md Configuration Entity for values). Also create/extend the Pydantic model in the config module to validate this section (Constitution V: all config MUST use Pydantic v2 with explicit validation constraints)
- [X] T002 [P] Create `classify_service_hours` macro in `dbt/macros/classify_service_hours.sql` — accepts `hours_column` parameter, returns CASE expression classifying >= 1000 as `'year_of_service'`, else `'no_credit'` (FR-004)

---

## Phase 2: User Story 1 + 2 — IECP Computation Periods & 1,000-Hour Threshold (Priority: P1) — MVP

**Goal**: Implement ERISA-compliant eligibility computation periods with boundary-aware IECP, plan-year switching, overlap/double-credit rule, IRC 410(a)(4) entry dates, and 1,000-hour threshold classification.

**Independent Test**: Simulate employees hired at various points (Jan 1, Apr 1, Oct 1) and verify: (a) IECP spans correct 12-month window from hire date, (b) hours are prorated and compared against 1,000-hour threshold, (c) system switches to plan year after first anniversary, (d) overlap/double-credit awards 2 years when both IECP and plan year meet threshold, (e) plan entry dates comply with IRC 410(a)(4).

**Covers**: FR-001 (IECP), FR-002 (plan year switching), FR-003 (overlap/double-credit), FR-004 (1,000-hour threshold), FR-005 (entry date), FR-007 (configurable plan parameters)

### Implementation

- [X] T003 [US1] Create `int_eligibility_computation_period.sql` in `dbt/models/intermediate/` — materialized as `table`, tags `['eligibility', 'erisa', 'STATE_ACCUMULATION']`. Must implement:
  - Read from `{{ ref('int_baseline_workforce') }}` for census employee hire dates, `{{ ref('int_hiring_events') }}` for simulated new hires (employee_id, effective_date as hire_date), and `{{ ref('int_new_hire_termination_events') }}` for employment status (LEFT JOIN — if matched, employee is terminated; otherwise active). This follows the E079 pattern used by `int_employer_eligibility` and avoids reading from marts-layer `fct_*` tables
  - IECP boundary calculation: `hire_date_anniversary = hire_date + INTERVAL '1 year'`
  - IECP Year 1 hours: `DATEDIFF('day', hire_date, MAKE_DATE(simulation_year, 12, 31)) / 365.0 * 2080.0`
  - IECP Year 2 hours: `DATEDIFF('day', MAKE_DATE(simulation_year, 1, 1), hire_date_anniversary) / 365.0 * 2080.0`
  - Plan year switching after IECP complete (period_type: `'iecp'` → `'plan_year'`)
  - Overlap/double-credit rule: `eligibility_years_this_period` = 2 when both IECP and plan year meet 1,000 hours
  - Plan entry date per IRC 410(a)(4): `LEAST(plan_year_start + INTERVAL '1 year', eligibility_met_date + INTERVAL '6 months')`
  - Use `{{ classify_service_hours(hours_column) }}` macro for threshold classification
  - All columns per data-model.md Eligibility Computation Period entity (21 columns)
  - Eligibility reason codes: `eligible_iecp`, `eligible_plan_year`, `eligible_double_credit`, `pending_iecp`, `insufficient_hours_iecp`, `insufficient_hours_plan_year`, `already_eligible`
  - Jan 1 hires: IECP and plan year coincide without double-counting
  - Filter by `{{ var('simulation_year') }}`; join on `scenario_id, plan_design_id, employee_id`
- [X] T004 [US1] Add schema tests for `int_eligibility_computation_period` in `dbt/models/intermediate/schema.yml` — add model entry with tags `['eligibility', 'erisa', 'STATE_ACCUMULATION']`, column tests: `not_null` on all required columns, `accepted_values` on `period_type` (`['iecp', 'plan_year']`), `accepted_values` on `hours_classification` (`['year_of_service', 'no_credit']`), `accepted_values` on `eligibility_reason`, range tests on `annual_hours_prorated` (0–3000), `eligibility_years_this_period` (0–2)
- [X] T005 [P] [US1] Create `test_iecp_computation.sql` in `dbt/tests/data_quality/` — config severity `'error'`, tags `['data_quality', 'erisa', 'eligibility']`. Validate: (a) IECP spans exactly 12 months from hire date, (b) `iecp_year1_hours + iecp_year2_hours = iecp_total_hours`, (c) mid-year hires produce correct partial-year proration, (d) system switches to `plan_year` period type after first anniversary, (e) plan entry dates never exceed statutory maximum delay per IRC 410(a)(4) — `plan_entry_date <= LEAST(next_plan_year_start, eligibility_met_date + INTERVAL '6 months')` (SC-004), (f) every row has non-null `eligibility_reason` and traceable `period_type` + `annual_hours_prorated` for audit reconstruction (SC-005). Return failure rows only with descriptive `issue_description`.
- [X] T006 [P] [US2] Create `test_hours_threshold.sql` in `dbt/tests/data_quality/` — config severity `'error'`, tags `['data_quality', 'erisa', 'eligibility']`. Validate boundary values: 0 hours → `'no_credit'`, 999 hours → `'no_credit'`, 1000 hours → `'year_of_service'`, 2080 hours → `'year_of_service'`. Use `{{ classify_service_hours() }}` macro result against expected classification. Return failure rows only.
- [X] T007 [US1] Build and validate `int_eligibility_computation_period`: run `dbt run --select int_eligibility_computation_period --vars "simulation_year: 2025" --threads 1`, then `dbt test --select int_eligibility_computation_period --threads 1`, then `dbt test --select tag:erisa --threads 1`. Verify all tests pass.

**Checkpoint**: IECP computation periods and 1,000-hour threshold are functional. Mid-year hires produce correct IECP boundaries, threshold classification works at all boundary values, and plan entry dates comply with IRC 410(a)(4).

---

## Phase 3: User Story 3 — Separate Eligibility vs. Vesting Service Credit (Priority: P2)

**Goal**: Implement independent tracking of eligibility service credit and vesting service credit using a temporal state accumulator pattern.

**Independent Test**: Simulate an employee who works 2,000 hours in 8 months then terminates — verify they receive 1 year of vesting service but 0 years of eligibility service (12-month eligibility period not completed). Also verify that VCP uses plan year while ECP uses IECP, producing different credit counts for the same employee.

**Covers**: FR-006 (independent eligibility/vesting tracking)

### Implementation

- [X] T008 [US3] Create `int_service_credit_accumulator.sql` in `dbt/models/intermediate/` — materialized as `incremental` with `incremental_strategy='delete+insert'`, unique_key `['employee_id', 'simulation_year']`, tags `['eligibility', 'erisa', 'STATE_ACCUMULATION']`. Must implement:
  - Temporal accumulator pattern (follow `int_enrollment_state_accumulator.sql`):
    - `{% if simulation_year == start_year %}`: Initialize from `{{ ref('int_baseline_workforce') }}` (census tenure → seed eligibility years) + `{{ ref('int_eligibility_computation_period') }}`
    - `{% else %}`: Read from `{{ this }}` (prior year `simulation_year - 1`) FULL OUTER JOIN `{{ ref('int_eligibility_computation_period') }}`
  - Independent tracking: `eligibility_years_credited` (from ECP) and `vesting_years_credited` (from VCP) as separate counters
  - **VCP hour source**: Vesting hours come from plan-year-aligned records in `int_eligibility_computation_period` (where `period_type = 'plan_year'`). For hire year when only IECP records exist, compute vesting hours directly as `DATEDIFF('day', GREATEST(hire_date, plan_year_start), plan_year_end) / 365.0 * 2080.0` using hire_date from `int_baseline_workforce`. Apply `{{ classify_service_hours() }}` macro to vesting hours independently of eligibility hours.
  - Carry-forward fields: `eligibility_years_credited`, `vesting_years_credited`, `is_plan_eligible`, `plan_entry_date`
  - Reset fields per year: `eligibility_hours_this_year`, `vesting_hours_this_year`
  - `is_plan_eligible` = TRUE once eligibility threshold met (ever), never reverts
  - `service_credit_source`: `'baseline'` (first year) or `'accumulated'` (subsequent years)
  - All columns per data-model.md Service Credit Accumulator entity (15 columns)
  - Filter/join on `scenario_id, plan_design_id, employee_id`
  - Pre-hook: `DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}`
- [X] T009 [US3] Add schema tests for `int_service_credit_accumulator` in `dbt/models/intermediate/schema.yml` — add model entry with tags `['eligibility', 'erisa', 'STATE_ACCUMULATION']`, column tests: `not_null` on all required columns, `accepted_values` on `eligibility_classification_this_year` and `vesting_classification_this_year` (`['year_of_service', 'no_credit']`), `accepted_values` on `employment_status` (`['active', 'terminated']`), `accepted_values` on `service_credit_source` (`['baseline', 'accumulated']`), range test on `eligibility_years_credited` (>= 0), range test on `vesting_years_credited` (>= 0)
- [X] T010 [P] [US3] Create `test_eligibility_vs_vesting_independence.sql` in `dbt/tests/data_quality/` — config severity `'error'`, tags `['data_quality', 'erisa', 'eligibility']`. Validate: (a) eligibility and vesting credits can differ for the same employee in the same year, (b) an employee can have vesting credit without eligibility credit (e.g., 8-month employee with 2,000 hours), (c) `is_plan_eligible` never reverts from TRUE to FALSE across years. Return failure rows only with descriptive `issue_description`.
- [X] T011 [US3] Build and validate `int_service_credit_accumulator`: run `dbt run --select int_service_credit_accumulator --vars "simulation_year: 2025" --threads 1`, then `dbt test --select int_service_credit_accumulator --threads 1`. Verify all tests pass.

**Checkpoint**: Eligibility and vesting service credits are tracked independently. The temporal accumulator correctly initializes from baseline and accumulates across simulation years.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Full system validation and verification

- [X] T012 Run full `dbt build --threads 1 --fail-fast` to validate no regressions across all models
- [X] T013 Execute quickstart.md verification checklist: confirm all 9 items pass (IECP for mid-year hires, plan year switching, overlap/double-credit, multi-year accumulation, independent eligibility/vesting, IRC 410(a)(4) entry dates, boundary values, Jan 1 hires, no modifications to existing models)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **US1+US2 (Phase 2)**: Depends on Phase 1 (macro and config must exist before model references them)
- **US3 (Phase 3)**: Depends on Phase 2 (`int_service_credit_accumulator` reads from `int_eligibility_computation_period`)
- **Polish (Phase 4)**: Depends on Phase 2 and Phase 3

### Within-Phase Dependencies

- **Phase 1**: T001 and T002 are independent [P] — can run in parallel
- **Phase 2**: T003 must complete before T004 and T007. T005 and T006 are [P] and can be written in parallel with T003 (they test the model output, so must run after T003 builds). T007 runs last.
- **Phase 3**: T008 must complete before T009 and T011. T010 is [P] and can be written in parallel with T008. T011 runs last.
- **Phase 4**: T012 before T013

### Parallel Opportunities

- T001 and T002 can run in parallel (different files)
- T005 and T006 can run in parallel (different test files)
- T005/T006 can be written in parallel with T003 (but must build after T003)
- T010 can be written in parallel with T008

---

## Parallel Example: Phase 2

```bash
# Write macro and config in parallel:
Task T001: "Add erisa_eligibility config section to config/simulation_config.yaml"
Task T002: "Create classify_service_hours macro in dbt/macros/classify_service_hours.sql"

# Write tests in parallel with model (tests can't run until model builds):
Task T003: "Create int_eligibility_computation_period.sql"
Task T005: "Create test_iecp_computation.sql"
Task T006: "Create test_hours_threshold.sql"
```

---

## Implementation Strategy

### MVP First (Phase 1 + Phase 2)

1. Complete Phase 1: Setup (config + macro)
2. Complete Phase 2: US1+US2 (IECP model + threshold tests)
3. **STOP and VALIDATE**: Run `dbt build --select int_eligibility_computation_period+ --threads 1`
4. Verify IECP computation, threshold classification, and plan entry dates

### Incremental Delivery

1. Phase 1 + Phase 2 → MVP: IECP and 1,000-hour threshold working
2. Phase 3 → Add independent eligibility/vesting tracking with temporal accumulator
3. Phase 4 → Full system validation, no regressions

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 and US2 are combined into Phase 2 because they share the same model file and are both P1
- US3 depends on US1+US2 output (accumulator reads from computation period model)
- All dbt commands must run from `/dbt` directory with `--threads 1`
- Follow existing patterns: temporal accumulator from `int_enrollment_state_accumulator.sql`, test format from `dbt/tests/data_quality/`
- Commit after each task or logical group
