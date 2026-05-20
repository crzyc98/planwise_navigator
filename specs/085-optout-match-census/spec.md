# Feature Specification: Match Census for Opt-Out Rate Configuration

**Feature Branch**: `085-optout-match-census`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "Add 'Match Census' button for opt-out rates with configurable tenure lookback"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Derive Opt-Out Rate from Census with Tenure Lookback (Priority: P1)

An analyst is configuring a scenario's opt-out assumptions in PlanAlign Studio. Rather than manually estimating the opt-out rate, they want to anchor it to real data. They click the "Match Census" button inside the Opt-Out Assumptions panel, set a lookback of 3 years (to focus on recently hired employees who reflect current enrollment behavior), and review the suggested rate. Satisfied with the result, they apply it to the configuration.

**Why this priority**: This is the core value of the feature. The ability to auto-derive a data-backed opt-out rate — with tenure filtering to focus on recent cohorts — eliminates guesswork and makes the simulation more credible.

**Independent Test**: Can be fully tested by clicking "Match Census", setting a tenure lookback, reviewing the preview showing the calculated rate and supporting statistics, and applying it to verify the field is updated.

**Acceptance Scenarios**:

1. **Given** a scenario with a census file uploaded, **When** the analyst clicks "Match Census" in the Opt-Out Assumptions panel, **Then** a preview panel appears showing the suggested opt-out rate and the supporting census statistics (eligible count, non-participant count, resulting rate).
2. **Given** the analyst sets the tenure lookback to 3 years, **When** the preview is calculated, **Then** only employees with 3 or fewer years of tenure are included in the non-participant rate calculation.
3. **Given** the preview shows a suggested rate, **When** the analyst clicks "Apply", **Then** the opt-out rate field is updated to the suggested value and the preview panel closes.
4. **Given** the preview shows a suggested rate, **When** the analyst clicks "Cancel", **Then** the opt-out rate field is unchanged.

---

### User Story 2 - Adjust Tenure Lookback and Re-preview (Priority: P2)

An analyst wants to explore how the lookback window affects the suggested rate. They open the "Match Census" preview, see the rate for a 5-year lookback, then reduce it to 1 year to isolate the most recently hired employees. They observe the rate change in the preview before deciding which window to use.

**Why this priority**: Analysts need to understand how the lookback window changes the result. Without the ability to adjust and re-preview, the feature is a one-shot tool that limits analytical exploration.

**Independent Test**: Can be fully tested by opening the preview, changing the lookback value, and confirming the preview statistics (counts, rate) update to reflect only employees within the new tenure window.

**Acceptance Scenarios**:

1. **Given** the "Match Census" preview is open with a default lookback, **When** the analyst changes the lookback value, **Then** the preview statistics and suggested rate recalculate immediately to reflect the new tenure window.
2. **Given** the analyst sets the lookback to 1 year and the census has no employees with ≤ 1 year tenure, **When** the preview calculates, **Then** an informative message is shown explaining that no eligible employees match the filter, rather than showing a zero or invalid rate.

---

### User Story 3 - Use Match Census with No Census File (Priority: P3)

An analyst attempts to use the "Match Census" button in a scenario that does not have a census file associated with it.

**Why this priority**: This edge case must be handled gracefully to avoid confusing errors. The button should remain accessible but provide a clear explanation when no data source is available.

**Independent Test**: Can be tested by clicking "Match Census" in a scenario with no census file and verifying a clear, actionable message appears rather than an error or empty preview.

**Acceptance Scenarios**:

1. **Given** a scenario with no census file uploaded, **When** the analyst clicks "Match Census", **Then** the system displays a message explaining that a census file is required to use this feature, with a prompt or link to upload one.

---

### Edge Cases

- What happens when the census has no employees marked as eligible for the DC plan?
  - The system shows a preview message indicating no eligible employees were found and cannot suggest a rate.
- What happens when all eligible employees in the lookback window are already enrolled (0% non-participants)?
  - The system suggests an opt-out rate of 0% and clearly labels this as the result, so the analyst is not confused by a zero value.
