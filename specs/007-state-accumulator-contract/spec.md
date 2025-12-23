# Feature Specification: Temporal State Accumulator Contract

**Feature Branch**: `007-state-accumulator-contract`
**Created**: 2025-12-14
**Status**: Draft
**Input**: User description: "Formalize the temporal state accumulator contract where Year N depends on Year N-1 data. Currently this dependency is implicit in SQL and not enforced at runtime. Preserved behavior: Year 2025 → 2026 → 2027 execution order maintained, deferral_rate_state_accumulator reads previous year correctly, enrollment_state_accumulator consolidates latest event per employee. Improved constraints: explicit StateAccumulatorContract interface that accumulator models must implement, pipeline fails fast if year dependency is violated (e.g., running 2027 before 2026), test suite validates temporal ordering invariants. This enables parallel year execution, checkpoint recovery, and streaming updates."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Runtime Year Dependency Validation (Priority: P1)

When running the simulation pipeline, analysts need immediate feedback if year dependencies are violated. Currently, if someone accidentally runs year 2027 before 2026, the SQL silently reads missing/stale data from `{{ this }}` references, producing incorrect results without any error. The pipeline should fail fast with a clear error message explaining which year(s) must be executed first.

**Why this priority**: This prevents silent data corruption - the most dangerous failure mode. Without this validation, users can unknowingly produce incorrect simulation results that propagate to downstream decisions.

**Independent Test**: Can be tested by attempting to execute year 2027 directly (without 2026) and verifying the pipeline fails with a descriptive error before any models run.

**Acceptance Scenarios**:

1. **Given** year 2025 has been executed successfully, **When** the pipeline attempts to execute year 2027 directly (skipping 2026), **Then** the pipeline fails with an error message stating "Year 2027 depends on year 2026 data which has not been executed. Please run years in sequence: 2025 → 2026 → 2027."

2. **Given** no years have been executed, **When** the pipeline executes year 2025 (the start year), **Then** execution succeeds because year 2025 has no prior year dependency.

3. **Given** years 2025 and 2026 have been executed, **When** the pipeline attempts to execute year 2027, **Then** execution proceeds normally because all dependencies are satisfied.

---

### User Story 2 - State Accumulator Model Registration (Priority: P2)

Developers adding new state accumulator models need a clear contract to implement. Currently, the temporal dependency pattern (reading `{{ this }}` for `simulation_year - 1`) is implicit and undocumented, leading to inconsistent implementations and bugs. A formal interface ensures all accumulator models follow the same pattern and enables automated validation.

**Why this priority**: This is foundational infrastructure that enables automated validation, consistent model development, and future parallel execution capabilities.

**Independent Test**: Can be tested by creating a new test accumulator model that implements the contract interface, registering it, and verifying the registration validates all required contract elements.

**Acceptance Scenarios**:

1. **Given** a new state accumulator model is created, **When** the model is registered with the StateAccumulatorRegistry, **Then** the registry validates that the model has the required temporal dependency pattern (reads from prior year state).

2. **Given** an existing accumulator model (e.g., `int_enrollment_state_accumulator`), **When** the model's metadata is queried from the registry, **Then** the registry returns the model's declared dependencies including prior year self-reference.

3. **Given** a model is registered without proper temporal dependency declaration, **When** registration is attempted, **Then** registration fails with a clear validation error explaining the missing contract elements.

---

### User Story 3 - Checkpoint-Based Recovery with Dependency Awareness (Priority: P3)

When resuming a simulation from a checkpoint, the system must validate that the checkpoint's year dependencies are satisfied before continuing. This enables reliable recovery after failures and supports the planned parallel year execution capability.

**Why this priority**: Recovery and resilience are important for long-running simulations, but require the dependency validation infrastructure from P1/P2 to be valuable.

**Independent Test**: Can be tested by creating a checkpoint at year 2026, corrupting the 2025 state, and verifying that resume correctly identifies the broken dependency chain.

**Acceptance Scenarios**:

1. **Given** a checkpoint exists for year 2026 with valid 2025 state, **When** the simulation resumes from the checkpoint, **Then** the pipeline validates dependencies are intact before continuing to year 2027.

2. **Given** a checkpoint exists for year 2026 but year 2025 data has been deleted, **When** the simulation attempts to resume, **Then** the pipeline fails with an error indicating the dependency chain is broken and which years need re-execution.

---

### User Story 4 - Test Suite for Temporal Ordering Invariants (Priority: P3)

