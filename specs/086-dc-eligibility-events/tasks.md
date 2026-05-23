# Tasks: DC Plan Eligibility Audit Trail

**Input**: Design documents from `/specs/086-dc-eligibility-events/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Included — constitution requires 90%+ coverage; plan.md explicitly calls out dbt schema tests, prerequisite chain test, and pytest unit test.

**Organization**: Tasks grouped by user story for independent implementation and validation.

---

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story (US1, US2, US3)
- Each task includes exact file path

---

## Phase 1: Setup (Shared Constants and Macros)

**Purpose**: Add the two constant/macro definitions that every subsequent task depends on. Both touch different files and can be done in parallel.

- [x] T001 [P] Add `EVENT_ELIGIBILITY = "eligibility"` constant after `EVENT_ENROLLMENT` on line 72 of `config/constants.py`
- [x] T002 [P] Add `{% macro cat_eligibility() %}'eligibility'{% endmacro %}` after the `evt_eligibility()` definition, and insert `WHEN {{ col }} = {{ evt_eligibility() }} THEN {{ cat_eligibility() }}` into the `event_category_from_type` CASE before the `ELSE 'other'` clause in `dbt/macros/constants.sql`

**Checkpoint**: Constants and macros in place — all downstream tasks can reference `EVENT_ELIGIBILITY` and `{{ cat_eligibility() }}`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The SQL model and its schema tests must exist before the UNION wire-up, the Python generator reference, or the prerequisite chain test can be implemented. These are strictly sequential.

**⚠️ CRITICAL**: No user story work can begin until T003 and T004 are complete.

- [x] T003 Create `dbt/models/intermediate/events/int_eligibility_events.sql` as an incremental model (`delete+insert`, `unique_key=['employee_id', 'simulation_year']`, tag `EVENT_GENERATION`) that: (1) reads `int_plan_eligibility_determination` filtered to `is_plan_eligible = true` for the current `simulation_year`; (2) for Year 2+, anti-joins against `{{ this }}` to exclude employees who already received an eligibility event in any prior year; (3) selects all columns required by the `fct_yearly_events` UNION schema — `employee_id`, `employee_ssn`, `{{ evt_eligibility() }}` as `event_type`, `simulation_year`, `eligibility_effective_date` as `effective_date`, a descriptive `event_details` string, NULL compensation fields, demographic fields (`employee_age`, `employee_tenure`, `level_id`, `age_band`, `tenure_band`), `1.0` as `event_probability`, and `{{ cat_eligibility() }}` as `event_category`
- [x] T004 Add `int_eligibility_events` entry to `dbt/models/intermediate/events/schema.yml` with: `dbt_utils.unique_combination_of_columns` on `[employee_id, simulation_year]`; `not_null` tests on `employee_id`, `event_type`, `effective_date`, `simulation_year`; `accepted_values` on `event_type: ['eligibility']`; `accepted_values` on `event_category: ['eligibility']`

**Checkpoint**: Run `dbt run --select int_eligibility_events --vars '{"simulation_year": 2025}' --threads 1` and `dbt test --select int_eligibility_events --threads 1` — both must pass before proceeding.

---

## Phase 3: User Story 1 — Eligibility Decisions Captured in Audit Trail (Priority: P1) 🎯 MVP

**Goal**: After this phase, running a simulation populates `fct_yearly_events` with one `DC_PLAN_ELIGIBILITY` event per newly-eligible employee per year, covering both census employees and new hires, with `effective_date = eligibility_effective_date` (exact computed date).

**Independent Test**:
```bash
duckdb dbt/simulation.duckdb "SELECT COUNT(*) FROM fct_yearly_events WHERE event_type = 'eligibility'"
# Must return > 0

duckdb dbt/simulation.duckdb "
  SELECT employee_id, COUNT(*) AS cnt FROM fct_yearly_events
  WHERE event_type = 'eligibility' GROUP BY employee_id HAVING COUNT(*) > 1"
