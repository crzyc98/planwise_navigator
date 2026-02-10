# Feature Specification: Salary Range Configuration UX Improvements

**Feature Branch**: `044-fix-salary-range-ux`
**Created**: 2026-02-10
**Status**: Draft
**Input**: User description: "Two UX improvements for salary range configuration in PlanAlign Studio's ConfigStudio: default Match Census scale factor to 1.5x and fix finicky salary range input boxes"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Comfortable Salary Range Editing (Priority: P1)

As a plan administrator editing job level compensation ranges in ConfigStudio, I want salary range input fields that allow me to type, delete, and correct values naturally without the inputs snapping to unexpected values, clipping large numbers, or feeling laggy.

**Why this priority**: This is the core usability issue. Broken input behavior blocks administrators from performing their primary task (configuring salary ranges), causing frustration and potential data entry errors.

**Independent Test**: Can be fully tested by opening the Job Level Compensation table, editing min/max values across all job levels, and verifying natural text editing behavior. Delivers immediate usability improvement for every salary range interaction.

**Acceptance Scenarios**:

1. **Given** a job level row with min compensation of $100,000, **When** the user clears the field and types "550000", **Then** the field displays "550000" without snapping to 0 or showing intermediate invalid values during editing.
2. **Given** a job level row, **When** the user edits a salary value using backspace to delete digits before retyping, **Then** the field remains editable with the partial value visible (no forced conversion to 0).
3. **Given** the compensation table with a job level at max compensation of $600,000, **When** the user views the input field, **Then** the full value is visible without clipping or requiring horizontal scrolling within the input.
4. **Given** a job level row, **When** the user sets min compensation to $120,000 and max compensation to $80,000, **Then** the system displays inline visual feedback indicating the min exceeds the max.
5. **Given** a job level row, **When** the user uses keyboard arrow keys to adjust a salary value, **Then** the value increments or decrements in a reasonable step size that does not jump by large amounts.

---

### User Story 2 - Practical Default Scale Factor for Match Census (Priority: P2)

As a plan administrator using the "Match Census" feature to derive salary ranges from census data, I want the default scale factor to be 1.5x so that the generated salary ranges reflect a more practical starting point for new hire ranges that typically exceed census medians.

**Why this priority**: This is a single default value change that improves the out-of-box experience. While important for new users, it does not block functionality — administrators can always manually adjust the scale factor.

**Independent Test**: Can be fully tested by navigating to the compensation configuration section and observing that the scale factor field shows 1.5 by default before any user interaction. Delivers a better starting point without requiring user adjustment.

**Acceptance Scenarios**:

1. **Given** the ConfigStudio compensation section is loaded for the first time, **When** the user views the Match Census scale factor input, **Then** the default value displayed is 1.5.
2. **Given** the default scale factor of 1.5, **When** the user clicks "Match Census" without changing the scale factor, **Then** the derived salary ranges are calculated using a 1.5x multiplier against census medians.
3. **Given** the default scale factor of 1.5, **When** the user changes the scale factor to 2.0, **Then** the system respects the user-specified value of 2.0 for subsequent Match Census calculations.

---

### Edge Cases

- What happens when the user clears a salary input field entirely and clicks away? The field should retain the empty state visually and commit a value of 0 on blur, without producing errors.
- What happens when the user types non-numeric characters? The field should reject non-numeric input gracefully.
- What happens when min and max compensation are equal? This is a valid configuration and should not trigger a validation warning.
- What happens when a salary value is 0? The system should accept 0 as a valid entry (e.g., for unpaid levels or placeholder rows).
- What happens when the user changes the scale factor to 0 or a negative value? The system should prevent non-positive scale factors.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display 1.5 as the default value for the Match Census compensation scale factor when the configuration page loads.
- **FR-002**: System MUST allow users to type, delete, and edit salary values in min/max compensation fields without the value snapping to 0 during partial edits.
- **FR-003**: System MUST display salary input fields wide enough to show values up to at least $999,999 without clipping.
- **FR-004**: System MUST display inline visual feedback (e.g., red border, warning text) on a job level row when the min compensation exceeds the max compensation.
- **FR-005**: System MUST commit salary value changes only when the user finishes editing (on blur or Enter), not on every keystroke.
- **FR-006**: System MUST use a step size for arrow key increments that is comfortable and not excessively large.
- **FR-007**: System MUST allow the user to override the default scale factor with any positive numeric value.
- **FR-008**: System MUST accept 0 as a valid salary input without triggering errors.
- **FR-009**: System MUST prevent the Match Census scale factor from being set to 0 or a negative number.

### Key Entities

- **Job Level Compensation Row**: Represents a single job level's salary range configuration, containing level identifier, level name, minimum compensation, and maximum compensation.
- **Match Census Scale Factor**: A positive numeric multiplier applied to census-derived salary medians to produce recommended salary ranges.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can edit a salary range value (including deleting and retyping all digits) without the field displaying incorrect intermediate values during editing.
- **SC-002**: All salary values up to $999,999 are fully visible in the input fields without horizontal scrolling or clipping.
- **SC-003**: 100% of job level rows with min compensation exceeding max compensation display a visible inline warning.
- **SC-004**: The Match Census scale factor defaults to 1.5 on every fresh page load.
- **SC-005**: Users report no perceived lag when editing salary range values (input response feels instantaneous).

## Assumptions

- The min > max validation is visual-only (warning indicator) and does not block saving, since administrators may be mid-edit across multiple fields.
- The scale factor change is a frontend-only default; no backend or API changes are needed.
- The existing compensation change handler is the only location where salary value updates are committed to form state.
