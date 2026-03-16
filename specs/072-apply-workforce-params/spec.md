# Feature Specification: Apply Workforce Parameters Across Scenarios

**Feature Branch**: `072-apply-workforce-params`
**Created**: 2026-03-16
**Status**: Draft
**Input**: User description: "Add an 'Apply Workforce Parameters' action to selectively copy workforce assumptions (merit, COLA, promotion/termination hazards, hiring, demographics) from one scenario to multiple target scenarios, while leaving DC plan parameters untouched."
**GitHub Issue**: https://github.com/crzyc98/planwise_navigator/issues/192

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Workforce Parameters to Selected Scenarios (Priority: P1)

As an analyst, I want to copy workforce assumptions from one scenario to multiple other scenarios so that I can standardize economic and turnover assumptions while keeping DC plan designs unique per scenario.

**Why this priority**: This is the core value proposition. Without this, analysts must manually copy-and-revert parameters across scenarios, which is error-prone and time-consuming.

**Independent Test**: Can be fully tested by opening a source scenario's config page, clicking "Apply Workforce Params", selecting target scenarios, confirming, and verifying that only workforce parameters changed in targets while DC plan parameters remained intact.

**Acceptance Scenarios**:

1. **Given** a workspace with 4 scenarios (A, B, C, D) where each has different workforce and DC plan parameters, **When** the analyst opens Scenario A's config page, clicks "Apply Workforce Params", selects Scenarios B and C, and confirms, **Then** Scenarios B and C have Scenario A's workforce parameters while their DC plan parameters remain unchanged.
2. **Given** the analyst has applied workforce params, **When** they open Scenario B's config page, **Then** workforce fields (merit budget, COLA rate, termination rates, promotion hazard, hiring targets, new hire demographics) match Scenario A's values, and DC plan fields (match tiers, core contribution, deferral escalation, vesting, eligibility) are unchanged from Scenario B's original values.
3. **Given** a workspace with only 1 scenario, **When** the analyst opens that scenario's config page, **Then** the "Apply Workforce Params" button is disabled or hidden (no targets available).

---

### User Story 2 - Pre-Apply Confirmation with Change Summary (Priority: P2)

As an analyst, I want to see a summary of what will be overwritten before applying so that I can avoid unintended changes.

**Why this priority**: Overwriting parameters across multiple scenarios is a significant action. A clear confirmation step prevents costly mistakes.

**Independent Test**: Can be tested by initiating the apply action and verifying the confirmation dialog shows the correct count of target scenarios and a summary of which parameter categories will be overwritten.

**Acceptance Scenarios**:

1. **Given** the analyst has selected 2 target scenarios and clicked "Apply", **When** the confirmation dialog appears, **Then** it shows the names of the 2 target scenarios and lists the workforce parameter categories that will be overwritten (e.g., "Compensation settings, Termination rates, Promotion hazard, Hiring targets, New hire demographics").
2. **Given** the confirmation dialog is showing, **When** the analyst clicks "Cancel", **Then** no changes are made to any scenario.
3. **Given** the confirmation dialog is showing, **When** the analyst clicks "Confirm", **Then** the changes are applied and a success toast notification appears with a summary (e.g., "Workforce parameters applied to 2 scenarios").

---

### User Story 3 - Post-Apply Feedback (Priority: P3)

As an analyst, I want clear feedback after applying workforce parameters so that I know the operation succeeded and which scenarios were updated.

**Why this priority**: Provides confidence that the operation completed correctly, reducing the need to manually verify each target scenario.

**Independent Test**: Can be tested by completing an apply operation and verifying the toast notification content and that the modal closes.

**Acceptance Scenarios**:

1. **Given** the apply operation completes successfully, **When** the success notification appears, **Then** it shows the count of updated scenarios and their names.
2. **Given** an error occurs during the apply operation (e.g., a target scenario was deleted by another user), **When** the error notification appears, **Then** it identifies which scenarios succeeded and which failed.

---

### Edge Cases

