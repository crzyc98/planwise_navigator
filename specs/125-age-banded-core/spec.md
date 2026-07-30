# Feature Specification: Age-Banded Employer Core Contributions

**Feature Branch**: `125-age-banded-core`
**Created**: 2026-07-30
**Status**: Draft
**Input**: User description: "Add an age-banded employer core contribution mode with validated age schedules, accurate plan-design displays, and consistent contribution auditing."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure an age-banded core contribution (Priority: P1)

A plan administrator can select an age-banded employer core contribution and define the contribution percentage for each age range in the plan document. This lets the administrator model age-based non-elective designs directly rather than approximating them with a combined age-and-service formula.

**Why this priority**: Directly representing the plan document is the core business value. Without it, administrators cannot produce a reliable client-facing simulation for this common design.

**Independent Test**: Configure contiguous age tiers, save the plan design, and confirm that the saved design continues to show the selected mode and every configured tier.

**Acceptance Scenarios**:

1. **Given** core contributions are enabled, **When** the administrator chooses the age-banded option, **Then** they can enter a minimum age, maximum age, and contribution percentage for each tier.
2. **Given** a valid age schedule is saved, **When** the administrator reopens the plan design, **Then** the age-banded mode and all saved tiers are displayed accurately.
3. **Given** an age schedule with tiers 0–30 at 3%, 30–40 at 4%, 40–50 at 5%, and 50+ at 6%, **When** an administrator views the plan-design summary or scenario comparison, **Then** it describes the design as age-banded and shows the configured age ranges and rates rather than describing it as a flat-rate plan.

---

### User Story 2 - Apply the correct annual age-based contribution rate (Priority: P1)

A plan administrator runs a multi-year scenario with an age-banded core contribution. Every eligible employee receives the rate for the age tier applicable to that simulation year, and the reported rate always explains the contribution amount.

**Why this priority**: A configurable design is only valuable if its financial results are correct, traceable, and stable from year to year.

**Independent Test**: Run a scenario with known employee ages at and around tier boundaries, then compare each employee’s reported core rate and core contribution amount to the configured tier and annual compensation basis.

**Acceptance Scenarios**:

1. **Given** tiers of 30–40 at 4% and 40–50 at 5%, **When** an employee’s annual age is exactly 40, **Then** the employee receives the 5% rate.
2. **Given** an employee turns 50 during a simulation year, **When** their annual core contribution is calculated, **Then** the 50+ rate applicable to their recorded age for that simulation year is used for the entire year; the rate is not blended across the birthday.
3. **Given** an employee is hired partway through the year, **When** the employee qualifies for an age-banded core contribution, **Then** the selected annual age-tier rate applies to the employee’s prorated annual compensation without prorating the rate itself.
4. **Given** an age-banded scenario runs for multiple years, **When** employees cross a tier boundary in a later simulation year, **Then** their annual core rate moves to the applicable later-year tier.
5. **Given** any supported core contribution mode, **When** a contribution is reported, **Then** its displayed or audited core rate multiplied by the applicable compensation basis equals the reported core contribution amount, subject only to documented monetary rounding.

---

### User Story 3 - Prevent invalid age schedules (Priority: P2)

A plan administrator receives clear, blocking feedback when an age-banded schedule could leave an age uncovered, assign an age to more than one tier, use an empty or reversed range, or contain a negative rate. This prevents an incomplete schedule from silently assigning an unintended fallback rate.

**Why this priority**: Invalid tiers can materially misstate employer cost and participant benefits; configuration must fail early and clearly.

**Independent Test**: Attempt to load or save schedules containing a gap, overlap, invalid age range, or negative rate and verify that the configuration is rejected with an explanation of the affected tier or boundary.

**Acceptance Scenarios**:

1. **Given** adjacent tiers whose ranges leave an uncovered interval, **When** the configuration is validated, **Then** it is rejected and identifies the gap.
2. **Given** tiers whose ranges cover the same age, **When** the configuration is validated, **Then** it is rejected and identifies the overlap.
3. **Given** a tier where the minimum age equals or exceeds the maximum age, **When** the configuration is loaded or saved, **Then** it is rejected before a simulation can run.
4. **Given** a tier with a negative contribution rate, **When** the configuration is loaded or saved, **Then** it is rejected before a simulation can run.

### Edge Cases