- What happens when the lookback value is set to 0 or a negative number?
  - The system rejects the value and displays a validation message requiring a positive whole number.
- What happens when the analyst applies a suggested rate and then manually edits it before saving?
  - The manually edited value takes precedence; the census-derived suggestion is treated as a starting point, not a locked value.
- What happens when the census contains employees with missing or null tenure values?
  - Those employees are excluded from the lookback-filtered calculation, and the preview notes how many records were excluded.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a "Match Census" button within the Opt-Out Assumptions panel of the DC Plan configuration in PlanAlign Studio.
- **FR-002**: When "Match Census" is clicked with a census file available, the system MUST open a preview panel showing: the tenure lookback setting, the count of total eligible employees in the lookback window, the count of non-participants in that group, and the calculated non-participant rate.
- **FR-003**: System MUST provide a configurable tenure lookback input (whole number of years, minimum 1) in the preview panel, defaulting to 3 years.
- **FR-004**: System MUST calculate the non-participant rate as: employees not enrolled in the DC plan divided by total eligible employees, filtered to only those with tenure at or below the lookback threshold.
- **FR-005**: System MUST recalculate and refresh the preview statistics when the analyst changes the tenure lookback value.
- **FR-006**: System MUST provide an "Apply" action in the preview that updates the opt-out rate field with the suggested rate.
- **FR-007**: System MUST provide a "Cancel" action in the preview that dismisses the panel without changing the opt-out rate field.
- **FR-008**: When "Match Census" is clicked with no census file available, system MUST display a clear message explaining the requirement and how to fulfill it.
- **FR-009**: System MUST exclude census records with missing or null tenure values from the calculation and show a count of excluded records in the preview.
- **FR-010**: System MUST validate that the tenure lookback input is a positive whole number before calculating.
- **FR-011**: The applied rate MUST remain editable after being applied — the census-derived value is a suggestion, not a locked value.

### Key Entities

- **Census Participation Data**: Employee records from the uploaded census containing enrollment status (enrolled vs. not enrolled) and tenure (years of service). Used as the source for the non-participant rate calculation.
- **Tenure Lookback**: A user-configured threshold (whole number of years) that filters the census to employees hired recently enough to be considered reflective of current enrollment behavior.
- **Non-Participant Rate**: The calculated ratio of eligible employees not enrolled in the DC plan to total eligible employees, within the tenure lookback window. This rate is suggested as the opt-out rate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Analysts can open the "Match Census" preview, review the suggested rate, and apply it to the opt-out rate field in under 60 seconds.
- **SC-002**: The preview accurately reflects the census data — the displayed non-participant count and total eligible count, when divided, equal the suggested rate with no rounding error greater than 0.001.
- **SC-003**: Changing the tenure lookback value updates the preview statistics without requiring a page reload or additional button click.
- **SC-004**: 100% of attempts to use "Match Census" without a census file result in an informative message rather than a silent failure or unhandled error.
- **SC-005**: The applied census-derived opt-out rate persists correctly when the scenario is saved and reloaded, identical to manually entered values.

## Assumptions

- The feature adds the "Match Census" button to the single global opt-out rate field (or the primary opt-out rate field), not to each of the 8 demographic-segmented fields individually. The derived rate applies as a single aggregate value. This mirrors the band configuration "Match Census" pattern which suggests a single boundary set.
- "Eligible" means employees who meet the DC plan eligibility criteria already defined in the scenario configuration (e.g., met minimum hours, satisfied waiting period). Non-participants are eligible employees with no active enrollment record.
- Tenure is measured in years from the hire date as of the census snapshot date, consistent with how tenure is used elsewhere in the simulation.
- The lookback defaults to 3 years, matching the issue example, as shorter lookbacks are more reflective of current enrollment behavior for recently onboarded employees.
- The feature does not modify or re-derive the demographic-segmented opt-out rates (age and income bands from E068); it only populates the single aggregate opt-out rate. Demographic-band breakdowns from census matching may be considered as a future enhancement.
