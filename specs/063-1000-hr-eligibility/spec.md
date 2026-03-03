# Feature Specification: ERISA 1,000-Hour Eligibility Rules

**Feature Branch**: `063-1000-hr-eligibility`
**Created**: 2026-03-03
**Status**: Draft
**Input**: User description: "Research how the 1-year, 1,000-hour eligibility requirement works in 401(a)/403(b) retirement plans under ERISA. Implement formal eligibility computation periods and distinct eligibility vs. vesting service credit tracking."

## Clarifications

### Session 2026-03-03

- Q: How should the system handle the IECP (which spans arbitrary 12-month windows from hire date) within the existing annual simulation pipeline? → A: Boundary-aware annual approximation — keep annual pipeline steps but add logic to prorate and track hours across the two plan years that an IECP spans, using hire date to define the boundary.
- Q: How should this feature relate to the existing `int_employer_eligibility.sql` model (which handles match/core contribution allocation eligibility)? → A: Parallel new models — create new models (`int_eligibility_computation_period`, `int_service_credit_accumulator`) alongside the existing model. The existing model continues to handle match/core allocation eligibility (a distinct concept from ERISA plan participation eligibility).
- Q: Should break-in-service rules (rehire scenarios, Rule of Parity, hold-out, maternity credit) be modeled? → A: No. PlanAlign is a plan design decision engine, not a recordkeeping system. The eligibility model assumes continuous employment — all employees in the simulation are active. Break-in-service tracking, rehire scenarios, and all related requirements (FR-006, FR-007, FR-009, FR-011) are removed from scope entirely.

## Out of Scope

- **Break-in-service tracking**: No modeling of consecutive breaks, break counters, or the 501-hour buffer zone. PlanAlign assumes continuous employment.
- **Rehire scenarios**: No service credit restoration, Rule of Parity, or one-year hold-out rule. If an employee is in the simulation, they are active.
- **Maternity/paternity leave crediting**: No 501-hour absence crediting (IRC 410(a)(5)(E)).
- **2-year eligibility plans**: The 2-year eligibility requirement with 100% immediate vesting (IRC 410(a)(1)(B)(i)) is not modeled.
- **Elapsed time method**: The elapsed time method (26 CFR 1.410(a)-7) is not implemented in this iteration. Only the prorated hours method (2,080-hour annual baseline) is supported. Elapsed time may be added in a future iteration if client demand warrants it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Formal Eligibility Computation Periods (Priority: P1)

As a plan administrator running a simulation, I need the system to correctly determine when each employee first becomes eligible for plan participation using ERISA-compliant eligibility computation periods (initial 12-month period from hire date, then switching to plan year method) so that entry dates are accurate.

**Why this priority**: The initial eligibility computation period (IECP) is the foundational ERISA requirement (IRC 410(a)(3)(A), 29 CFR 2530.202-2). Without it, all downstream eligibility dates are approximate. The current system uses a simple calendar-year proration, which does not account for mid-year hires whose IECP spans two calendar years.

**Independent Test**: Can be fully tested by simulating employees hired at various points throughout the year and verifying that (a) the IECP is correctly defined as the 12-month period from hire date, (b) hours are measured within that period, and (c) the system switches to the plan year method after the first anniversary.

**Acceptance Scenarios**:

1. **Given** an employee hired April 1, 2025 in a calendar-year plan, **When** the employee works 1,000+ hours between April 1, 2025 and March 31, 2026, **Then** the system records one year of eligibility service and computes the plan entry date as no later than July 1, 2026 (6 months after satisfying the requirement) or January 1, 2027 (first day of next plan year), whichever is earlier.
2. **Given** an employee hired October 1, 2025 who works only 600 hours in the IECP (Oct 2025–Sep 2026), **When** the system switches to the plan year method, **Then** the system checks hours in the 2026 calendar year (Jan–Dec 2026). If the employee reaches 1,000 hours in that period, one year of eligibility service is credited.
3. **Given** an employee hired April 1, 2025 who works 1,000+ hours in both the IECP (Apr 2025–Mar 2026) AND the 2026 plan year (Jan–Dec 2026), **When** the system evaluates eligibility, **Then** the employee is credited with two years of eligibility service per the overlap/double-credit rule (29 CFR 2530.202-2(a)(2)).

---

