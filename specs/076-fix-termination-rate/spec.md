# Feature Specification: Fix Termination Rate Suggestion Bug

**Feature Branch**: `076-fix-termination-rate`
**Created**: 2026-03-18
**Status**: Draft
**Input**: Fix GitHub issue #245 - Suggested termination rate always shows 100%

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Calculate Realistic Termination Rate from Census Data (Priority: P1)

When a user uploads workforce census data and views the suggested termination rate, the system should calculate a realistic rate based on the census data rather than defaulting to 100%.

**Why this priority**: This is the core issue reported in the bug. Without fixing the calculation logic, the feature is unusable for all scenarios. Users cannot make informed decisions about termination rates when the suggestion is always 100%.

**Independent Test**: Can be fully tested by uploading a census file and verifying that the suggested termination rate reflects the actual data (not always 100%) and can be validated against the census independently.

**Acceptance Scenarios**:

1. **Given** a census file with workforce data is uploaded, **When** the termination rate suggestion is requested, **Then** the suggested rate reflects realistic values (not 100%) derived from the census
2. **Given** a census with historical terminations tracked, **When** the system calculates suggested rate, **Then** the rate is calculated using appropriate denominators (active employees, not just terminations)
3. **Given** multiple census files with varying turnover patterns, **When** rates are suggested for each, **Then** each suggestion varies appropriately with the data (not all 100%)

---

### User Story 2 - Handle Edge Cases in Termination Rate Calculation (Priority: P2)

The system should gracefully handle edge cases that might have caused the 100% fallback, such as empty datasets or missing data.

**Why this priority**: Prevents regression and improves robustness. Ensures the fix works across different data quality scenarios and doesn't just patch the immediate bug.

**Independent Test**: Can be tested by providing census data with edge cases (empty, minimal, or unusual data patterns) and verifying the system returns reasonable values and error messages instead of 100%.

**Acceptance Scenarios**:

1. **Given** a census with no active employees, **When** termination rate is calculated, **Then** the system returns a clear message about insufficient data rather than defaulting to 100%
2. **Given** a census with only one employee, **When** the rate is calculated, **Then** the system handles this gracefully (either 0%, or a message about needing more data)
3. **Given** a census with missing termination data, **When** the system attempts calculation, **Then** it either estimates based on available data or returns a specific error message

---

### Edge Cases

- What happens when the census has no termination records?
- How does the system handle very small employee populations (1-5 people)?
- What if the data has missing or null values in key fields used for calculation?
- How should the system behave if it cannot calculate a meaningful rate from the data?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST calculate termination rate based on actual census data (terminated employees / active employees) rather than hardcoding 100%
- **FR-002**: System MUST identify and fix the root cause of the 100% suggestion (division error, missing denominator, or filter issue)
- **FR-003**: System MUST use the correct denominator for the calculation (total active employees in the period, not just terminations)
- **FR-004**: System MUST handle cases where the denominator is zero or data is insufficient without defaulting to 100%
- **FR-005**: System MUST validate that termination rate suggestions vary appropriately across different census datasets
- **FR-006**: System MUST return termination rate suggestions as a percentage value between 0% and 100% (exclusive of 100% for normal cases)

### Key Entities *(include if feature involves data)*

- **Census Data**: Workforce snapshot containing employee counts, statuses, and historical terminations used for rate calculation
- **Termination Rate Suggestion**: A calculated percentage representing the recommended annual termination rate derived from census data
- **Active Employees**: Count of employees in active status during the period used as the denominator in rate calculation
- **Terminated Employees**: Count of employees who separated during a given period, used as the numerator in rate calculation

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Termination rate suggestions return values between 0% and 99% for normal datasets (no more 100% defaults)
- **SC-002**: Suggested rates vary appropriately across different census files (coefficient of variation > 0.1 across test datasets with different turnover patterns)
- **SC-003**: Edge cases (empty data, single employee, missing values) are handled with informative messages instead of 100% defaults
- **SC-004**: 100% of tested census files return realistic rates that can be validated against the data
- **SC-005**: System maintains consistent calculation logic across all scenarios (same census should always produce the same suggestion)

## Assumptions

- The termination rate is calculated as: (number of employees terminated in period) / (average active employees in period) × 100%
- Census data includes fields for employee status, termination dates, and employment dates
- The suggestion endpoint or service layer has a fallback or error case that returns 100% when data is unavailable
- Historical termination data is available in the census or can be inferred from employment records

## Dependencies

- Access to the termination rate suggestion service/endpoint code
- Access to the census data schema and available fields
- Test datasets with known termination rates for validation

## Notes

- Investigation should focus on: division errors, missing denominators, filters that return empty active employee lists, and any fallback logic defaulting to 100%
- The fix should maintain backward compatibility with existing scenario configurations
