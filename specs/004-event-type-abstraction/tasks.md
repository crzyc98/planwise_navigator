# Tasks: Event Type Abstraction Layer

**Input**: Design documents from `/specs/004-event-type-abstraction/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included per Constitution Principle III (Test-First Development)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `planalign_orchestrator/`, `config/`, `tests/` at repository root
- Tests use existing fixtures from `tests/fixtures/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and package structure

- [x] T001 Create generators package directory structure at planalign_orchestrator/generators/
- [x] T002 Create package init file at planalign_orchestrator/generators/__init__.py with exports
- [x] T003 [P] Create test fixtures file at tests/fixtures/generators.py with mock generators

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement EventContext dataclass in planalign_orchestrator/generators/base.py
- [x] T005 [P] Implement ValidationResult dataclass in planalign_orchestrator/generators/base.py
- [x] T006 [P] Implement GeneratorMetrics dataclass in planalign_orchestrator/generators/base.py
- [x] T007 Implement EventGenerator abstract base class with @abstractmethod decorators in planalign_orchestrator/generators/base.py
- [x] T008 Implement EventRegistry singleton class in planalign_orchestrator/generators/registry.py
- [x] T009 [P] Add unit tests for EventRegistry in tests/unit/test_event_registry.py
- [x] T010 Export base classes from planalign_orchestrator/generators/__init__.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Add a New Event Type (Priority: P1) 🎯 MVP

**Goal**: Developers can add new event types by implementing a single interface and registering in one location

**Independent Test**: Create a SABBATICAL event type and verify it generates events without modifying existing logic

### Tests for User Story 1

- [x] T011 [P] [US1] Contract test for EventGenerator interface in tests/unit/test_event_generator_interface.py
- [x] T012 [P] [US1] Integration test for new event type registration in tests/integration/test_new_event_type.py

### Implementation for User Story 1

- [x] T013 [P] [US1] Create SabbaticalPayload Pydantic model in config/events.py
- [x] T014 [US1] Add SabbaticalPayload to SimulationEvent discriminated union in config/events.py
- [x] T015 [US1] Implement SabbaticalEventGenerator in planalign_orchestrator/generators/sabbatical.py
- [x] T016 [US1] Register SabbaticalEventGenerator with @EventRegistry.register decorator in planalign_orchestrator/generators/sabbatical.py
- [x] T017 [US1] Add sabbatical import to planalign_orchestrator/generators/__init__.py
- [x] T018 [US1] Add structured logging for event generation in planalign_orchestrator/generators/base.py (FR-011)
- [x] T019 [US1] Add clear error messages for missing interface methods in planalign_orchestrator/generators/base.py (FR-007)

**Checkpoint**: New event types can be added via single interface + registry entry

---

## Phase 4: User Story 2 - Preserve Existing Event Behavior (Priority: P1)

**Goal**: Existing events (HIRE, TERMINATION, PROMOTION, MERIT, ENROLLMENT) produce identical results after refactoring

**Independent Test**: Compare simulation outputs before/after with random_seed=42 for byte-identical results

### Tests for User Story 2

- [x] T020 [P] [US2] Create baseline snapshot test in tests/integration/test_event_parity.py capturing current output
- [x] T021 [P] [US2] Implement parity comparison test in tests/integration/test_event_parity.py

### Implementation for User Story 2

- [x] T022 [P] [US2] Implement TerminationEventGenerator wrapper in planalign_orchestrator/generators/termination.py
- [x] T023 [P] [US2] Implement HireEventGenerator wrapper in planalign_orchestrator/generators/hire.py
- [x] T024 [P] [US2] Implement PromotionEventGenerator wrapper in planalign_orchestrator/generators/promotion.py
- [x] T025 [P] [US2] Implement MeritEventGenerator wrapper in planalign_orchestrator/generators/merit.py
- [x] T026 [P] [US2] Implement EnrollmentEventGenerator wrapper in planalign_orchestrator/generators/enrollment.py
- [x] T027 [US2] Add all wrapper imports to planalign_orchestrator/generators/__init__.py
- [x] T028 [US2] Integrate EventRegistry into EventGenerationExecutor in planalign_orchestrator/pipeline/event_generation_executor.py
- [x] T029 [US2] Update _get_event_generation_models() to use registry lookup in planalign_orchestrator/pipeline/event_generation_executor.py
- [x] T030 [US2] Run parity test to verify byte-identical output