### User Story 2 - 1,000-Hour Eligibility Threshold (Priority: P1)

As a plan administrator, I need the system to correctly determine whether each employee meets the 1,000-hour threshold per computation period so that eligibility and vesting service credit decisions are accurate.

**Why this priority**: The 1,000-hour threshold (per IRC 410(a)(3)(A)) is the binary gate for earning a year of service. The current system tracks hours but does not formally apply the threshold within ERISA computation periods.

**Independent Test**: Can be fully tested by creating employees with different annual hour totals (e.g., 400, 600, 1,100, 2,080) and verifying the correct eligibility determination for each.

**Acceptance Scenarios**:

1. **Given** an employee who works 1,100 prorated hours in a computation period, **When** the system evaluates service, **Then** the employee is credited with one year of service (eligibility and/or vesting, as applicable).
2. **Given** a part-time employee who works 600 prorated hours in a computation period, **When** the system evaluates service, **Then** the employee receives no year-of-service credit for that period.
3. **Given** an employee hired mid-year who works full-time for the remainder of the year, **When** the system prorates hours within the IECP, **Then** the prorated hours are correctly compared against the 1,000-hour threshold.

---

### User Story 3 - Separate Eligibility vs. Vesting Service Credit (Priority: P2)

As a plan administrator, I need the system to track eligibility service credit and vesting service credit independently, using their respective computation periods, so that employees can have different service credit totals for each purpose.

**Why this priority**: Eligibility and vesting have structurally different rules (IRC 410(a) vs. 411(a); 29 CFR 2530.202-2 vs. 2530.203-2). The eligibility computation period mandatorily starts from hire date and may shift to plan year; the vesting computation period is designated once by the plan and does not shift. Conflating these produces incorrect results.

**Independent Test**: Can be fully tested by simulating an employee who works 2,000 hours in 8 months then terminates, and verifying they receive one year of vesting service but zero years of eligibility service (because the 12-month eligibility period was not completed).

**Acceptance Scenarios**:

1. **Given** an employee hired January 15, 2025 who works 1,500 hours and terminates July 31, 2025, **When** the system evaluates service credit, **Then** the employee receives one year of vesting service credit (1,500 hours >= 1,000 in the VCP) but zero years of eligibility service credit (did not complete a 12-month eligibility computation period).
2. **Given** a plan using the calendar year as both the VCP and the plan year, **When** the system tracks service for an employee hired mid-year, **Then** the eligibility computation period starts from the hire date (IECP) while the vesting computation period uses the calendar year, and these are tracked separately.

---

### Edge Cases

- What happens when an employee is hired on the first day of the plan year (January 1)? The IECP and plan year coincide — the system should handle this gracefully without double-counting.
- How are hours tracked for employees who transition between full-time and part-time mid-year? The system does not distinguish FT/PT status — hours are always prorated from the 2,080-hour annual baseline based on employment duration within the computation period. FT/PT transitions do not affect the proration formula.
- What happens when an employee works exactly 1,000 hours? The threshold is "not less than 1,000 hours" per IRC 410(a)(3)(A), so exactly 1,000 hours meets the requirement.
- What happens when a new hire's IECP and the overlapping plan year both produce exactly 999 hours? Neither period satisfies the 1,000-hour threshold, so no year of service is credited in either.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute the Initial Eligibility Computation Period (IECP) as the 12-consecutive-month period beginning on each employee's employment commencement date (hire date), per 29 CFR 2530.202-2.
- **FR-002**: System MUST support switching from the IECP to the plan year method after the first anniversary of the employment commencement date, per 29 CFR 2530.202-2(a)(1).
- **FR-003**: System MUST apply the overlap/double-credit rule: when an employee completes 1,000 hours in both the IECP and the overlapping plan year, two years of eligibility service are credited, per 29 CFR 2530.202-2(a)(2).
- **FR-004**: System MUST determine whether each employee meets the 1,000-hour threshold per computation period, classifying the result as either "year of service" (>= 1,000 hours) or "no credit" (< 1,000 hours).
- **FR-005**: System MUST compute the plan entry date as no later than the earlier of: (a) the first day of the first plan year beginning after the employee meets eligibility requirements, or (b) 6 months after meeting the requirements, per IRC 410(a)(4).
- **FR-006**: System MUST track eligibility service credit and vesting service credit independently using their respective computation periods (ECP and VCP), per 29 CFR 2530.202-2 and 29 CFR 2530.203-2.
- **FR-007**: System MUST support configurable plan parameters: plan year start/end dates, eligibility hour threshold, and vesting computation period type (plan year or anniversary year).

