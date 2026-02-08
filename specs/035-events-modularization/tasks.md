# Tasks: Events Module Modularization

**Input**: Design documents from `/specs/035-events-modularization/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Test tasks included for User Story 4 (FR-007 explicitly requires validator tests).

**Organization**: Tasks grouped by user story to enable independent implementation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Project structure**: `config/events/` (new package), `tests/unit/` (test files)
- Refactoring existing `config/events.py` (1,056 lines) into modular package

---

## Phase 1: Setup

**Purpose**: Create package structure and foundational validators module

- [x] T001 Create events package directory at config/events/
- [x] T002 Create package init file at config/events/__init__.py with minimal exports
- [x] T003 Create shared validators module at config/events/validators.py with quantize_amount, quantize_rate, quantize_amount_dict functions per contracts/validators.py

**Checkpoint**: Package structure exists, validators module ready for use by payload modules ✅

---

## Phase 2: Foundational (Domain Payload Modules)

**Purpose**: Extract all 14 payload classes from config/events.py into domain-specific modules. MUST complete before User Story 1 can be tested.

**⚠️ CRITICAL**: These modules must exist before the compatibility layer can re-export them.

- [x] T004 [P] Create workforce payloads module at config/events/workforce.py containing HirePayload, PromotionPayload, TerminationPayload, MeritPayload, SabbaticalPayload - import validators from .validators
- [x] T005 [P] Create DC plan payloads module at config/events/dc_plan.py containing EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload, AutoEnrollmentWindowPayload, EnrollmentChangePayload - import validators from .validators
- [x] T006 [P] Create admin payloads module at config/events/admin.py containing ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload - import validators from .validators
- [x] T007 Create core module at config/events/core.py containing SimulationEvent, LegacySimulationEvent alias, EventFactory, WorkforceEventFactory, DCPlanEventFactory, PlanAdministrationEventFactory - import all payloads from domain modules

**Checkpoint**: All modules created with correct content; core.py has discriminated union with all payloads ✅

---

## Phase 3: User Story 1 - Navigate to Domain-Specific Event Code (Priority: P1) 🎯 MVP

**Goal**: Developers can locate any payload class within 3 domain-specific files instead of scrolling through 1,000+ lines

**Independent Test**: Open config/events/dc_plan.py and verify ContributionPayload is there without workforce/admin code

### Implementation for User Story 1

- [x] T008 [US1] Update config/events/__init__.py to re-export all symbols from workforce.py, dc_plan.py, admin.py, core.py
- [x] T009 [US1] Verify each domain module contains ONLY its domain payloads (no cross-domain classes)
- [x] T010 [US1] Verify module line counts: workforce.py < 150, dc_plan.py < 250, admin.py < 120

**Checkpoint**: User Story 1 complete - developers can navigate to domain-specific modules ✅

---

## Phase 4: User Story 2 - Import Events Using Existing Paths (Priority: P1)

**Goal**: 100% backward compatibility - all existing `from config.events import X` statements work unchanged

**Independent Test**: Run existing test suite (256+ tests) with zero import errors

### Implementation for User Story 2

- [x] T011 [US2] Replace config/events.py content with compatibility layer that re-exports from config.events subpackage
- [x] T012 [US2] Preserve exact __all__ list in config/events.py matching original (26 symbols)
- [x] T013 [US2] Preserve re-exports from planalign_orchestrator.generators (EventRegistry, EventGenerator, EventContext, ValidationResult, GeneratorMetrics)
- [x] T014 [US2] Run full test suite: pytest tests/unit/events/ -v to verify all imports resolve
- [x] T015 [US2] Run extended test suite: pytest -m fast to verify no regressions across codebase

**Checkpoint**: User Story 2 complete - all 256+ existing tests pass without import changes ✅

---

## Phase 5: User Story 3 - Use Shared Validators Without Duplication (Priority: P2)

**Goal**: Payload classes use shared validator functions instead of duplicated inline validators

**Independent Test**: Create a test payload using shared validators and verify quantization works

### Implementation for User Story 3

- [x] T016 [US3] Verify HirePayload in workforce.py uses quantize_amount from .validators
- [x] T017 [US3] Verify EnrollmentPayload in dc_plan.py uses quantize_rate from .validators
- [x] T018 [US3] Verify VestingPayload in dc_plan.py uses quantize_amount_dict from .validators
- [x] T019 [US3] Verify all 14 payload classes use shared validators (no inline quantize calls)
- [x] T020 [US3] Count validator usage: confirm ~15 inline validators replaced by 3 shared functions

**Checkpoint**: User Story 3 complete - all payloads use shared validators ✅

---

## Phase 6: User Story 4 - Test Shared Validators Independently (Priority: P3)

**Goal**: Shared validators have their own unit tests for edge cases

**Independent Test**: Run pytest tests/unit/test_validators.py -v

### Tests for User Story 4

- [x] T021 [P] [US4] Create test file at tests/unit/test_validators.py with test class structure
- [x] T022 [P] [US4] Add test_quantize_amount_precision: verify Decimal("100000.123456789") → Decimal("100000.123457")
- [x] T023 [P] [US4] Add test_quantize_amount_zero: verify Decimal("0") → Decimal("0.000000")
- [x] T024 [P] [US4] Add test_quantize_rate_precision: verify Decimal("0.12345") → Decimal("0.1234") (banker's rounding)
- [x] T025 [P] [US4] Add test_quantize_rate_bounds: verify Decimal("0") and Decimal("1") work correctly
- [x] T026 [P] [US4] Add test_quantize_amount_dict: verify dictionary values are quantized
- [x] T027 [P] [US4] Add test_quantize_rate_optional: verify None passthrough and Decimal quantization

### Validation for User Story 4

- [x] T028 [US4] Run pytest tests/unit/test_validators.py -v and verify all tests pass (21 tests)
- [x] T029 [US4] Verify test coverage for edge cases: zero, large numbers, negative (for amount), boundary rates

**Checkpoint**: User Story 4 complete - validators have comprehensive test coverage ✅

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T030 [P] Verify each module has proper docstring header explaining its purpose
- [x] T031 [P] Verify no circular imports by running: python -c "from config.events import SimulationEvent"
- [x] T032 [P] Verify line counts: wc -l config/events/*.py (each < 300 lines except core.py with factories at 633)
- [x] T033 Run full integration test: pytest -m fast --tb=short (463 passed, 5 failed unrelated to events)
- [x] T034 Run quickstart.md validation: verify examples work
- [x] T035 Delete or archive original monolithic content from config/events.py (now a thin re-export layer)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - creates package structure
- **Foundational (Phase 2)**: Depends on Setup - creates all domain modules [P] parallelizable
- **User Story 1 (Phase 3)**: Depends on Foundational - verifies domain separation
- **User Story 2 (Phase 4)**: Depends on Foundational - creates compatibility layer
- **User Story 3 (Phase 5)**: Depends on User Story 1 - verifies shared validator usage
- **User Story 4 (Phase 6)**: Depends on Setup (validators.py) - can run parallel with US1-3
- **Polish (Phase 7)**: Depends on all user stories

### User Story Dependencies

```
Setup (Phase 1)
    │
    ├──> T004, T005, T006, T007 (Foundational - parallel)
    │           │
    │           v
    │    ┌──────┴──────┐
    │    │             │
    │    v             v
    │  US1 (P1)      US2 (P1)
    │    │             │
    │    v             │
    │  US3 (P2) <──────┘
    │
    └──> US4 (P3) ← Can run parallel with US1-3
              │
              v
          Polish (Phase 7)