- What happens when the source scenario has no workforce parameters configured (all defaults)? The defaults are still applied to targets, effectively resetting those fields to defaults.
- What happens if a target scenario is currently being edited by the same user in another tab? The server-side update takes precedence; the other tab will show stale data until refreshed.
- What happens if a target scenario has an active simulation running? The apply operation still succeeds (it modifies config, not runtime state). The next simulation run will use the updated config.
- What happens if the source and a target scenario already have identical workforce parameters? The operation completes normally (idempotent) with no error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an "Apply Workforce Params" action on each scenario's configuration page.
- **FR-002**: System MUST display a modal listing all other scenarios in the workspace with checkboxes for multi-select.
- **FR-003**: System MUST copy only workforce-related parameters to selected target scenarios:
  - Compensation settings (merit budget, COLA rate, promotion increase, promotion budget, promotion rate multiplier, promotion distribution range)
  - Workforce settings (total termination rate, new hire termination rate)
  - Simulation growth settings (target growth rate)
  - New hire demographics (strategy, age distribution, level distribution, compensation variance, market scenario, job level compensation, level market adjustments)
  - Seed configurations (promotion hazard rates, age bands, tenure bands)
- **FR-004**: System MUST NOT modify DC plan parameters in target scenarios:
  - Eligibility settings (eligibility months, hours requirements)
  - Auto-enrollment settings (auto-enroll toggle, default deferral, window days, grace period, scope, hire date cutoff)
  - Match configuration (match enabled, match template, match tiers, match mode, tenure/points match tiers, min tenure, year-end active requirement, hours requirement, terminated hire rules)
  - Core contribution settings (core enabled, core status, core rate, graded schedule, min tenure, year-end active, hours, terminated hire rules)
  - Deferral escalation settings (auto-escalation, rate, cap, effective day, delay years, hire date cutoff)
- **FR-005**: System MUST show a confirmation dialog before applying changes, listing target scenario names and workforce parameter categories that will be overwritten.
- **FR-006**: System MUST show a success or error notification after the operation completes.
- **FR-007**: The "Apply Workforce Params" button MUST be disabled or hidden when the workspace contains only one scenario.
- **FR-008**: System MUST apply changes atomically per target scenario — if one target fails, others that already succeeded remain updated, and the user is informed of the partial failure.

### Key Entities

- **Source Scenario**: The scenario from which workforce parameters are read. This is the currently viewed scenario.
- **Target Scenario(s)**: One or more scenarios selected by the analyst to receive the workforce parameters.
- **Workforce Parameters**: The subset of scenario configuration that pertains to workforce assumptions (compensation, termination, promotion, hiring, demographics, seed configs). Excludes all DC plan parameters.
- **DC Plan Parameters**: The subset of scenario configuration that pertains to retirement plan design (match, core, escalation, eligibility, enrollment). These are never modified by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Analysts can standardize workforce assumptions across 3+ scenarios in under 30 seconds (vs. minutes of manual copy-and-revert today).
- **SC-002**: After applying workforce parameters, 100% of DC plan parameters in target scenarios remain unchanged.
- **SC-003**: The confirmation step prevents accidental overwrites — analysts can review and cancel before any changes are made.
- **SC-004**: The operation completes within 2 seconds for up to 10 target scenarios.
- **SC-005**: Error cases (partial failures) are clearly communicated so the analyst knows exactly which scenarios were and were not updated.

## Assumptions

- The existing flexible configuration dictionary structure is sufficient to distinguish workforce vs. DC plan parameters by key naming conventions. No schema migration is needed.
- The "Apply Workforce Params" action writes to multiple target scenarios server-side (not just client-side form population), since it modifies persisted scenario configurations.
- Simulation-level settings like scenario name, start/end year, and random seed are NOT included in the workforce parameter copy, as these are scenario-identity fields.
- Census data path is NOT included in the copy, as each scenario may reference different census files.
- The feature operates within a single workspace — cross-workspace parameter application is out of scope.
- Advanced/engine settings (engine type, multithreading, memory limit, log level) are NOT included in the copy, as these are infrastructure settings unrelated to workforce assumptions.
