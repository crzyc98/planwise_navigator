# Feature Specification: Fix Auto Enrollment Runs Despite Being Disabled

**Feature Branch**: `074-fix-auto-enroll-disabled`
**Created**: 2026-03-18
**Status**: Draft
**Input**: GitHub Issue #246 — Auto enrollment runs despite being disabled in DC plan config

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Disable Auto Enrollment (Priority: P1)

A plan administrator configures a DC plan with auto enrollment disabled, runs a simulation, and expects zero auto-enrollment events in the results. Currently, employees are still auto-enrolled regardless of this setting.

**Why this priority**: This is the core bug. The auto-enrollment toggle is the primary control for this feature, and ignoring it produces incorrect simulation results that undermine trust in the platform.

**Independent Test**: Can be fully tested by disabling auto enrollment in DC plan config, running a simulation, and verifying that no auto-enrollment events appear in the results.

**Acceptance Scenarios**:

1. **Given** auto enrollment is disabled in the DC plan configuration, **When** a simulation is run, **Then** no auto-enrollment events are generated for any employees.
2. **Given** auto enrollment is disabled and a simulation completes, **When** viewing enrollment results, **Then** only voluntary enrollment events (if any) appear — no employees have an auto-enrollment category.
3. **Given** auto enrollment was previously disabled and is now re-enabled, **When** a new simulation is run, **Then** auto-enrollment events are generated normally according to scope settings.

---

### User Story 2 - Auto Enrollment Scope Respected When Enabled (Priority: P2)

When auto enrollment is enabled, the scope setting (e.g., "all eligible employees" vs. "new hires only") continues to work correctly and is not broken by the fix.

**Why this priority**: Ensuring the fix doesn't regress existing scope behavior is critical for users who rely on scoped auto-enrollment.

**Independent Test**: Can be tested by enabling auto enrollment with "new hires only" scope, running a simulation, and verifying only new hires receive auto-enrollment events.

**Acceptance Scenarios**:

1. **Given** auto enrollment is enabled with scope "all eligible employees", **When** a simulation is run, **Then** all eligible employees receive auto-enrollment events.
2. **Given** auto enrollment is enabled with scope "new hires only", **When** a simulation is run, **Then** only newly hired employees within the enrollment window receive auto-enrollment events.

---

### User Story 3 - Multi-Year Simulation Consistency (Priority: P3)

The auto-enrollment disabled setting persists correctly across all years of a multi-year simulation.

**Why this priority**: Multi-year simulations must respect the config consistently; a single-year fix that doesn't carry forward would still produce incorrect results.

**Independent Test**: Can be tested by disabling auto enrollment and running a 3-year simulation, then verifying zero auto-enrollment events in every simulated year.

**Acceptance Scenarios**:

1. **Given** auto enrollment is disabled, **When** a multi-year simulation (e.g., 2025–2027) is run, **Then** no auto-enrollment events are generated in any simulation year.
2. **Given** auto enrollment is disabled via PlanAlign Studio UI, **When** the saved configuration is used in a batch simulation, **Then** the disabled setting is honored across all scenarios and years.

---

### Edge Cases

- What happens when auto enrollment is disabled but voluntary enrollment models reference auto-enrollment defaults (e.g., default deferral rate)? Voluntary enrollments should still function independently using their own rate logic.
- What happens when the `auto_enrollment_enabled` configuration variable is missing entirely? The system should default to enabled for backward compatibility.
- What happens when auto enrollment is disabled but employees from a prior year were already auto-enrolled? Previously enrolled employees retain their enrollment; only new auto-enrollment event generation is suppressed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST NOT generate auto-enrollment events when the auto enrollment setting is disabled in the DC plan configuration.
- **FR-002**: System MUST continue to generate auto-enrollment events normally when auto enrollment is enabled, respecting the configured scope ("all eligible employees" or "new hires only").
- **FR-003**: The auto-enrollment disabled setting MUST be respected consistently across all years of a multi-year simulation.
- **FR-004**: Voluntary enrollment events MUST continue to function independently of the auto-enrollment enabled/disabled setting.
- **FR-005**: System MUST default to auto enrollment enabled when the configuration variable is not explicitly set (backward compatibility).
- **FR-006**: The auto-enrollment enabled/disabled flag MUST flow correctly from the UI configuration through to the simulation engine without being overridden or ignored at any layer.

### Key Entities

- **DC Plan Configuration**: Contains the `auto_enroll` flag (enabled/disabled), scope, default deferral rate, and enrollment window settings.
- **Auto-Enrollment Event**: A simulation event with an auto-enrollment category, generated for employees who meet eligibility criteria when auto enrollment is enabled.
- **Voluntary Enrollment Event**: A simulation event where an employee proactively enrolls, independent of auto-enrollment settings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When auto enrollment is disabled, 100% of simulation runs produce zero auto-enrollment events across all simulated years.
- **SC-002**: When auto enrollment is enabled, simulation results match expected enrollment counts based on the configured scope with no regressions from prior behavior.
- **SC-003**: Toggling auto enrollment on/off and re-running simulations produces correct results within one simulation cycle — no stale state carries over.
- **SC-004**: All existing enrollment-related tests continue to pass with no regressions.

## Assumptions

- The auto-enrollment configuration is correctly saved and loaded by the API and Python config layers. The bug is isolated to the simulation layer not checking the flag.
- The `auto_enrollment_enabled` variable is already exported by the orchestrator to dbt; the issue is that downstream models do not gate on it.
- Voluntary enrollment behavior is independent of auto-enrollment and should not be affected by this fix.
- Backward compatibility requires defaulting to enabled when the flag is absent.