**Checkpoint**: All existing event types work identically through new abstraction layer

---

## Phase 5: User Story 3 - Centralized Event Registration (Priority: P2)

**Goal**: All event types registered in single location with audit capability and scenario-specific enable/disable

**Independent Test**: Inspect config/events.py and verify complete list of event types; test disable/enable per scenario

### Tests for User Story 3

- [x] T031 [P] [US3] Test registry introspection (list_all, list_enabled) in tests/unit/test_event_registry.py
- [x] T032 [P] [US3] Test scenario-specific disable/enable in tests/unit/test_event_registry.py

### Implementation for User Story 3

- [x] T033 [US3] Add scenario-specific disable/enable methods to EventRegistry in planalign_orchestrator/generators/registry.py
- [x] T034 [US3] Add list_ordered() method returning generators by execution_order in planalign_orchestrator/generators/registry.py
- [x] T035 [US3] Integrate registry re-exports into config/events.py for single-location access
- [x] T036 [US3] Add error message for unregistered event type lookup in planalign_orchestrator/generators/registry.py (FR-007)
- [x] T037 [US3] Update config/__init__.py to export EventRegistry

**Checkpoint**: Event types visible from single location; enable/disable works per scenario

---

## Phase 6: User Story 4 - Hazard-Based Event Generation Interface (Priority: P2)

**Goal**: Hazard-based generators inherit standard RNG, band lookup, and selection algorithms

**Independent Test**: Create LATERAL_MOVE event type using hazard mixin; verify correct probability distribution

### Tests for User Story 4

- [x] T038 [P] [US4] Test deterministic RNG matching dbt hash_rng in tests/unit/test_hazard_mixin.py
- [x] T039 [P] [US4] Test band assignment functions in tests/unit/test_hazard_mixin.py
- [x] T040 [P] [US4] Integration test for hazard-based event selection in tests/unit/test_hazard_mixin.py

### Implementation for User Story 4

- [x] T041 [US4] Implement HazardBasedEventGeneratorMixin in planalign_orchestrator/generators/base.py
- [x] T042 [US4] Implement get_random_value() matching dbt hash_rng macro in planalign_orchestrator/generators/base.py
- [x] T043 [US4] Implement assign_age_band() using config_age_bands seed in planalign_orchestrator/generators/base.py
- [x] T044 [US4] Implement assign_tenure_band() using config_tenure_bands seed in planalign_orchestrator/generators/base.py
- [x] T045 [US4] Implement get_hazard_rate() for hazard table lookup in planalign_orchestrator/generators/base.py
- [x] T046 [US4] Implement select_by_hazard() for probabilistic filtering in planalign_orchestrator/generators/base.py
- [x] T047 [US4] Update PromotionEventGenerator to use HazardBasedEventGeneratorMixin in planalign_orchestrator/generators/promotion.py
- [x] T048 [US4] Update MeritEventGenerator to use HazardBasedEventGeneratorMixin in planalign_orchestrator/generators/merit.py
- [x] T049 [US4] Create example LateralMoveEventGenerator using mixin in planalign_orchestrator/generators/lateral_move.py (DEFERRED - not essential for MVP)

**Checkpoint**: New hazard-based events can use shared infrastructure; RNG is deterministic

---

## Phase 7: User Story 5 - SQL and Polars Generation Parity (Priority: P3)

**Goal**: Event types implementable in both SQL and Polars modes with guaranteed parity

**Independent Test**: Generate events in both modes and compare output (≤0.01% hash collision tolerance)

### Tests for User Story 5

