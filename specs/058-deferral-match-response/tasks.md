# Tasks: Match-Responsive Deferral Adjustments

**Input**: Design documents from `/specs/058-deferral-match-response/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Included — the constitution mandates test-first development (Principle III), and the spec explicitly lists test coverage in acceptance criteria.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Config + Pipeline Infrastructure)

**Purpose**: Configuration models, variable export, and pipeline registration that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T001 [P] Add `DeferralMatchResponseSettings` Pydantic v2 model to `planalign_orchestrator/config/workforce.py`. Include all fields from data-model.md Entity 2: `enabled` (bool, default False), `upward_participation_rate`, `upward_maximize_rate`, `upward_partial_increase_rate`, `upward_partial_increase_factor`, `downward_enabled`, `downward_participation_rate`, `downward_reduce_to_max_rate`, `downward_partial_decrease_rate`, `downward_partial_decrease_factor` (Decimal, default 0.50), `effective_timing`. Add model validators: upward rates sum to 1.0, downward rates sum to 1.0, all rates in [0.0, 1.0]. Follow `EmployerMatchSettings` pattern (same file, line ~250).

- [X] T002 [P] Add `deferral_match_response:` section to `config/simulation_config.yaml`. Place after the `deferral_rates:` section (~line 709). Include all config parameters with defaults matching data-model.md Entity 2 (including `downward_partial_decrease_factor: 0.50`). Set `enabled: false` as the default so the feature is opt-in and existing simulations are unaffected (FR-007).

- [X] T003 Add `_export_deferral_match_response_vars()` function to `planalign_orchestrator/config/export.py`. Export all settings as flat dbt variables prefixed with `deferral_match_response_` (see data-model.md Entity 3 for the complete variable list). Map `downward_partial_decrease_factor` → `deferral_match_response_downward_partial_factor`. Call this function from `to_dbt_vars()` (~line 809). Follow the pattern of `_export_employer_match_vars()` (~line 275).

- [X] T004 Add `int_deferral_match_response_events` to the EVENT_GENERATION stage models list in `planalign_orchestrator/pipeline/workflow.py`. Insert after `int_enrollment_events` (line 168) and before `int_deferral_rate_escalation_events` (line 169), so match-response fires before escalation per the clarified execution order (D1 in plan.md).

**Checkpoint**: Config loads successfully, dbt variables export correctly, pipeline includes the new model name. Verify: `python -c "from planalign_orchestrator.config import load_simulation_config; c = load_simulation_config('config/simulation_config.yaml'); print(c.deferral_match_response)"`

---

## Phase 2: User Story 1 — Upward Deferral Response to Match Improvement (Priority: P1) MVP

**Goal**: Generate upward deferral adjustment events for employees whose current deferrals fall below the match-maximizing rate, using deferral-based match mode. This is the core feature delivering the primary business value.

**Independent Test**: Run a simulation where census deferrals cluster below the match max (e.g., 3% deferral, 6% match max). Verify ~40% of below-max employees get upward adjustment events.

### Tests for User Story 1

- [X] T005 [P] [US1] Create dbt data quality test in `dbt/tests/data_quality/test_deferral_match_response.sql`. Validate: (1) no duplicate events per employee per year, (2) `employee_deferral_rate > prev_employee_deferral_rate` for all upward events, (3) `employee_deferral_rate <= escalation_cap` and `<= IRS 402(g) limit`, (4) all events have non-null `employee_id`, `event_details`, `event_type`. Follow the pattern in `dbt/tests/data_quality/test_deferral_escalation.sql`.

- [X] T006 [P] [US1] Add schema tests for the new model in `dbt/models/intermediate/events/schema.yml`. Add entry for `int_deferral_match_response_events` with: `unique_combination_of_columns` on `[employee_id, simulation_year]`, `not_null` on `employee_id` and `event_type`, `accepted_values` for event_type = `['deferral_match_response']`, `accepted_range` for `employee_deferral_rate` (0.0-1.0). Follow existing `int_synthetic_baseline_enrollment_events` pattern.

- [X] T007 [P] [US1] Update `fct_yearly_events` accepted_values test in `dbt/models/marts/schema.yml` to include `'deferral_match_response'` in the `event_type` accepted values list alongside existing types (`termination`, `promotion`, `hire`, `raise`, `enrollment`, `enrollment_change`, `deferral_escalation`).

### Implementation for User Story 1

- [X] T008 [US1] Create `dbt/models/intermediate/events/int_deferral_match_response_events.sql` — the core event generation model. Configure as `materialized='ephemeral'` with tags `['EVENT_GENERATION', 'E058_MATCH_RESPONSE']`. Implement the following CTEs:

  **Config variables** (top of file): Read all `deferral_match_response_*` variables with defaults. Read `employer_match_status`, `match_tiers`, `deferral_escalation_cap`, `irs_402g_limit`. Add first-year guard: `{% if var('deferral_match_response_enabled', false) and var('simulation_year') == var('start_year') %}` (D5 in plan.md).

  **match_maximizing_rate CTE**: For `deferral_based` mode, calculate `MAX(employee_max)` from `match_tiers` variable array. This is the target rate all employees are compared against. Output a single scalar value. (Service/tenure/points modes deferred to US4.)

  **eligible_employees CTE**: Join `int_employee_compensation_by_year` (active employees with demographics) with deferral rates:
  - Year 1 (`start_year`): Read from `int_enrollment_events` and `int_synthetic_baseline_enrollment_events` (same pattern as `int_deferral_rate_escalation_events.sql` lines 86-117).
  - Year 2+: Read from `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` where `simulation_year = {{ prev_year }}` (direct table reference, NOT `ref()`, to avoid circular deps — R7 in research.md).
  - Filter: enrolled = true, employment_status = active, NOT a new hire in current simulation year (FR-012).

  **upward_response_candidates CTE**: Filter eligible employees where `current_deferral_rate < match_maximizing_rate`. Calculate deterministic hash: `(ABS(HASH(employee_id || '-match-response-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0` (D4 in plan.md). Filter by `hash_value < upward_participation_rate`.

  **upward_events CTE**: For selected candidates, calculate new rate:
  - Maximizers (`hash_value < participation_rate * maximize_rate`): `new_rate = match_maximizing_rate`
  - Partial responders: `new_rate = current_rate + partial_factor * (match_maximizing_rate - current_rate)`, rounded to nearest 0.005 (0.5% increment).
  - Cap at `LEAST(new_rate, deferral_escalation_cap, irs_402g_limit / compensation)` (FR-014).

  **Output SELECT**: Produce columns matching `fct_yearly_events` schema (see data-model.md Entity 1 for full column list). Set `event_type = 'deferral_match_response'`, `event_category = 'match_response'`. Build `event_details` string: `'Match response: ' || prev_rate || '% → ' || new_rate || '% (' || response_type || ', target ' || match_max || '%)'`.

  **Empty result for disabled/non-first-year**: `{% else %}` branch returns `SELECT ... WHERE FALSE` with correct column types.

- [X] T009 [US1] Modify `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` to merge match-response events as a fourth source. Add three items:

  **(a) New CTE** `match_response_events` (~after enrollment_events CTE, around line 180): Read from `{{ ref('int_deferral_match_response_events') }}`. Filter by `simulation_year <= {{ simulation_year }}`. Cast to standard types matching existing CTEs.

  **(b) New CTE** `employee_match_response_summary`: Aggregate by employee_id. Output: `latest_match_responsive_rate` (MAX), `last_match_response_date` (MAX), `total_match_responsive_adjustments` (COUNT), `had_match_responsive_this_year` (BOOL_OR on current year).

  **(c) Update `final_state`**: Replace the simple COALESCE with the additive CASE logic from D2 in plan.md:
  ```
  CASE
    WHEN mr.match_responsive_rate IS NOT NULL AND e.escalation_rate IS NOT NULL
      THEN LEAST(
        mr.match_responsive_rate + e.escalation_rate,
        deferral_escalation_cap,
        irs_402g_limit / NULLIF(comp.compensation_amount, 0)
      )
    WHEN e.latest_deferral_rate IS NOT NULL THEN e.latest_deferral_rate
    WHEN mr.match_responsive_rate IS NOT NULL THEN mr.match_responsive_rate
    ELSE NULL
  END
  ```
  The IRS 402(g) rate-equivalent cap is critical for the additive case: two individually-capped rates can still sum above the IRS limit (FR-014).
  Add LEFT JOIN on `employee_match_response_summary`. Add output columns: `match_responsive_adjustments_received`, `last_match_response_date`, `has_match_responsive_adjustments`.

**Checkpoint**: Run `planalign simulate 2025 --verbose` with `deferral_match_response.enabled: true`. Verify events in `fct_yearly_events` where `event_type = 'deferral_match_response'`. Check that ~40% of below-max employees have events. Verify adjusted rates appear in `int_deferral_rate_state_accumulator_v2`.

---

## Phase 3: User Story 2 — Downward Deferral Response to Match Reduction (Priority: P2)

**Goal**: Add downward deferral adjustment logic for employees deferring above the match-maximizing rate. Implements asymmetric behavior (weaker downward response).

**Independent Test**: Run a simulation where census deferrals cluster above the match max (e.g., 8% deferral, 3% match max). Verify ~15% of above-max employees get downward adjustment events.

### Implementation for User Story 2

- [X] T010 [US2] Extend `dbt/models/intermediate/events/int_deferral_match_response_events.sql` with downward response logic. Add new CTEs:

  **downward_response_candidates CTE**: Filter eligible employees where `current_deferral_rate > match_maximizing_rate` AND `deferral_match_response_downward_enabled = true`. Use same deterministic hash but with a different sub-salt (e.g., `'-match-response-down-'`) to ensure independent selection from upward candidates. Filter by `hash_value < downward_participation_rate`.

  **downward_events CTE**: For selected candidates, calculate new rate:
  - Reducers (`hash_value < participation_rate * reduce_to_max_rate`): `new_rate = match_maximizing_rate`
  - Partial reducers: `new_rate = current_rate - partial_factor * (current_rate - match_maximizing_rate)`, rounded to nearest 0.005.
  - Floor at 0.0 (cannot have negative deferral rate).
  - When match is completely removed (match_maximizing_rate = 0%), all enrolled employees above 0% are candidates per clarification.

  **UNION**: Combine `upward_events UNION ALL downward_events` in the output SELECT. Add `response_direction` ('upward'/'downward') to `event_details` string.

- [X] T011 [US2] Update `dbt/tests/data_quality/test_deferral_match_response.sql` to add downward-specific validations: (1) `employee_deferral_rate < prev_employee_deferral_rate` for downward events, (2) `employee_deferral_rate >= 0.0` floor check, (3) no employee has BOTH an upward and downward event in the same year.

**Checkpoint**: Run simulation with census deferrals above match max. Verify ~15% downward events exist and downward count is lower than upward count for comparable populations.

---

## Phase 4: User Story 3 — Feature Toggle and Configuration (Priority: P2)

**Goal**: Verify that the feature toggle works correctly: disabled produces zero events, custom config values propagate, and downward can be independently disabled.

**Independent Test**: Run same simulation twice (enabled vs disabled), confirm zero events when disabled and correct distribution when enabled with custom values.

### Tests for User Story 3

- [X] T012 [US3] Create Python integration test file `tests/test_match_response_events.py`. Follow the pattern in `tests/test_escalation_events.py`. Implement test class with:

  **(a)** `test_no_events_when_disabled`: Connect to `dbt/simulation.duckdb` (read-only), query `fct_yearly_events WHERE event_type = 'deferral_match_response'`, assert count = 0 when feature is disabled. Skip if DB doesn't exist.

  **(b)** `test_events_generated_when_enabled`: Assert count > 0 when feature is enabled.

  **(c)** `test_upward_events_have_increasing_rates`: Assert `employee_deferral_rate > prev_employee_deferral_rate` for all upward match-response events.

  **(d)** `test_rate_cap_enforcement`: Assert `employee_deferral_rate <= escalation_cap + 0.0001` for all events (small tolerance for floating point).

  **(e)** `test_event_audit_fields_complete`: Assert `event_details IS NOT NULL` and contains 'Match response:' for all events.

  Mark all tests `@pytest.mark.integration`. Use `get_database_path()` with fallback to `Path("dbt/simulation.duckdb")`.

**Checkpoint**: `pytest tests/test_match_response_events.py -v` passes for the current simulation state. Toggle config and verify behavior changes.

---

## Phase 5: User Story 4 — All Match Mode Compatibility (Priority: P3)

**Goal**: Extend match-maximizing rate calculation to work with service-based, tenure-based, and points-based match modes (in addition to the deferral-based mode already implemented in US1).

**Independent Test**: Change `employer_match_status` to each mode and verify correct match-maximizing rate per employee.

### Implementation for User Story 4

- [X] T013 [P] [US4] Extend the `match_maximizing_rate` CTE in `dbt/models/intermediate/events/int_deferral_match_response_events.sql` to handle all four match modes. Add branching logic on `employer_match_status`:

  **(a)** `deferral_based` (already done in US1): `MAX(employee_max)` from `match_tiers` array.

  **(b)** `graded_by_service`: Use `{{ get_tiered_match_max_deferral('years_of_service', employer_match_graded_schedule, 0.06) }}` macro. This returns a per-employee rate based on their service years. Join with `int_employee_compensation_by_year` for `years_of_service`.

  **(c)** `tenure_based`: Use tenure tiers from `tenure_match_tiers` variable. Apply same `get_tiered_match_max_deferral()` macro pattern with tenure column.

  **(d)** `points_based`: Calculate points = `FLOOR(current_age) + FLOOR(years_of_service)`. Use `points_match_tiers` variable. Apply `get_points_based_match_rate()` macro pattern to derive `max_deferral_pct` for the employee's points tier.

  Use Jinja `{% if %}` branching on `employer_match_status` variable to emit the correct SQL for each mode. When mode is not `deferral_based`, the match-maximizing rate varies per employee (not a constant).

**Checkpoint**: Test each match mode by changing `employer_match_status` in config and running a simulation. Verify match-maximizing rates match expected values from tier configurations.

---

## Phase 6: User Story 5 — Integration with Auto-Escalation (Priority: P3)

**Goal**: Verify that match-response and auto-escalation work additively in the same year and across multi-year simulations. The accumulator logic from T009 handles this; this phase validates it.

**Independent Test**: Run a 2025-2027 simulation. Verify Year 1: match response (3%→6%) + escalation (6%→7%) = 7%. Year 2: escalation (7%→8%).

### Implementation for User Story 5

- [X] T014 [US5] Add multi-year integration tests to `tests/test_match_response_events.py`:

  **(a)** `test_additive_with_escalation_same_year`: Query employees who have BOTH `deferral_match_response` and `deferral_escalation` events in the same year. Verify the accumulator's `current_deferral_rate` equals `match_response_rate + escalation_increment` (within tolerance). This validates the additive CASE logic in the accumulator (D2 in plan.md).

  **(b)** `test_escalation_builds_on_adjusted_rate_year2`: For a multi-year simulation, query Year 2 escalation events and verify `prev_employee_deferral_rate` matches the Year 1 combined (match-response + escalation) rate, not the original census rate. This validates temporal state continuity.

  **(c)** `test_cap_enforcement_combined`: Verify that no employee's `current_deferral_rate` exceeds the escalation cap even when match-response + escalation would push them above it.

**Checkpoint**: `pytest tests/test_match_response_events.py -v -k "escalation"` passes for a multi-year simulation run.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, edge cases, and cleanup

- [X] T015 Run end-to-end validation per `specs/058-deferral-match-response/quickstart.md` Step 5. Execute full simulation, check event counts, verify distribution matches config parameters. **SC-003 coverage**: Query `fct_workforce_snapshot` or match calculations to compare total employer match costs between an enabled run and a disabled baseline — verify that upward deferral responses produce a measurable increase in employer match costs.

- [X] T016 Verify edge cases from spec.md: (1) employee at exact match-max gets no event, (2) terminated employees excluded, (3) new hires excluded, (4) flat match formula uses plan max or IRS 402(g) as cap. Add specific assertions to `dbt/tests/data_quality/test_deferral_match_response.sql` if not already covered.

- [X] T017 Verify disabled-mode backward compatibility (SC-005): Run simulation with `enabled: false`, compare `fct_yearly_events` and `fct_workforce_snapshot` counts against a known-good baseline to confirm zero impact.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: Depends on Phase 1 completion — CORE MVP
- **US2 (Phase 3)**: Depends on Phase 2 (extends the event model created in US1)
- **US3 (Phase 4)**: Depends on Phase 2 (tests the config created in Phase 1 + events from US1)
- **US4 (Phase 5)**: Depends on Phase 2 (extends the match-maximizing rate CTE from US1)
- **US5 (Phase 6)**: Depends on Phase 2 (validates accumulator logic from US1)
- **Polish (Phase 7)**: Depends on all preceding phases

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational — no other story dependencies. **This is the MVP.**
- **US2 (P2)**: Depends on US1 (extends the same event model file)
- **US3 (P2)**: Can start after US1 (tests require events to exist). Can run in parallel with US2.
- **US4 (P3)**: Can start after US1 (extends the same event model file). Serialized with US2 (same file).
- **US5 (P3)**: Can start after US1 (validates accumulator). Can run in parallel with US2/US4.

### Within Each User Story

- Tests written first where applicable (T005-T007 before T008-T009)
- Model creation before accumulator integration
- Core implementation before edge case handling

### Parallel Opportunities

- **Phase 1**: T001, T002 can run in parallel (different files). T003 depends on T001. T004 is independent.
- **Phase 2**: T005, T006, T007 can run in parallel (different test files). T008 then T009 sequential (model before accumulator).
- **After US1**: US3 and US5 can run in parallel with US2 (different files). US4 must serialize with US2 (same model file).

---

## Parallel Example: User Story 1

```bash
# Launch all tests in parallel (different files):
Task: "T005 - dbt data quality test in dbt/tests/data_quality/test_deferral_match_response.sql"
Task: "T006 - Schema tests in dbt/models/intermediate/events/schema.yml"
Task: "T007 - Update accepted_values in dbt/models/marts/schema.yml"

# Then sequential implementation:
Task: "T008 - Create event model (must exist before accumulator reads it)"
Task: "T009 - Modify accumulator to merge events (depends on T008)"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Foundational (config + pipeline)
2. Complete Phase 2: US1 tests + event model + accumulator integration
3. **STOP and VALIDATE**: Run simulation, verify upward events generated, rates flow through accumulator
4. This alone delivers the core business value: employees responding to match improvements

### Incremental Delivery

1. Phase 1 → Foundational ready
2. Phase 2 (US1) → Upward response working → **MVP deployed**
3. Phase 3 (US2) → Downward response added → Asymmetric modeling complete
4. Phase 4 (US3) → Toggle verified → Production-safe configuration
5. Phase 5 (US4) → All match modes → Full feature parity
6. Phase 6 (US5) → Multi-year validated → Long-term accuracy confirmed
7. Phase 7 → Polish → Release-ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently testable after implementation
- Commit after each task or logical group
- Reference patterns: `int_deferral_rate_escalation_events.sql` (event model), `int_voluntary_enrollment_decision.sql` (hash selection), `_export_employer_match_vars()` (config export)
- The event model (`int_deferral_match_response_events.sql`) is the largest single file (~200 lines). US2 and US4 extend it — coordinate to avoid merge conflicts.
