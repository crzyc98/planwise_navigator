# Feature Specification: Fix Deferral Rate Escalation Circular Dependency

**Feature Branch**: `036-fix-deferral-escalation-cycle`
**Created**: 2026-02-07
**Status**: Draft
**Input**: User description: "Re-enable int_deferral_rate_escalation_events by breaking the circular dependency with fct_workforce_snapshot"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deferral Escalation Events Generated for Eligible Employees (Priority: P1)

As a plan administrator, I need the simulation to automatically generate annual deferral rate escalation events for enrolled employees so that projected 401(k) contributions reflect real-world auto-escalation programs.

Currently the `int_deferral_rate_escalation_events` model is disabled (returns empty result sets) because it originally depended on `fct_workforce_snapshot` for prior-year escalation state, creating a circular dependency in the dbt DAG. This means every simulation run produces zero escalation events, making deferral rate projections inaccurate for any plan with an auto-escalation feature.

**Why this priority**: Without escalation events, the entire auto-escalation feature (Epic E035) is non-functional. This is the core deliverable.

**Independent Test**: Can be fully tested by running a single-year simulation and verifying that eligible enrolled employees receive deferral escalation events with correct rate increments.

**Acceptance Scenarios**:

1. **Given** an enrolled employee with a 6% deferral rate below the 10% escalation cap, **When** the simulation runs for the current year, **Then** a `deferral_escalation` event is generated with a new rate of 7% (6% + 1% default increment).
2. **Given** a simulation year where the disabled model previously returned empty results, **When** the fixed model runs, **Then** the dbt DAG compiles and executes without circular dependency errors.
3. **Given** an employee whose deferral rate is already at or above the escalation cap (e.g., 15%), **When** the simulation runs, **Then** no escalation event is generated for that employee (their rate is not reduced).

---

### User Story 2 - Multi-Year Escalation State Carries Forward Correctly (Priority: P2)

As a plan administrator, I need escalation state (current rate, escalation count, last escalation date) to carry forward across simulation years so that multi-year projections accumulate rate increases correctly over time.

The `.disabled` version of the model previously read prior-year escalation state from `fct_workforce_snapshot`, which caused the circular dependency. The replacement approach must provide equivalent prior-year state without that dependency.

**Why this priority**: Single-year escalation is useful, but multi-year accumulation is where the feature delivers real projection value. Depends on P1 being functional.

**Independent Test**: Can be tested by running a 3-year simulation and verifying that an employee's deferral rate increments each year (e.g., 6% -> 7% -> 8%) and does not reset.

**Acceptance Scenarios**:

1. **Given** an employee who received an escalation in Year 1 (6% -> 7%), **When** Year 2 simulation runs, **Then** the employee's starting rate for Year 2 is 7% and they receive an escalation to 8%.
2. **Given** an employee who reaches the 10% cap in Year 3, **When** Year 4 simulation runs, **Then** no further escalation event is generated.
3. **Given** a new hire enrolled mid-simulation (e.g., Year 2), **When** Year 3 simulation runs, **Then** the employee is eligible for their first escalation based on the configured delay period.

---

### User Story 3 - Escalation Events Validated by Automated Tests (Priority: P3)

As a developer, I need automated tests that verify escalation event correctness so that future changes do not silently break the feature again.

**Why this priority**: Tests protect the fix from regression and document expected behavior. Depends on P1 and P2 being functional.

**Independent Test**: Can be tested by running the test suite and confirming all escalation-related tests pass.

**Acceptance Scenarios**:

1. **Given** the full test suite, **When** tests are executed, **Then** at least one test verifies that eligible employees receive escalation events with correct rate changes.
2. **Given** a test for the model DAG, **When** the dbt project compiles, **Then** no circular dependency warnings or errors appear for escalation-related models.
3. **Given** a determinism test, **When** the same simulation is run twice with the same random seed, **Then** the escalation events are identical.

---

### Edge Cases

