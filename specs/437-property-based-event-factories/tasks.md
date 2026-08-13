# Tasks: Property-Based Event Factory Contracts

**Input**: Design documents from `/specs/437-property-based-event-factories/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/event-serialization.md`, `quickstart.md`

**Tests**: Required. Issue 437 explicitly requests Hypothesis properties, and the project constitution requires red-green-refactor for the production validation correction.

**Organization**: Tasks are grouped by user story. Shared dependency metadata and strategy contracts are established first; each story then has a focused independent pytest selector.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other tasks marked `[P]` in the same group because they modify different files and do not depend on incomplete work.
- **[Story]**: Maps implementation work to User Story 1, 2, or 3 from `spec.md`.
- Every task names the exact file or files it changes or validates.

## Phase 1: Setup (Dependency Classification)

**Purpose**: Make Hypothesis available to development and CI without installing it in production environments.

- [X] T001 [P] Move `hypothesis>=6.0.0` from `[project].dependencies` into the testing subsection of `[project.optional-dependencies].dev` in `pyproject.toml`
- [X] T002 [P] Remove `hypothesis>=6.0.0` from `requirements.txt` and add it under Testing in `requirements-dev.txt`
- [X] T003 Run `uv lock`, review the expected editable-project metadata refresh, and verify Hypothesis moves from unconditional dependencies into the `dev` extra in `uv.lock` after T001 and T002

**Checkpoint**: Runtime and development dependency declarations agree, and the generated lock metadata is current.

---

## Phase 2: Foundational (Shared Property-Test Contracts)

**Purpose**: Establish reusable, typed test metadata used by all three stories.

**⚠️ CRITICAL**: Complete this phase before implementing any user-story properties.

- [X] T004 Create the typed `EventFactoryCase`/generated-input support plus bounded finite Decimal, year/date, identifier, literal, and common context strategies in `tests/fixtures/event_factory_strategies.py`; avoid `.filter()`, rejection-heavy `assume()`, NaN/infinity, surrogates/control-only identifiers, and extreme Decimal magnitudes
- [X] T005 Populate exact envelope metadata and nine factory descriptors for hire, termination, promotion, merit, enrollment, contribution, vesting, forfeiture, and HCE status in `tests/fixtures/event_factory_strategies.py`, including callable, payload subtype/discriminator, source system, effective-date argument, payload key set, and JSON type families from `contracts/event-serialization.md`

**Checkpoint**: The shared fixture describes every in-scope public factory and exact serialization shape without executing production changes.

---

## Phase 3: User Story 1 - Trust Valid Event Construction (Priority: P1) 🎯 MVP

**Goal**: Prove all nine public factories produce correctly mapped events that survive complete native dump/revalidation, including Unicode identifiers, and close the discovered workforce compensation round-trip defect.

**Independent Test**: `pytest tests/unit/events/test_event_factory_properties.py -q -k "native_round_trip or factory_mapping or unicode_identifier or subquantum_compensation"` passes; before T009/T010, the sub-quantum regression must fail by showing the factory constructs compensation as `0.000000`.

### Tests for User Story 1

- [X] T006 [P] [US1] Add valid keyword-argument composite strategies for each of the nine factory descriptors plus readable Unicode, combining-character, emoji, and surrounding-whitespace identifier cases in `tests/fixtures/event_factory_strategies.py`
- [X] T007 [P] [US1] Add focused parameterized hire/promotion/merit tests proving positive compensation that half-even quantizes to `0.000000` must raise `pydantic.ValidationError` in `tests/unit/events/test_event_factory_properties.py`, then run those tests and confirm they fail before production edits
- [X] T008 [US1] Add locally bounded Hypothesis tests for complete `model_dump()` → `SimulationEvent.model_validate()` equality, payload subtype/discriminator, fixed source system, effective-date mapping, top-level identifier trimming, and Unicode preservation across all nine descriptors in `tests/unit/events/test_event_factory_properties.py` using `max_examples=100`, `deadline=None`, deterministic generation, and normal shrinking phases

### Implementation for User Story 1

- [X] T009 [US1] Add a shared six-place positive-amount quantization helper that rejects a normalized result `<= 0` with `ValueError` in `planalign_core/events/validators.py`
- [X] T010 [US1] Apply the shared positive-amount helper to `HirePayload.annual_compensation`, `PromotionPayload.new_annual_compensation`, and `MeritPayload.new_compensation` validators in `planalign_core/events/workforce.py`
- [X] T011 [US1] Run the User Story 1 selector against `tests/unit/events/test_event_factory_properties.py` and confirm the formerly failing sub-quantum examples now raise `ValidationError` while every generated-valid event round-trips unchanged