```

### Within Each User Story

- Models/modules must exist before verification tasks
- Compatibility layer (US2) must complete before running full test suite
- Tests (US4) written before counting as complete

### Parallel Opportunities

- **Phase 2**: T004, T005, T006 can run in parallel (different files)
- **Phase 6**: T021-T027 can all run in parallel (independent test cases)
- **Phase 7**: T030, T031, T032 can run in parallel (independent validations)
- **Cross-story**: US4 can run in parallel with US1-3 (no dependencies)

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch all domain module creation in parallel:
Task: "Create workforce payloads module at config/events/workforce.py"
Task: "Create DC plan payloads module at config/events/dc_plan.py"
Task: "Create admin payloads module at config/events/admin.py"

# Then sequentially (depends on above):
Task: "Create core module at config/events/core.py"
```

## Parallel Example: User Story 4 Tests

```bash
# Launch all validator tests in parallel:
Task: "Add test_quantize_amount_precision in tests/unit/test_validators.py"
Task: "Add test_quantize_amount_zero in tests/unit/test_validators.py"
Task: "Add test_quantize_rate_precision in tests/unit/test_validators.py"
Task: "Add test_quantize_rate_bounds in tests/unit/test_validators.py"
Task: "Add test_quantize_amount_dict in tests/unit/test_validators.py"
Task: "Add test_quantize_rate_optional in tests/unit/test_validators.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T007)
3. Complete Phase 3: User Story 1 (T008-T010) - Domain navigation works
4. Complete Phase 4: User Story 2 (T011-T015) - Backward compatibility verified
5. **STOP and VALIDATE**: Run `pytest -m fast` - all tests pass
6. Can deploy/merge at this point - core value delivered

### Incremental Delivery

1. MVP (US1 + US2) → Backward-compatible modular structure
2. Add US3 → Verify shared validators in use
3. Add US4 → Full test coverage for validators
4. Polish → Documentation and final validation

### Task Summary

| Phase | Tasks | Parallel Opportunities |
|-------|-------|------------------------|
| Setup | 3 | 0 |
| Foundational | 4 | 3 (T004-T006) |
| US1 | 3 | 0 |
| US2 | 5 | 0 |
| US3 | 5 | 0 |
| US4 | 9 | 7 (T021-T027) |
| Polish | 6 | 3 (T030-T032) |
| **Total** | **35** | **13** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- US1 + US2 together form the MVP (backward-compatible modular structure)
- US4 (tests) explicitly required by FR-007 in spec
- Commit after each phase completion
- Stop at any checkpoint to validate independently
