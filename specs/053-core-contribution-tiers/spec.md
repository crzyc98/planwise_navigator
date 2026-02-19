# Feature Specification: Core Contribution Tier Validation & Points-Based Mode

**Feature Branch**: `053-core-contribution-tiers`
**Created**: 2026-02-19
**Status**: Draft
**Input**: User description: "Add tier validation warnings to graded-by-service core contributions and add a points-based core contribution option"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tier Validation Warnings for Graded Core (Priority: P1)

A plan administrator configures graded-by-service core contributions and enters tier boundaries with gaps or overlaps. The system immediately displays amber warning messages highlighting the misconfiguration, just like the tenure-based and points-based match tier editors already do. This prevents the administrator from saving a broken schedule that would produce incorrect contribution calculations during simulation.

**Why this priority**: This is a parity fix for existing functionality. The validation logic already exists and works for match tiers; its absence from core tiers is a gap that can lead to silent misconfiguration errors. This is the highest-impact, lowest-effort improvement.

**Independent Test**: Can be fully tested by entering core tier configurations with known gaps/overlaps and verifying warning messages appear. Delivers immediate value by catching configuration errors before simulation.

**Acceptance Scenarios**:

1. **Given** the user has enabled core contributions and selected "Graded by Service" mode, **When** they enter two tiers where the first tier's max is less than the second tier's min (e.g., 0-2 years, 5-null years), **Then** an amber warning box appears below the tier editor stating "Gap: service years 2-5 is not covered between tier 1 and 2"
2. **Given** the user has two core tiers where the first tier's max exceeds the second tier's min (e.g., 0-5 years, 3-null years), **When** the tiers render, **Then** an amber warning box appears stating "Overlap: service years 3-5 is covered by both tier 1 and 2"
3. **Given** the user has a single core tier starting at 3 instead of 0, **When** the tier renders, **Then** a warning states "First tier starts at 3 — should start at 0 to cover all employees"
4. **Given** the user has correctly configured contiguous tiers with no gaps or overlaps, **When** the tiers render, **Then** no warning box is displayed
5. **Given** the warning box is displayed, **Then** it includes the reminder text "Tiers use [min, max) intervals — min is inclusive, max is exclusive"

---

### User Story 2 - Points-Based Core Contribution Mode (Priority: P2)

A plan administrator wants to configure employer core contributions that vary by an employee's combined age and service points (points = floor(age) + floor(years of service)), similar to how points-based match contributions already work. They select "Points-Based" from the core contribution type dropdown, configure point-range tiers with corresponding contribution rates, and the system applies the correct rate during simulation.

**Why this priority**: This adds a new capability that mirrors the existing points-based match mode. While valuable for plan designs that use age+service formulas for non-elective contributions, it requires both frontend UI and backend simulation changes, making it higher effort than Story 1.

**Independent Test**: Can be fully tested by selecting "Points-Based" core mode, adding point tiers, running a simulation, and verifying that employees receive core contributions based on their age+service points rather than a flat rate or service-only grading.

**Acceptance Scenarios**:

1. **Given** the user has enabled core contributions, **When** they view the "Contribution Type" dropdown, **Then** they see three options: "Flat Rate (same for all)", "Graded by Service (increases with tenure)", and "Points-Based (varies by age + tenure points)"
2. **Given** the user selects "Points-Based" core mode, **When** the UI updates, **Then** a points tier editor appears with fields for min points, max points, and contribution rate (%), along with a description explaining "Points = FLOOR(age) + FLOOR(years of service)"
3. **Given** the user has configured points-based core tiers, **When** they add a tier, **Then** the new tier's min points defaults to the previous tier's max points (or 0 if first tier), and the max points defaults to null (unbounded)
4. **Given** points-based core tiers are configured with gaps or overlaps, **When** the tiers render, **Then** the same amber validation warnings appear as for other tier-based editors
5. **Given** a valid points-based core configuration is saved and a simulation runs, **When** core contributions are calculated, **Then** each employee's core rate is determined by looking up their floor(age) + floor(tenure) in the configured point tiers

---

### User Story 3 - Points-Based Core in Simulation Engine (Priority: P3)