**Checkpoint**: User Story 1 independently establishes the reusable valid-event harness and closes the reproduced factory/self-schema inconsistency.

---

## Phase 4: User Story 2 - Protect Numeric and Temporal Boundaries (Priority: P1)

**Goal**: Prove exact Decimal types/scales/bounds and contextual simulation-year/lifecycle date properties without inventing unsupported business rules.

**Independent Test**: `pytest tests/unit/events/test_event_factory_properties.py -q -k "decimal_discipline or rate_boundary or effective_date or lifecycle_ordering"` passes with first/last-day, leap-day, same-day lifecycle, six-place amount, four-place rate, and nested vesting-balance coverage.

### Tests for User Story 2

- [X] T012 [P] [US2] Add constructive strategies for exact and accepted overprecision workforce amounts, constrained-scale DC/admin amounts and rates, zero/one rate boundaries, nested vesting balances, January 1/December 31/leap-day dates, and `hire_date <= termination_date` lifecycle pairs in `tests/fixtures/event_factory_strategies.py`; do not add a vesting-balance sign rule or unsupported final-pay/pay-period/service-date ordering
- [X] T013 [P] [US2] Add Hypothesis properties asserting exact `Decimal` output types, six-place amount/four-place rate exponents, no float conversion, inclusive rate bounds, schema-specific overprecision behavior, factory effective-date mapping within the generated year, and contextual hire/termination ordering in `tests/unit/events/test_event_factory_properties.py`
- [X] T014 [US2] Run the User Story 2 selector with `--hypothesis-show-statistics` against `tests/unit/events/test_event_factory_properties.py` and confirm every property executes no more than 100 examples with successful shrinking/settings health

**Checkpoint**: User Story 2 independently guards exact arithmetic and supported temporal invariants while preserving existing schema semantics.

---

## Phase 5: User Story 3 - Reject Malformed Inputs and Freeze Serialization (Priority: P1)

**Goal**: Reject malformed values through public factories and pin exact JSON-compatible envelope/payload contracts for all nine event types.

**Independent Test**: `pytest tests/unit/events/test_event_factory_properties.py -q -k "invalid_input_rejected or json_contract or json_round_trip"` passes, with every invalid category raising `ValidationError` and every JSON-mode dump matching `contracts/event-serialization.md` exactly.

### Tests for User Story 3

- [X] T015 [P] [US3] Add otherwise-valid argument strategies mutated with empty/whitespace-only employee IDs, negative and zero-when-positive amounts, sub-quantum workforce compensation, and below-zero/above-one rates in `tests/fixtures/event_factory_strategies.py`, keeping invalid values within supported finite magnitude/scale so the intended bound is exercised
- [X] T016 [P] [US3] Add public-factory rejection properties plus exact `model_dump(mode="json")` envelope/payload key and primitive-type assertions, `json.dumps`/`json.loads` compatibility, and complete JSON revalidation equality for all nine descriptors in `tests/unit/events/test_event_factory_properties.py`; use exact `type(value) is bool/int` checks and retain default/`None` keys
- [X] T017 [US3] Run the User Story 3 selector against `tests/unit/events/test_event_factory_properties.py` and compare all asserted key/type metadata with `specs/437-property-based-event-factories/contracts/event-serialization.md`, treating any drift as a reviewed contract change rather than automatically updating expectations

**Checkpoint**: User Story 3 independently prevents silent invalid construction and freezes the guarded audit JSON shape.

---

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: Verify compatibility, dependency placement, formatting, and bounded incremental test cost across the complete feature.