The test suite should include validation tests that verify temporal ordering invariants are maintained across all registered state accumulator models. This catches regressions when models are modified and validates new models follow the contract.

**Why this priority**: Testing infrastructure that depends on the contract being defined (P1/P2), but essential for maintaining correctness as the system evolves.

**Independent Test**: Can be tested by running the temporal invariant test suite against the current codebase and verifying all registered accumulators pass.

**Acceptance Scenarios**:

1. **Given** the test suite runs against registered accumulators, **When** all accumulators implement the contract correctly, **Then** all temporal ordering invariant tests pass.

2. **Given** a test accumulator model intentionally violates the contract (e.g., reads year N+1 instead of N-1), **When** the invariant test suite runs, **Then** the specific violation is detected and reported with the model name and nature of violation.

---

### Edge Cases

- What happens when the start year (e.g., 2025) is executed? The first year has no prior dependency and should use baseline workforce data instead.
- How does the system handle re-execution of a year that already has data? The incremental delete+insert strategy should be preserved; dependency validation only checks that prior year data exists.
- What happens if someone manually deletes intermediate year data (e.g., deletes 2026 but 2027 exists)? The dependency check should fail when 2027 is attempted, even though 2027 data technically exists.
- How are non-accumulator models handled? Models without temporal self-references should not be registered in the StateAccumulatorRegistry and should not affect dependency validation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Pipeline MUST validate year dependencies before executing any STATE_ACCUMULATION stage models for a given year.
- **FR-002**: Pipeline MUST fail with a descriptive error when year dependency validation fails, specifying which prior years are required.
- **FR-003**: System MUST provide a StateAccumulatorRegistry that tracks all models implementing the temporal state accumulator pattern.
- **FR-004**: Registry MUST validate that registered models declare their temporal dependency pattern (prior year self-reference).
- **FR-005**: Pipeline MUST query registered accumulators to determine which years have valid state data before execution.
- **FR-006**: System MUST treat the start year (e.g., 2025) as having no prior year dependency, using baseline workforce as the initial state.
- **FR-007**: Checkpoint recovery MUST validate dependency chain integrity before resuming execution.
- **FR-008**: Test suite MUST include validation tests that verify all registered accumulators maintain temporal ordering invariants.
- **FR-009**: System MUST preserve existing behavior where `int_enrollment_state_accumulator` consolidates the latest enrollment event per employee.
- **FR-010**: System MUST preserve existing behavior where `int_deferral_rate_state_accumulator` reads previous year deferral rates correctly.

### Key Entities

- **StateAccumulatorContract**: Defines the interface that all temporal state accumulator models must implement. Includes declarations for: model name, target table, temporal dependency pattern, start year behavior.
- **StateAccumulatorRegistry**: Centralized registry that tracks all accumulator models, their dependencies, and provides query methods for dependency validation.
- **YearDependencyGraph**: Represents the dependency relationships between simulation years, enabling validation queries like "is year N ready to execute?"
- **YearExecutionState**: Tracks which years have been successfully executed and have valid state data, enabling dependency validation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Pipeline prevents 100% of out-of-order year execution attempts by failing fast with clear error messages before any model execution begins.
- **SC-002**: All existing state accumulator models (enrollment, deferral rate) are registered in the StateAccumulatorRegistry with complete contract metadata.
- **SC-003**: Adding a new state accumulator model requires implementing the contract interface and registering with the registry - no other changes needed to enable dependency validation.
- **SC-004**: Checkpoint recovery validates dependency chain integrity with zero silent failures when prior year data is missing or corrupted.
- **SC-005**: Test suite achieves 100% coverage of temporal ordering invariants across all registered accumulator models.
- **SC-006**: Existing simulation behavior is fully preserved - year 2025 → 2026 → 2027 execution order produces identical results to current implementation.

## Assumptions

1. **Sequential execution remains the default**: While this feature enables future parallel year execution, the initial implementation maintains sequential year-by-year execution.
2. **dbt incremental models continue to use delete+insert strategy**: The dependency validation checks for data existence, not data freshness - re-runs of the same year are allowed.
3. **Start year is deterministic from configuration**: The `start_year` comes from `simulation_config.yaml` and determines which year has no prior dependency.
4. **Baseline workforce serves as initial state**: For the start year, `int_baseline_workforce` provides the initial employee state rather than a prior year accumulator.
5. **Two primary accumulators exist today**: `int_enrollment_state_accumulator` and `int_deferral_rate_state_accumulator` are the models that implement the temporal pattern and will be registered initially.