- What happens when an employee is terminated mid-year but was eligible for escalation? (Escalation should only apply to active employees.)
- What happens when the escalation effective date falls before an employee's enrollment date? (Employee should not be escalated.)
- What happens when `deferral_escalation_enabled` is set to `false` in configuration? (Zero escalation events should be produced, preserving the toggle behavior.)
- What happens when the `int_deferral_rate_state_accumulator_v2` table does not yet exist (first ever simulation run)? (Year 1 logic should handle this gracefully.)
- What happens when an employee opts out of their plan between escalation years? (No escalation should be generated for opted-out employees.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The deferral rate escalation model MUST compile and execute within the dbt DAG without introducing any circular dependencies.
- **FR-002**: The model MUST generate `deferral_escalation` events for employees who are enrolled, active, below the rate cap, and meet all configured eligibility criteria (tenure threshold, age threshold, enrollment maturity, timing).
- **FR-003**: For multi-year simulations, the model MUST read prior-year escalation state from a dependency-safe source (such as the `int_deferral_rate_state_accumulator_v2` via direct table reference or the existing temporal accumulation pattern) rather than from `fct_workforce_snapshot`.
- **FR-004**: The model MUST respect the `deferral_escalation_enabled` configuration toggle, producing zero events when escalation is disabled.
- **FR-005**: The model MUST NOT reduce an employee's deferral rate (e.g., an employee with a census rate of 15% must not be escalated down to the 10% cap).
- **FR-006**: The model MUST produce deterministic results for a given random seed and configuration.
- **FR-007**: Escalation events MUST include an audit trail (previous rate, new rate, escalation rate, eligibility details) for regulatory transparency.
- **FR-008**: The state accumulator models that consume escalation events MUST continue to function correctly, receiving non-empty event data instead of the current empty result sets.

### Key Entities

- **Deferral Escalation Event**: Represents an annual increase to an employee's 401(k) deferral rate. Key attributes: employee ID, previous rate, new rate, escalation increment, effective date, simulation year, eligibility details.
- **Deferral Rate State Accumulator**: Tracks cumulative escalation state per employee per year. Key attributes: employee ID, current deferral rate, escalations received, last escalation date, enrollment date, enrollment status.
- **Escalation Configuration**: Controls escalation behavior. Key attributes: enabled toggle, increment rate, rate cap, effective date, hire date cutoff, enrollment requirement, first-escalation delay.

## Assumptions

- The existing `int_deferral_rate_escalation_events.sql` (non-disabled version) already contains a working implementation that uses `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` as a direct table reference (not `{{ ref() }}`) for Year 2+ prior-year state. This approach avoids the dbt dependency graph cycle while still accessing the needed data.
- The `.disabled` version is the original implementation with the circular dependency; the non-disabled `.sql` file is a corrected version that needs to be validated and enabled in the pipeline.
- The `int_deferral_rate_state_accumulator_v2` model (which uses `{{ this }}` for temporal self-reference) is the correct accumulator to pair with escalation events.
- The orchestrator workflow stages already have a `STATE_ACCUMULATION` stage that runs after `EVENT_GENERATION`, which is the correct ordering for this model's dependencies.
- Configuration variables (`deferral_escalation_enabled`, `deferral_escalation_increment`, `deferral_escalation_cap`, etc.) are already defined in the dbt project variables and/or `simulation_config.yaml`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The dbt project compiles successfully (`dbt compile`) with the escalation model enabled, producing zero circular dependency errors.
- **SC-002**: A single-year simulation produces escalation events for at least 1 eligible enrolled employee (non-zero event count when escalation is enabled).
- **SC-003**: A 3-year simulation shows correct rate accumulation: employees' deferral rates increase by the configured increment each year until they reach the cap.
- **SC-004**: Employees with existing rates at or above the cap receive zero escalation events (no rate reduction).
- **SC-005**: At least 3 automated tests cover escalation scenarios: basic eligibility, multi-year accumulation, and cap enforcement.
- **SC-006**: Simulation results are deterministic - two runs with the same seed and configuration produce identical escalation events.