- [X] T018 Run `pytest -m "fast and events" tests/unit/events -q --hypothesis-show-statistics` and record the final event-suite count and elapsed time in `specs/437-property-based-event-factories/quickstart.md`, preserving all existing example-based tests under `tests/unit/events/`
- [X] T019 [P] Run `ruff check` and `black --check` on `tests/fixtures/event_factory_strategies.py`, `tests/unit/events/test_event_factory_properties.py`, `planalign_core/events/validators.py`, and `planalign_core/events/workforce.py`, then correct only feature-scoped findings in those files
- [X] T020 [P] Verify Hypothesis is absent from runtime declarations and present in development declarations with `rg` across `pyproject.toml`, `requirements.txt`, and `requirements-dev.txt`, then run `uv lock --check` against `uv.lock`
- [X] T021 Run `pytest -m fast -q` against `tests/`, compare elapsed time with the repository's inherited multi-minute baseline, and document issue 437's bounded incremental cost or any mitigation in `specs/437-property-based-event-factories/quickstart.md`
- [X] T022 Reconcile the implemented descriptors and assertions with `specs/437-property-based-event-factories/spec.md`, `data-model.md`, `contracts/event-serialization.md`, and `quickstart.md`; run `git diff --check` and remove any stale claims or unintended out-of-scope changes

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: T001 and T002 can run in parallel; T003 depends on both.
- **Phase 2 (Foundational)**: Depends on T003; T004 precedes T005 and blocks all story work.
- **Phase 3 (US1)**: Depends on T005. T006 and T007 can run in parallel; T008 follows the test support, then T009/T010 implement the red-green fix, and T011 validates the story.
- **Phase 4 (US2)**: Depends on US1's valid-event harness and closure fix. T012 and T013 can be authored in parallel, then T014 validates them.
- **Phase 5 (US3)**: Depends on US1's valid-event harness. T015 and T016 can be authored in parallel, then T017 validates them. US2 and US3 may proceed concurrently after US1 if their shared-file edits are coordinated or isolated in separate worktrees.
- **Phase 6 (Polish)**: Depends on all desired story phases. T019 and T020 can run in parallel; final timing and documentation checks follow.

### User Story Dependency Graph

```text
Setup -> Foundation -> US1 (MVP)
                         ├──> US2 ──┐
                         └──> US3 ──┴──> Polish
```

- **US1** owns the common valid-event harness and the only planned production correction.
- **US2** reuses US1's descriptors but is independently verified by numeric/temporal selectors.
- **US3** reuses US1's descriptors but is independently verified by rejection/serialization selectors.
- **US2 and US3** have no semantic dependency on each other.

### Within Each User Story

- Write tests and reproduce failures before production implementation.
- Construct strategies before running properties that consume them.
- Preserve Hypothesis shrinking and bounded settings.
- Run the story's independent selector before advancing to another phase.

## Parallel Execution Examples

### User Story 1

```text
Parallel after T005:
- T006: valid generated-input and Unicode strategy support in tests/fixtures/event_factory_strategies.py
- T007: focused failing sub-quantum regressions in tests/unit/events/test_event_factory_properties.py

Then sequential: T008 -> T009 -> T010 -> T011
```

### User Story 2

```text
Parallel after US1:
- T012: Decimal/date/lifecycle strategies in tests/fixtures/event_factory_strategies.py
- T013: Decimal/date/lifecycle properties in tests/unit/events/test_event_factory_properties.py

Then: T014
```

### User Story 3

```text
Parallel after US1:
- T015: malformed-input strategies in tests/fixtures/event_factory_strategies.py
- T016: rejection and JSON-contract properties in tests/unit/events/test_event_factory_properties.py

Then: T017
```

## Implementation Strategy

### MVP First: User Story 1

1. Complete dependency setup and shared factory metadata.
2. Write and reproduce the sub-quantum failure.
3. Add valid round-trip, mapping, and Unicode properties.
4. Implement the shared positive-amount validator correction.
5. Stop and run the US1 selector before expanding coverage.

The MVP produces immediate value: every requested factory has generated-valid round-trip coverage, and the already-reproduced invalid-event closure defect is fixed.

### Incremental Delivery

1. **US1**: Valid construction and self-schema closure.
2. **US2**: Exact Decimal and contextual date invariants.
3. **US3**: Invalid-input rejection and exact JSON audit contract.
4. **Polish**: Full event/fast selections, dependency verification, formatting, timing, and artifact reconciliation.

### Parallel Team Strategy

After Setup and Foundation, complete US1 first because it owns shared valid cases and the production fix. US2 and US3 can then run concurrently in isolated worktrees; within each story, the fixture task and test-module task can be authored in parallel and merged before the story validation task.

## Notes

- `[P]` tasks operate on different files or scopes and have no incomplete prerequisite within their parallel group.
- The current model does not enforce final-pay, contribution/pay-period, or vesting service-date ordering; these are out of scope.
- Vesting balance values are currently sign-unconstrained; issue 437 pins their Decimal type and six-place scale only.
- The event factories have no direct proven DuckDB adapter in this scope; the JSON tests guard the documented audit payload boundary.
- No dbt command, simulation, or isolated DuckDB run is required unless implementation expands beyond Pydantic event behavior.
