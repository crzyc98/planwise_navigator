# Feature Specification: Service-Based Match Contribution Tiers

**Feature Branch**: `010-fix-match-service-tiers`
**Created**: 2026-01-05
**Status**: Draft
**Input**: User description: "Investigate if the employer match contributions model has the same bug that was fixed in E009 for core contributions."

## Investigation Summary

This investigation examined whether the employer match contributions model (`int_employee_match_calculations.sql`) has the same service-based tier bug that was fixed in E009 for core contributions.

### Finding: Not a Bug - Different Design Pattern

**The E009 bug does NOT exist in the match model** because match contributions were intentionally designed for **deferral-rate-based tiers**, not service-based tiers.

| Aspect                | Core Contributions (E009 Fix)           | Match Contributions (Current)            |
|-----------------------|-----------------------------------------|------------------------------------------|
| Tier Basis            | Years of service                        | Employee deferral rate %                 |
| Variable              | `employer_core_graded_schedule`         | `match_tiers`                            |
| Tier Fields           | `min_years`, `max_years`, `rate`        | `employee_min`, `employee_max`, `match_rate` |
| Status Variable       | `employer_core_status` ('graded_by_service') | N/A (no service-based mode)         |
| Macro                 | `get_tiered_core_rate`                  | Inline CASE expression                   |

### Key Files Analyzed