# Must return 0 rows (no duplicates)
```

### Implementation for User Story 1

- [x] T005 [P] [US1] Add a `UNION ALL` block for `{{ ref('int_eligibility_events') }}` to `dbt/models/marts/fct_yearly_events.sql` in the SQL-mode `all_events` CTE, positioned after the `int_hiring_events` block (matching event priority order: hire=2, eligibility=3); select the same 18 columns as every other UNION branch, filtered to `simulation_year = {{ simulation_year }}`
- [x] T006 [P] [US1] Create `planalign_orchestrator/generators/eligibility.py` with `EligibilityEventGenerator` decorated with `@EventRegistry.register(EVENT_ELIGIBILITY)`, `event_type = EVENT_ELIGIBILITY`, `execution_order = 25`, `requires_hazard = False`, `supports_sql = True`, `dbt_models = ["int_plan_eligibility_determination", "int_eligibility_events"]`; `generate_events()` returns `[]` (SQL mode delegates to dbt); `validate_event()` checks `event_type == EVENT_ELIGIBILITY` and that `eligibility_date` is not None; import `EVENT_ELIGIBILITY` from `config.constants`
- [x] T007 [US1] Register `EligibilityEventGenerator` in `planalign_orchestrator/generators/__init__.py`: add `from planalign_orchestrator.generators.eligibility import EligibilityEventGenerator` to the import block alongside `EnrollmentEventGenerator`, and add `"EligibilityEventGenerator"` to `__all__`
- [x] T008 [P] [US1] Create `tests/test_eligibility_generator.py` with fast-marked pytest tests covering: `EligibilityEventGenerator.event_type == "eligibility"`; `EligibilityEventGenerator.execution_order == 25`; `generate_events()` returns `[]`; `validate_event()` returns `is_valid=True` for a valid eligibility payload; `validate_event()` returns `is_valid=False` when `event_type` is wrong; `EligibilityEventGenerator` appears in `EventRegistry.list_all()` output

**Checkpoint**: After T005–T008, run:
```bash
dbt run --select int_eligibility_events fct_yearly_events --vars '{"simulation_year": 2025}' --threads 1
pytest -m fast -k "eligib" -v
```
Both must pass. User Story 1 is independently complete.

---

## Phase 4: User Story 2 — Enrollment Events Always Preceded by Eligibility Events (Priority: P2)

**Goal**: A dbt data quality test encodes the prerequisite chain (eligibility → enrollment) so that any simulation run with enrollment events but missing eligibility events fails with a clear, actionable error.

**Independent Test**:
```bash
dbt test --select test_enrollment_requires_prior_eligibility --threads 1
# Must pass (0 violations) after Phase 3 is complete
```

### Implementation for User Story 2

- [x] T009 [US2] Create `dbt/tests/data_quality/test_enrollment_requires_prior_eligibility.sql` as a singular dbt test that returns rows (violations) when an employee has a `DC_PLAN_ENROLLMENT` event in `fct_yearly_events` but no `eligibility` event in the same `simulation_year` with `effective_date <= enrollment_effective_date`; use `{{ ref('fct_yearly_events') }}` twice (enrollment side and eligibility side) with a `LEFT JOIN … WHERE elig.employee_id IS NULL` anti-join pattern; use `{{ evt_eligibility() }}` and `{{ evt_enrollment() }}` macros for event type literals
- [x] T010 [US2] Verify `test_enrollment_requires_prior_eligibility` passes by running `dbt test --select test_enrollment_requires_prior_eligibility --threads 1`; if violations are returned, diagnose the mismatch between `int_eligibility_events` effective dates and `int_enrollment_events` effective dates and correct the eligibility date logic in `int_eligibility_events.sql` so enrollment effective dates are never earlier than their corresponding eligibility effective dates

**Checkpoint**: `dbt test --select test_enrollment_requires_prior_eligibility --threads 1` returns 0 violations. User Story 2 is independently complete.

---

## Phase 5: User Story 3 — Waiting Period Configuration Produces Observable Output (Priority: P3)

**Goal**: Confirm that changing `plan_eligibility_waiting_period_days` between otherwise-identical simulations produces `DC_PLAN_ELIGIBILITY` events with different `effective_date` values, demonstrating that the configuration change is fully observable in the event log.

**Independent Test**: Run two simulations with different waiting periods and compare eligibility event dates.

### Implementation for User Story 3

- [x] T011 [US3] Validate waiting-period observability by running two `dbt run` invocations against `int_eligibility_events` with different `plan_eligibility_waiting_period_days` values (e.g., 0 vs 90) and confirming that `effective_date` values shift by exactly 90 days for the same employees; document the verification query and result in a comment at the top of `dbt/models/intermediate/events/int_eligibility_events.sql`; no code change required if dates already differ correctly — this task is complete when the verification passes

**Checkpoint**: Two simulations produce eligibility event dates differing by exactly the waiting period delta. User Story 3 is complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, multi-year deduplication check, and final cleanup.

- [x] T012 [P] Run the full dbt build to confirm no regressions: `cd dbt && dbt build --threads 1 --fail-fast`; all previously passing tests must still pass; count of `eligibility` events in `fct_yearly_events` must be > 0
- [x] T013 [P] Run a multi-year simulation (`planalign simulate 2025-2027`) and verify that: (a) eligibility events appear in `fct_yearly_events` for each year's newly-eligible cohort; (b) no employee appears with eligibility events in more than one simulation year (deduplication invariant); use the verification queries in `specs/086-dc-eligibility-events/quickstart.md`

**Checkpoint**: All dbt tests pass, full simulation completes without errors, deduplication verified — feature is shippable.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001 and T002 are parallel
- **Foundational (Phase 2)**: Requires T001 + T002 — **BLOCKS all user story work**
- **User Story 1 (Phase 3)**: Requires T003 + T004; T005, T006, T008 can run in parallel; T007 requires T006
- **User Story 2 (Phase 4)**: Requires T005 (eligibility events in `fct_yearly_events`) to be complete so the test has data to validate against
- **User Story 3 (Phase 5)**: Requires T003 (model exists and computes exact dates)
- **Polish (Phase 6)**: Requires all story phases complete

### User Story Dependencies

```
T001, T002 (Setup)
    ↓
