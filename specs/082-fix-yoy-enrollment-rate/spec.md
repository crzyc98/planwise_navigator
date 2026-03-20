# Feature Specification: Fix Year-over-Year Voluntary Enrollment Rate Override

**Feature Branch**: `082-fix-yoy-enrollment-rate`
**Created**: 2026-03-20
**Status**: Draft
**Input**: GitHub Issue #278 — Voluntary enrollment rate=0% does not suppress year-over-year voluntary enrollment events

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Suppress All Voluntary Enrollment at 0% (Priority: P1)

As a plan administrator, I set the Voluntary Enrollment Rate to 0% in the DC Plan configuration so that no employees voluntarily enroll in the retirement plan during simulation. I expect zero voluntary enrollment events across all pathways — including year-over-year conversions — for every simulation year.

**Why this priority**: This is the core bug. Users expect a 0% voluntary enrollment rate to mean zero voluntary enrollments. The year-over-year pathway currently ignores this setting, producing misleading simulation results.

**Independent Test**: Run a multi-year simulation with voluntary enrollment rate set to 0%. Verify that no voluntary enrollment events are generated in any year, including from the year-over-year conversion pathway.

**Acceptance Scenarios**:

1. **Given** voluntary enrollment rate is set to 0%, **When** a multi-year simulation runs (e.g., 2025–2027), **Then** zero voluntary enrollment events are generated across all three pathways (existing employee, new hire proactive, and year-over-year conversion).
2. **Given** voluntary enrollment rate is set to 0% and employees were not enrolled in prior years, **When** the year-over-year conversion logic executes, **Then** no previously non-enrolled employees convert to enrolled status.
3. **Given** voluntary enrollment rate was previously set to 50% and is changed to 0%, **When** the simulation reruns, **Then** no new voluntary enrollment events appear in any year.

---

### User Story 2 - Proportional Scaling of Year-over-Year Conversions (Priority: P1)

As a plan administrator, I set the Voluntary Enrollment Rate to an intermediate value (e.g., 50%) and expect all voluntary enrollment pathways — including year-over-year conversions — to scale proportionally. The year-over-year demographic base rates should be multiplied by the voluntary enrollment rate, just like the other two pathways.

**Why this priority**: Equal to P1 because the fix must work consistently across the full 0–100% range, not just at 0%.

**Independent Test**: Run simulations at 25%, 50%, and 100% voluntary enrollment rates. Verify that year-over-year conversion counts scale proportionally to the rate, matching the behavior of the other two pathways.

**Acceptance Scenarios**:

1. **Given** voluntary enrollment rate is set to 50%, **When** simulation runs, **Then** year-over-year conversion probabilities are 50% of the demographic base rates.
2. **Given** voluntary enrollment rate is set to 100%, **When** simulation runs, **Then** year-over-year conversions use the full demographic base rates (unchanged behavior from today at 100%).
3. **Given** voluntary enrollment rate is set to 25%, **When** simulation runs, **Then** year-over-year conversion event counts are approximately 25% of the count at 100% rate (within statistical tolerance).

---

### User Story 3 - Single Sensitivity Dial for All Voluntary Enrollment (Priority: P2)

As a plan administrator, I want the Voluntary Enrollment Rate to function as a single unified sensitivity dial that controls overall voluntary participation across all pathways. I should not need to configure separate rates for different enrollment mechanisms.

**Why this priority**: This is a usability concern. The current architecture has a hidden, non-configurable pathway that operates independently, which violates the principle of least surprise. Unifying under a single dial is simpler and more predictable.

**Independent Test**: Verify that changing the single voluntary enrollment rate slider in the DC Plan config UI affects all three enrollment pathways uniformly without requiring any additional configuration.

**Acceptance Scenarios**:

1. **Given** a user adjusts the voluntary enrollment rate in the DC Plan config, **When** simulation runs, **Then** all three voluntary enrollment pathways (existing employee, new hire proactive, year-over-year) reflect the configured rate.
2. **Given** no changes are made to year-over-year conversion variables directly, **When** voluntary enrollment rate is modified, **Then** year-over-year behavior changes accordingly.

---

### Edge Cases

- What happens when voluntary enrollment rate is set to exactly 0.0? All three pathways must produce exactly zero events (not near-zero due to floating-point rounding).
- What happens when voluntary enrollment rate is set to 100%? Year-over-year conversions should use the full demographic base rates, matching current behavior.
- What happens when voluntary enrollment rate is set to a very small value (e.g., 1%)? The year-over-year pathway should still respect the multiplier and produce a proportionally small number of events.
- What happens in Year 1 of simulation vs. Year 2+? Year-over-year conversions only apply in Year 2+; the fix should not affect Year 1 behavior.
- What happens when `year_over_year_conversion_enabled` is set to false independently? The year-over-year pathway should remain disabled regardless of voluntary enrollment rate.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The voluntary enrollment rate MUST act as a multiplier on the year-over-year conversion pathway, consistent with how it already applies to the existing employee and new hire proactive pathways.
- **FR-002**: When voluntary enrollment rate is 0%, the system MUST generate exactly zero voluntary enrollment events across all three pathways.
- **FR-003**: When voluntary enrollment rate is between 0% and 100%, the year-over-year conversion demographic base rates MUST be scaled by the voluntary enrollment rate before determining enrollment decisions.
- **FR-004**: When voluntary enrollment rate is 100%, the year-over-year conversion behavior MUST remain identical to current production behavior (no regression).
- **FR-005**: The existing `year_over_year_conversion_enabled` flag MUST continue to function as an independent kill switch for the year-over-year pathway.
- **FR-006**: No new UI controls are required — the existing Voluntary Enrollment Rate control is sufficient as the unified sensitivity dial.

### Key Entities

- **Voluntary Enrollment Rate**: A scaling factor (0.0–1.0) that controls the probability of voluntary enrollment across all pathways. Applied as a multiplier to demographic-based enrollment probabilities.
- **Year-over-Year Conversion**: A pathway where previously non-enrolled employees may voluntarily convert to enrolled status in subsequent simulation years, using age-based demographic base rates (3–8%).
- **Enrollment Event**: An immutable event record representing an employee's enrollment in the DC plan, generated by one of three voluntary enrollment pathways.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A simulation with voluntary enrollment rate at 0% produces exactly zero voluntary enrollment events across all years and all pathways.
- **SC-002**: A simulation with voluntary enrollment rate at 50% produces approximately 50% of the voluntary enrollment events compared to a 100% rate simulation (within 10% statistical tolerance over a sufficiently large population).
- **SC-003**: A simulation with voluntary enrollment rate at 100% produces identical results to the current production behavior (regression-free).
- **SC-004**: All existing enrollment-related tests continue to pass without modification.

## Assumptions

- Option A from the issue (apply `voluntary_enrollment_rate` as a multiplier to the year-over-year CTE) is the chosen approach, rather than adding a separate UI control (Option B).
- The `year_over_year_conversion_enabled` flag and demographic base rate variables remain as internal implementation details, not exposed in the UI.
- The `voluntary_enrollment_rate` variable is already correctly passed to dbt as a simulation variable and is accessible within the enrollment models.
- No changes to the config model or frontend UI are needed since the existing voluntary enrollment rate field already exists and is exported to dbt vars.