1. **dbt/models/intermediate/events/int_employee_match_calculations.sql** (lines 49-54): Uses `match_tiers` with deferral-rate-based tier logic
2. **dbt/macros/get_tiered_core_rate.sql**: Service-based rate macro (core only)
3. **planalign_orchestrator/config/export.py** (lines 355-415): Exports `match_tiers`, `match_template`, `match_cap_percent`
4. **artifacts/runs/*/summary.json**: Confirms UI sends deferral-based tiers only

### Conclusion

If service-based match tiers are needed (e.g., "0-5 years service: 50% match, 5+ years: 100% match"), this is a **feature request** requiring new implementation, not a bug fix.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Service-Based Match Rates (Priority: P1)

As a plan administrator, I want to configure employer match contribution rates that vary by employee years of service, so that I can reward employee loyalty with increasing match rates.

**Why this priority**: This is the primary capability requested. Service-based matching is a common plan design pattern for 401(k) plans.

**Independent Test**: Can be fully tested by configuring a 2-tier service-based match schedule and verifying employees with different tenure receive the correct match rates.

**Acceptance Scenarios**:

1. **Given** match is configured with service tiers (0-4 years: 50% up to 6%, 5+ years: 100% up to 6%), **When** an employee with 3 years, $100k salary, contributes 6%, **Then** employer match = 50% × 6% × $100k = $3,000
2. **Given** match is configured with service tiers (0-4 years: 50% up to 6%, 5+ years: 100% up to 6%), **When** an employee with 7 years, $100k salary, contributes 6%, **Then** employer match = 100% × 6% × $100k = $6,000
3. **Given** service tier has max_deferral_pct = 6%, **When** employee contributes 10% of $100k salary, **Then** match only applies to first 6% (capped)
4. **Given** match status is set to 'graded_by_service', **When** simulation runs, **Then** each employee's match uses their years of service to determine rate

---

### User Story 2 - UI Configuration for Service-Based Match (Priority: P2)

As a plan administrator using PlanAlign Studio, I want to configure service-based match tiers through the web interface, so that I can easily set up and modify match schedules without editing config files.

**Why this priority**: Depends on P1 implementation but essential for usability.

**Independent Test**: Can be tested by creating a service-based match schedule in the UI and verifying it saves correctly to scenario config.

**Acceptance Scenarios**:

1. **Given** I am on the match configuration page, **When** I select "Service-based" match type, **Then** I see input fields for service tier definitions
2. **Given** I configure service tiers (0-5 years: 50%, 5+ years: 75%), **When** I save the configuration, **Then** the tiers are persisted with correct field names for dbt consumption

---

### User Story 3 - Audit Trail for Applied Service Tier (Priority: P3)

As a compliance officer, I want to see which service tier was applied to each employee's match calculation, so that I can audit and verify the correct rates were used.

**Why this priority**: Important for compliance but not blocking core functionality.

**Independent Test**: Can be tested by running a simulation and querying the output for the applied_years_of_service audit field.

**Acceptance Scenarios**:

1. **Given** a completed simulation with service-based match, **When** I query the match calculations output, **Then** I can see the `applied_years_of_service` field for each employee

---

### Edge Cases

- What happens when an employee has exactly the boundary years (e.g., exactly 5 years when tier changes at 5)?
  - Use [min, max) interval convention consistent with core contributions
- What happens when both deferral-rate tiers AND service-based rates are configured?
  - Not applicable: each simulation uses ONE match formula type (mutually exclusive)
- How does the system handle employees with null/missing tenure data?
  - Default to 0 years of service (lowest tier)
- What happens when service tiers have gaps (e.g., 0-3 years, 5+ years)?
  - Validate configuration to prevent gaps

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support `employer_match_status` variable with mutually exclusive values: 'none', 'flat', 'deferral_based', 'graded_by_service' (one formula per simulation)
- **FR-002**: System MUST support `employer_match_graded_schedule` variable accepting a list of service tiers with `min_years`, `max_years`, `rate`, and `max_deferral_pct`
- **FR-003**: When `employer_match_status` = 'graded_by_service', system MUST calculate match as: (service tier rate) × min(employee deferral %, max_deferral_pct) × compensation
- **FR-004**: System MUST provide a `get_tiered_match_rate` macro (or reuse `get_tiered_core_rate`) for service-based rate lookup
- **FR-005**: Config export MUST transform UI field names (`service_years_min`, `service_years_max`, `match_rate`, `max_deferral_pct`) to dbt macro format (`min_years`, `max_years`, `rate`, `max_deferral_pct`)
- **FR-006**: Match calculation output MUST include `applied_years_of_service` audit field when service-based matching is enabled
- **FR-007**: System MUST validate service tier configurations for gaps and overlaps
- **FR-008**: System MUST maintain backward compatibility - existing deferral-rate-based simulations continue to work; service-based is a new mutually exclusive formula option
- **FR-009**: Service-based match mode MUST NOT apply match_cap_percent; tier rates apply directly to eligible compensation

### Key Entities

- **Service Tier**: Represents a years-of-service band with associated match rate and deferral cap (min_years, max_years, rate, max_deferral_pct)
- **Match Calculation**: Extended to include service tier lookup when graded_by_service mode is active
- **Match Configuration**: Extended to support both deferral-based and service-based tier modes

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Match rates correctly vary by employee years of service when graded_by_service mode is enabled
- **SC-002**: All existing deferral-based tier functionality continues to work unchanged (backward compatibility)
- **SC-003**: Service-based match configuration can be set via PlanAlign Studio UI
- **SC-004**: Audit trail includes applied_years_of_service for compliance review

## Files Requiring Modification

Based on the E009 fix pattern, implementing service-based match tiers would require:

1. **dbt/models/intermediate/events/int_employee_match_calculations.sql**
   - Add `employer_match_status` and `employer_match_graded_schedule` variable declarations
   - Add join to snapshot for years_of_service
   - Conditionally apply service-based rate when status = 'graded_by_service'
   - Add `applied_years_of_service` audit field

2. **dbt/macros/get_tiered_match_rate.sql** (new file, or reuse get_tiered_core_rate)
   - Create macro to return match rate based on years of service
   - Follow same pattern as `get_tiered_core_rate`

3. **planalign_orchestrator/config/export.py** (lines ~355-415, _export_employer_match_vars)
   - Add export for `employer_match_status`
   - Add export for `employer_match_graded_schedule` with field name transformation
   - Transform `service_years_min` -> `min_years`, `service_years_max` -> `max_years`, `contribution_rate` -> `rate`

4. **PlanAlign Studio frontend** (if UI configuration needed)
   - Add service-based match tier configuration component
   - Add match status toggle (deferral-based vs service-based)

## Clarifications

### Session 2026-01-05

- Q: Feature scope - verify deferral-based tiers vs add service-based? → A: Proceed with service-based; deferral-based tiers already work correctly
- Q: How does match_cap_percent interact with service-based tiers? → A: No match cap for service-based; tier rates apply directly without additional cap
- Q: What does the service tier rate apply to? → A: Rate applies to employee deferrals (not directly to compensation)
- Q: Can service tiers have complex deferral formulas (stretch, tiered)? → A: No - simple model: each service tier has ONE match rate applied to all deferrals
- Q: Should service-based match have a cap on deferral % matched? → A: Yes - each service tier defines a max deferral % to match (e.g., 100% match up to 6%)

## Assumptions

- Service-based match rates use the same [min, max) interval convention as core contributions
- Years of service is calculated the same way as for core contributions (using snapshot's years_of_service field)
- The `get_tiered_core_rate` macro can be generalized or duplicated for match purposes
- Rate values follow the same convention (UI sends as percentage, macro expects percentage)