T003, T004 (Foundational — BLOCKS all stories)
    ↓
┌── T005, T006, T008 [parallel] ──┐
│   T007 (after T006)             │
└────── User Story 1 complete ────┘
    ↓
T009, T010 — User Story 2 complete
    ↓
T011 — User Story 3 complete
    ↓
T012, T013 [parallel] — Polish complete
```

### Within Phase 3 (User Story 1)

T005, T006, T008 can all start together (different files: `fct_yearly_events.sql`, `eligibility.py`, `test_eligibility_generator.py`). T007 starts after T006 (needs the class to exist before `__init__.py` imports it).

### Parallel Opportunities Summary

| Phase | Parallel Tasks | Constraint |
|-------|---------------|-----------|
| Phase 1 | T001 ∥ T002 | Different files |
| Phase 3 | T005 ∥ T006 ∥ T008 | Different files; T007 waits for T006 |
| Phase 6 | T012 ∥ T013 | Independent validation targets |

---

## Parallel Example: User Story 1

```bash
# All three can start simultaneously after T003 + T004:

Task A: "Add UNION ALL for int_eligibility_events in dbt/models/marts/fct_yearly_events.sql"
Task B: "Create planalign_orchestrator/generators/eligibility.py"
Task C: "Create tests/test_eligibility_generator.py"

# After Task B completes:
Task D: "Register EligibilityEventGenerator in planalign_orchestrator/generators/__init__.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: T001 + T002 (constants and macros)
2. Complete Phase 2: T003 + T004 (model + schema tests) — verify with `dbt run + dbt test`
3. Complete Phase 3: T005 + T006 + T007 + T008 — verify with `dbt run fct_yearly_events` and `pytest -m fast`
4. **STOP and VALIDATE**: Query `fct_yearly_events` for eligibility events; confirm count > 0, no duplicates

### Incremental Delivery

1. **MVP** (US1): Events generated → audit trail gap closed → demonstrates core value
2. **+US2**: Prerequisite chain test → regulatory compliance assertion added
3. **+US3**: Waiting period observability confirmed → simulation reproducibility verified
4. **Polish**: Multi-year simulation validates deduplication across all three stories

### Single Developer Sequence

`T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012 → T013`

Total estimated tasks: **13** across 6 phases.

---

## Notes

- `[P]` tasks write to different files and have no shared incomplete dependency — safe to parallelize
- T010 may reveal a date ordering issue if `eligibility_effective_date` is ever later than enrollment's `effective_date` for the same employee; the fix is in `int_eligibility_events.sql` (adjust the date computation)
- T003 is the most complex task — the incremental self-reference pattern (`{{ this }}`) for Year 2+ deduplication is critical; refer to `int_enrollment_events.sql` as the canonical example
- Commit after each phase checkpoint to preserve incremental progress
- Do not run `dbt build` until T005 is complete — `fct_yearly_events` will compile with a missing reference otherwise
