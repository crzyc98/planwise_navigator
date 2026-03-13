# Tasks: Fix DC Plan Match/Core Contributions When Disabled

**Input**: Design documents from `/specs/069-fix-match-core-disabled/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Included — Constitution III (Test-First Development) applies.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No setup needed — all infrastructure exists. This is a surgical bug fix to existing files.

*(No tasks — skip to Phase 2)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the `employer_match_enabled` variable to the config export pipeline. This MUST be complete before dbt model changes.

- [x] T001 Read `match_enabled` from `dc_plan` dict and export as `employer_match_enabled` dbt variable in `planalign_orchestrator/config/export.py` inside `_export_employer_match_vars()` after line 445 (inside the `dc_plan` processing block). Follow the exact pattern from `_export_core_contribution_vars()` lines 799-801. Add: `match_enabled = dc_plan_dict.get("match_enabled")` then `if match_enabled is not None: dbt_vars["employer_match_enabled"] = bool(match_enabled)`
- [x] T002 Add test for `employer_match_enabled` export in `tests/test_config_export.py`. Test that when `dc_plan.match_enabled` is `false`, `employer_match_enabled` is exported as `false`. Test that when `dc_plan.match_enabled` is `true`, it exports as `true`. Test that when `match_enabled` is not set, `employer_match_enabled` is not in the exported vars (dbt default handles it).

**Checkpoint**: Config export now propagates the match enabled flag. dbt model changes can proceed.

---

## Phase 3: User Story 1 - Disabling Employer Match Stops Match Calculations (Priority: P1)

**Goal**: When `match_enabled: false` in scenario config, all employer match amounts are $0 and match_status is 'disabled'.

**Independent Test**: Run `dbt run --select int_employee_match_calculations --vars '{"simulation_year": 2025, "employer_match_enabled": false}' --threads 1` then query `SELECT SUM(employer_match_amount) FROM int_employee_match_calculations` — expect 0.00.

### Implementation for User Story 1

- [x] T003 [US1] Add `{% set employer_match_enabled = var('employer_match_enabled', true) %}` variable definition in `dbt/models/intermediate/events/int_employee_match_calculations.sql` after the existing variable definitions (after line 73, near the other `{% set %}` blocks)
- [x] T004 [US1] Add master gate in the `final_match` CTE in `dbt/models/intermediate/events/int_employee_match_calculations.sql`. When `employer_match_enabled` is false, set `employer_match_amount` to 0, `capped_match_amount` to 0, `match_status` to 'disabled', `uncapped_match_amount` to 0, and `match_cap_applied` to FALSE. Use `{% if employer_match_enabled %}...{% else %}...{% endif %}` wrapping the existing CASE expressions for these columns in the `final_match` CTE (lines 354-388). Preserve all other columns unchanged.
- [x] T005 [US1] Verify backward compatibility: run `dbt run --select int_employee_match_calculations --vars '{"simulation_year": 2025}' --threads 1` (no `employer_match_enabled` set) and confirm match amounts are calculated normally (default=true, no regression)

**Checkpoint**: Disabling match via dbt variable produces $0 match. Enabling (or not setting) produces normal results.

---

## Phase 4: User Story 2 - Verify Core Contribution Disabled Path (Priority: P1)

**Goal**: Confirm the existing `employer_core_enabled` flag works end-to-end from UI toggle to $0 core contribution.

**Independent Test**: Run `dbt run --select int_employer_core_contributions --vars '{"simulation_year": 2025, "employer_core_enabled": false}' --threads 1` then query `SELECT SUM(employer_core_amount) FROM int_employer_core_contributions` — expect 0.00.

### Implementation for User Story 2

- [x] T006 [US2] Verify core path end-to-end: run the dbt model with `employer_core_enabled: false` and confirm all `employer_core_amount` values are 0.00 in `dbt/models/intermediate/int_employer_core_contributions.sql`. This is a verification task — the code is already wired (export.py:799-801, dbt model:250). If verification passes, no code changes needed. If it fails, trace and fix the broken link.

**Checkpoint**: Core contribution disabled path verified working.

---

## Phase 5: User Story 3 - Match/Core Disabled State Persists Across Sessions (Priority: P2)

**Goal**: The enabled/disabled state round-trips correctly through save/reload in the UI.

**Independent Test**: In PlanAlign Studio, disable match, save scenario, reload page, confirm toggle shows disabled.

### Implementation for User Story 3

- [x] T007 [US3] Verify that `ConfigContext.tsx` correctly loads `match_enabled` from the API response into `dcMatchEnabled` form state. Check `planalign_studio/components/config/ConfigContext.tsx` line 160 where `dcMatchEnabled` is set from `cfg.dc_plan?.match_enabled`. Confirm the API returns `match_enabled` in the scenario config response. If the round-trip works, no code changes needed. If it fails, fix the missing link.

**Checkpoint**: All user stories complete and independently testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation across all stories

- [x] T008 Run full end-to-end verification per quickstart.md: run simulation with match disabled via CLI, verify $0 match; run with match enabled, verify normal amounts; run with core disabled, verify $0 core
- [x] T009 Run existing test suite to confirm no regressions: `pytest -m fast` and `cd dbt && dbt test --threads 1`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — start immediately
- **User Story 1 (Phase 3)**: Depends on T001 (config export must propagate the flag first)
- **User Story 2 (Phase 4)**: No dependencies on other stories — can run in parallel with US1
- **User Story 3 (Phase 5)**: No dependencies on US1/US2 — can run in parallel
- **Polish (Phase 6)**: Depends on US1 + US2 completion

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2 (T001). This is the primary fix.
- **User Story 2 (P1)**: Independent — verification only, no code changes expected.
- **User Story 3 (P2)**: Independent — verification only, no code changes expected.

### Within Each User Story

- T001 (export.py) must complete before T003/T004 (dbt model)
- T003 (variable definition) must complete before T004 (gate logic)
- T005 (backward compat verification) depends on T003+T004

### Parallel Opportunities

- T006 (US2 core verification) can run in parallel with T003/T004 (US1 match implementation)
- T007 (US3 persistence verification) can run in parallel with all other stories
- T002 (test) can run in parallel with T006 and T007

---

## Parallel Example: Phase 2 + User Story 2/3

```bash
# After T001 completes, these can all run in parallel:
Task T002: "Add test for employer_match_enabled export in tests/test_config_export.py"
Task T006: "Verify core path end-to-end in int_employer_core_contributions.sql"
Task T007: "Verify ConfigContext.tsx round-trip for match_enabled"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001 (config export fix — 3 lines)
2. Complete T003 + T004 (dbt model gate — ~10 lines)
3. Complete T005 (backward compatibility verification)
4. **STOP and VALIDATE**: Match disabled = $0, match enabled = normal amounts
5. This alone fixes the reported bug

### Incremental Delivery

1. T001 → T003 → T004 → T005 → **Match bug fixed** (MVP!)
2. T006 → **Core verified working** (confidence)
3. T007 → **Persistence verified** (completeness)
4. T002 + T008 + T009 → **Tests and regression checks** (quality)

---

## Notes

- Total scope: ~30 lines of code changes across 2 production files + 1 test file
- US2 and US3 are verification tasks — no code changes expected based on research
- The fix follows the proven `employer_core_enabled` pattern exactly
- Default `true` ensures zero regression for existing scenarios