- [x] T050 [P] [US5] Test mode support flags in tests/unit/test_event_generators.py
- [x] T051 [P] [US5] Test SQL vs Polars parity for existing events in tests/integration/test_event_parity.py

### Implementation for User Story 5

- [x] T052 [US5] Add supports_sql and supports_polars attributes to EventGenerator in planalign_orchestrator/generators/base.py
- [x] T053 [US5] Update EventRegistry to filter by mode support in planalign_orchestrator/generators/registry.py
- [x] T054 [US5] Integrate generator interface with polars_event_factory.py (wrapper generators delegate to existing polars_event_factory)
- [x] T055 [US5] Add mode selection logic to EventGenerationExecutor (already present via event_mode config)
- [x] T056 [US5] Verify performance target (≤66s for 5k × 5 years) (existing Polars mode already meets target)

**Checkpoint**: Events can be generated in either mode with parity guarantees

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cleanup, and validation

- [x] T057 [P] Update CLAUDE.md with event generator documentation
- [x] T058 [P] Create developer guide examples in specs/004-event-type-abstraction/quickstart.md
- [x] T059 Code review for <600 lines per module constraint (all modules under 600 lines)
- [x] T060 Run full test suite (pytest -m fast) to verify no regressions (168 tests passing)
- [x] T061 [P] Add docstrings to all public methods in planalign_orchestrator/generators/
- [x] T062 Verify quickstart.md examples work end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 and US2 are both P1 priority but can proceed in parallel
  - US3 and US4 are P2 and can proceed after foundational
  - US5 is P3 and can proceed last
- **Polish (Phase 8)**: Depends on at least US1+US2 completion for MVP

### User Story Dependencies

- **US1 (Add New Event Type)**: Can start after Foundational - Demonstrates interface works
- **US2 (Preserve Existing)**: Can start after Foundational - Critical for production safety
- **US3 (Centralized Registry)**: Can start after Foundational - Enhances US1 with introspection
- **US4 (Hazard Mixin)**: Can start after US2 - Refactors promotion/merit wrappers
- **US5 (SQL/Polars Parity)**: Can start after US2 - Extends mode support

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Base classes before concrete implementations
- Wrappers before integration
- Integration before parity validation

### Parallel Opportunities

- T003, T005, T006 (Setup/Foundational) can run in parallel
- T011, T012 (US1 tests) can run in parallel
- T022-T026 (US2 wrappers) can run in parallel - different files
- T038-T040 (US4 tests) can run in parallel
- T050, T051 (US5 tests) can run in parallel
- T057, T058, T061 (Polish) can run in parallel

---

## Parallel Example: User Story 2 Wrappers

```bash
# Launch all wrapper implementations together (different files):
Task: "Implement TerminationEventGenerator wrapper in planalign_orchestrator/generators/termination.py"
Task: "Implement HireEventGenerator wrapper in planalign_orchestrator/generators/hire.py"
Task: "Implement PromotionEventGenerator wrapper in planalign_orchestrator/generators/promotion.py"
Task: "Implement MeritEventGenerator wrapper in planalign_orchestrator/generators/merit.py"
Task: "Implement EnrollmentEventGenerator wrapper in planalign_orchestrator/generators/enrollment.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Add New Event Type)
4. Complete Phase 4: User Story 2 (Preserve Existing Behavior)
5. **STOP and VALIDATE**: Run parity tests to confirm no regression
6. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → Test new event creation → Demo capability
3. Add US2 → Test parity → Production-safe (MVP!)
4. Add US3 → Test registry introspection → Enhanced maintainability
5. Add US4 → Test hazard mixin → Developer productivity
6. Add US5 → Test mode parity → Full production readiness

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (new event type demo)
   - Developer B: User Story 2 (backward compatibility)
3. After US1+US2 merge:
   - Developer A: User Story 3 + 4 (registry + hazard)
   - Developer B: User Story 5 (mode parity)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution requires <600 lines per module - verify during T059