- A schedule may use an unbounded final tier to cover all ages at or above its minimum age.
- Age tier boundaries use inclusive minimums and exclusive maximums; an employee at an exact shared boundary belongs to the higher tier.
- An empty age schedule uses the configured flat core rate, preserving a usable fallback for incomplete optional schedules.
- Missing annual age is treated consistently with the existing contribution calculation’s default age behavior; plan administrators are alerted through existing data-quality controls rather than silently assigned an arbitrary tier.
- Existing flat, service-graded, and points-based core contribution designs retain exactly their current results and summaries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer `age_banded` as an employer core contribution mode alongside flat, service-graded, and points-based modes.
- **FR-002**: The system MUST allow an age-banded core contribution schedule consisting of age ranges and non-negative contribution percentages.
- **FR-003**: The system MUST resolve each employee’s age-banded rate once per simulation year from that year’s recorded point-in-time age.
- **FR-004**: The system MUST assign a boundary age to the tier whose minimum equals that age, using inclusive-minimum and exclusive-maximum intervals.
- **FR-005**: The system MUST apply the selected annual rate to the employee’s applicable annual compensation basis, including prorated compensation for mid-year hires, without prorating the rate.
- **FR-006**: The system MUST use the same resolved core rate for both the contribution amount and its auditable reported rate for every core contribution mode.
- **FR-007**: The system MUST preserve the existing calculated results for flat, service-graded, and points-based core contribution modes.
- **FR-008**: The system MUST reject an age schedule with a gap, overlap, reversed or empty finite range, or negative contribution rate before simulation execution.
- **FR-009**: When an age-banded mode has no configured tiers, the system MUST use the configured flat core rate as its fallback.
- **FR-010**: The system MUST preserve age-banded schedules through every supported plan-design configuration path, with contribution percentages retaining their intended value across configuration and simulation.
- **FR-011**: The plan-design editor MUST allow administrators to select, create, edit, and review age-banded core contribution tiers.
- **FR-012**: Plan-design details and scenario comparisons MUST identify an age-banded core design accurately and display its configured schedule.
- **FR-013**: The system MUST not present a clean nondiscrimination pass for an age-banded core design without the same age-related caveat currently surfaced for benefit concentrations that require further nondiscrimination analysis.

### Key Entities

- **Age-Banded Core Schedule**: A set of ordered age tiers for an employer core contribution, each with a minimum age, optional maximum age, and contribution percentage.
- **Age-Banded Core Tier**: One inclusive-minimum, exclusive-maximum age interval and its contribution percentage; the final tier may be open-ended.
- **Annual Core Contribution Decision**: The annual employee-level record of the resolved core rate, applicable compensation basis, and resulting employer core contribution.
- **Plan-Design Summary**: The client-facing description of a scenario’s employer core contribution design and, when applicable, its age schedule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can configure, save, reopen, and accurately review a valid age-banded core schedule with at least four tiers without converting it to another core contribution mode.
- **SC-002**: In a boundary-focused scenario, 100% of employees receive the configured rate for their annual age tier, including every employee whose age is exactly a tier boundary.
- **SC-003**: For every employee and supported core contribution mode in regression scenarios, the reported core rate and compensation basis reproduce the reported core contribution amount within documented monetary rounding.
- **SC-004**: 100% of schedules containing a gap, overlap, reversed or empty finite interval, or negative rate are rejected before a simulation begins.
- **SC-005**: Existing flat, service-graded, and points-based regression scenarios produce identical contribution results before and after this feature.
- **SC-006**: 100% of plan-design and scenario-comparison views for age-banded scenarios identify the design as age-banded and list its configured tiers.

## Assumptions

- Annual age is already available for each employee and simulation year and remains the authoritative value for the tier decision.
- Contribution percentages entered by administrators are displayed as percentages and retain their intended percentage value throughout configuration and calculation.
- The feature includes an age-related nondiscrimination caveat but does not add a new age-weighted nondiscrimination test or determine plan qualification.
- Age schedules are intended to cover the relevant non-negative age domain continuously; validation does not substitute reporting age bands for plan-design tier boundaries.
- The feature does not change contribution eligibility, compensation definitions, or the treatment of existing core contribution modes.

## Out of Scope

- Prorating a core contribution rate across an employee’s birthday within a simulation year.
- Replacing or changing the plan’s shared reporting age bands.
- Adding a new age-weighted nondiscrimination test, cross-testing methodology, or legal qualification conclusion.