A plan administrator has configured points-based core contributions via the UI and runs a multi-year simulation. The simulation engine correctly calculates core contribution amounts using the points formula, applying the appropriate tier rate based on each employee's age+service points for that simulation year.

**Why this priority**: This is the backend counterpart to Story 2. Without it, the UI configuration has no effect on simulation results. It depends on Story 2 for the configuration to exist.

**Independent Test**: Can be fully tested by running a simulation with points-based core configuration and querying the resulting contribution events to verify rates match the tier schedule based on employee demographics.

**Acceptance Scenarios**:

1. **Given** a points-based core configuration with tiers [0-50 pts: 1%, 50-75 pts: 2%, 75+: 3%] and an employee aged 40 with 15 years of service (points = 55), **When** the simulation calculates core contributions, **Then** the employee receives a 2% core contribution rate
2. **Given** a multi-year simulation with points-based core, **When** an employee ages and gains tenure over simulation years, **Then** their points increase and they may move to higher core contribution tiers in subsequent years
3. **Given** an employee whose points fall in a gap between configured tiers, **When** core contributions are calculated, **Then** the employee receives the default fallback rate (0%)

---

### Edge Cases

- What happens when all core tiers are deleted? The system should display a prompt to add at least one tier (consistent with match tier editors).
- What happens when the user switches from "Points-Based" to "Flat Rate" and back? The previously entered points tiers should be preserved in form state.
- How does the system handle an employee with null age or null tenure in points calculation? Points calculation should use COALESCE to treat null values as 0.
- What happens when a middle tier has no upper bound (null max)? A warning should appear stating the tier has no upper bound but is not the last tier.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display tier gap/overlap validation warnings for graded-by-service core contribution tiers, using the same validation logic and visual styling as tenure-based match tier warnings
- **FR-002**: System MUST include the "[min, max) intervals" reminder text in core tier validation warnings
- **FR-003**: System MUST offer "Points-Based" as a third core contribution type option alongside "Flat Rate" and "Graded by Service"
- **FR-004**: System MUST display a points tier editor when "Points-Based" core mode is selected, with fields for min points, max points (nullable for unbounded), and contribution rate (%)
- **FR-005**: System MUST display the points formula explanation ("Points = FLOOR(age) + FLOOR(years of service)") in the points-based core tier editor
- **FR-006**: System MUST display tier gap/overlap validation warnings for points-based core tiers
- **FR-007**: System MUST calculate core contribution rates using the points-based tier schedule during simulation when "Points-Based" core mode is configured
- **FR-008**: System MUST persist points-based core tier configuration when saving plan design settings
- **FR-009**: System MUST default new point tiers to start where the previous tier ends (min = previous max, max = null, rate = previous rate + 1)

### Key Entities

- **Points Core Tier**: Represents a single tier in the points-based core contribution schedule. Attributes: minimum points threshold, maximum points threshold (nullable for unbounded last tier), contribution rate as a percentage of compensation.
- **Core Contribution Configuration**: The overall core contribution setup for a plan. Has a type (flat, graded_by_service, or points_based) and the corresponding rate or tier schedule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tier configuration errors (gaps, overlaps, non-zero start) in graded-by-service core tiers produce visible warnings before the user saves
- **SC-002**: Points-based core contribution mode is available in the UI with the same editing experience as points-based match tiers
- **SC-003**: Simulations with points-based core configurations produce correct contribution amounts that match the tier schedule based on employee age+service points
- **SC-004**: All tier-based core editors (graded-by-service and points-based) display consistent validation warnings using the same validation function as match tier editors

## Assumptions

- The `validateMatchTiers()` function in `DCPlanSection.tsx` is generic enough to validate any tier-based configuration that has `min` and `max` fields. This has been confirmed by code review.
- The points formula (floor(age) + floor(years of service)) is identical to the one used for points-based match contributions.
- Points-based core contribution tiers follow the same [min, max) interval convention as all other tier configurations in the system.
- The backend dbt model for core contributions (`int_employer_core_contributions.sql`) will need a new conditional branch for `points_based` mode, following the same pattern as points-based match calculations.
- The Pydantic configuration model can reuse or mirror the existing `PointsMatchTier` structure for points-based core tiers.