### Key Entities

- **Eligibility Computation Period (ECP)**: A 12-month measurement window used to determine whether an employee has completed a year of eligibility service. Begins as the IECP (from hire date), then may switch to the plan year. Key attributes: start date, end date, period type (IECP vs. plan year), hours credited, service credit outcome (year of service / no credit).
- **Vesting Computation Period (VCP)**: A 12-month measurement window used to determine vesting service credit. Designated by the plan (calendar year or anniversary year). Key attributes: start date, end date, period type, hours credited, service credit outcome.
- **Service Credit Accumulator**: Per-employee cumulative record of eligibility service years and vesting service years. Updated each computation period. Key attributes: employee ID, eligibility years credited, vesting years credited, total hours by period, plan entry date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For employees hired mid-year, the system correctly computes the IECP from the hire date and determines eligibility within the first 18 months of employment, matching manual calculations for 100% of test scenarios.
- **SC-002**: The 1,000-hour threshold correctly determines year-of-service credit for all boundary values (0, 999, 1000, 2080 hours) in every computation period.
- **SC-003**: Eligibility service credit and vesting service credit are independently tracked and may differ for the same employee in the same simulation year (e.g., an employee can have 1 year of vesting credit and 0 years of eligibility credit).
- **SC-004**: Plan entry dates are computed correctly per IRC 410(a)(4), never exceeding the statutory maximum delay (6 months or start of next plan year, whichever is earlier).
- **SC-005**: All eligibility determination results are traceable to specific computation periods and hour totals, supporting full audit trail reconstruction.

## Assumptions

- The simulation engine uses a prorated hours model (2,080 annual hours for full-time, prorated by employment dates). Actual hours tracking is not available from census data; the system estimates hours based on employment duration.
- **IECP implementation uses boundary-aware annual approximation**: The existing annual pipeline is preserved. For mid-year hires, hours are prorated across the two plan years that the IECP spans (e.g., an April 1 hire's IECP covers 9 months of Year 1 and 3 months of Year 2). The system tracks the hire-date boundary to split and sum hours correctly within the annual step, rather than adding sub-annual pipeline stages.
- The hour-counting method is the prorated hours method (2,080-hour annual baseline). The elapsed time method is out of scope for this iteration.
- The plan year defaults to the calendar year (January 1–December 31) unless configured otherwise in `simulation_config.yaml`.
- The vesting computation period defaults to the plan year unless configured to use the anniversary year.
- **Continuous employment assumed**: All employees in the simulation are active. The system does not model rehire scenarios, break-in-service tracking, or service credit restoration. PlanAlign is a plan design decision engine, not a recordkeeping system.
- **Migration strategy**: New models are created in parallel to the existing `int_employer_eligibility.sql`. The existing model retains its role for match/core contribution allocation eligibility. The new ERISA plan participation eligibility models (`int_eligibility_computation_period`, `int_service_credit_accumulator`) operate independently and do not modify or replace the existing model.

## Regulatory References

| Citation | Subject | Application |
|----------|---------|-------------|
| IRC 410(a)(1) | Minimum participation standards | Maximum 1-year / 1,000-hour eligibility requirement |
| IRC 410(a)(3)(A) | Year of service definition | 12-month period with 1,000+ hours |
| IRC 410(a)(4) | Entry date requirements | Within 6 months or start of next plan year |
| IRC 411(a) | Minimum vesting standards | 1,000 hours = year of vesting service |
| ERISA 202 (29 USC 1052) | Minimum participation standards | Parallel to IRC 410(a) |
| ERISA 203 (29 USC 1053) | Minimum vesting standards | Parallel to IRC 411(a) |
| 29 CFR 2530.200b-2 | Hour of service definition | What counts as an hour of service |
| 29 CFR 2530.202-2 | Eligibility computation period | IECP from hire date; switching to plan year |
| 29 CFR 2530.203-2 | Vesting computation period | Plan designates; no mandatory shift |
| 26 CFR 1.410(a)-7 | Elapsed time method | Alternative to hour-counting |
