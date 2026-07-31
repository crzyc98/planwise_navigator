# Feature Specification: Social Security Integrated Employer Core Contribution

**Feature Branch**: `126-ss-integrated-core`
**Created**: 2026-07-30
**Status**: Draft
**Upstream issue**: crzyc98/planwise_navigator#514
**Input**: User description: "Add Social Security integrated (permitted disparity) employer core contributions — a `social_security_wage_base` statutory limit by year, plus an integration modifier (`enabled`, `level_mode`, `level_value`, `disparity_rate`) that layers an additional rate on compensation above an integration level, composing with any existing core rate shape (`flat`, `graded_by_service`, `points_based`, `age_banded`). Employer core / non-elective only; match formulas out of scope."

## Overview

The employer core (non-elective) contribution currently applies a single rate to the whole of an employee's recognized compensation, whatever the rate shape. There is no way to model a **Social Security integrated** allocation (permitted disparity, also called an "excess" or "step-rate" formula), in which compensation above an integration level receives an additional rate on top of the base rate.

Integration is one of the most common non-elective designs in the market, because §401(l) makes it a safe harbor for weighting employer money toward higher earners without failing 401(a)(4). Today the engine cannot price this class of plan design, and cannot compare an integrated design against a flat one. The engine also has no notion of the Social Security taxable wage base at all.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Price an integrated core design (Priority: P1)

A consultant modeling a prospect's plan needs to reproduce that plan's actual non-elective formula: "3% of pay, plus 2.7% of pay above the Social Security taxable wage base." They configure the base core rate as they do today, turn integration on, choose the taxable wage base as the integration level, set the disparity rate, and run a scenario. The resulting employer cost reflects the step-rate allocation, and each employee's contribution can be decomposed into its base and disparity halves so the number can be checked line-by-line against the plan document.

**Why this priority**: This is the entire point of the feature. Without it, a large, common class of plan designs cannot be modeled at all. It delivers value on its own with no other story implemented.

**Independent Test**: Configure a scenario with integration enabled and a known base rate, disparity rate, and integration level; run it in an isolated database; confirm that for every employee the contribution equals base rate × recognized compensation plus disparity rate × excess compensation, and that the base and disparity components are individually reported.

**Acceptance Scenarios**:

1. **Given** integration is enabled with the taxable wage base as the integration level, **When** an employee's recognized compensation exceeds the wage base, **Then** they receive the base rate on all recognized compensation plus the disparity rate on the amount above the wage base, and both components are reported separately.
2. **Given** integration is enabled, **When** an employee's recognized compensation is below the integration level, **Then** their excess compensation is zero, their disparity amount is zero, and their total is unchanged from the non-integrated result.
3. **Given** integration is enabled, **When** an employee's recognized compensation equals the integration level exactly, **Then** the disparity amount is zero.
4. **Given** any employee row in the output, **When** the base and disparity components are added, **Then** the sum equals the reported total core contribution amount exactly.

---

### User Story 2 - Integration composes with every core rate shape (Priority: P1)

A plan sponsor runs a graded-by-service core (1% / 2% / 3% by service band) that is *also* integrated. The consultant expects to enable integration without abandoning the service schedule — the schedule still determines each employee's base rate, and integration simply layers disparity on top.

**Why this priority**: Co-equal with Story 1. If integration only worked with a flat base rate it would be a new mutually-exclusive plan type rather than a modifier, and the designs clients actually run (graded + integrated, age-banded + integrated) would still be unmodelable.

**Independent Test**: Run the same integration settings against each supported base rate shape (flat, graded by service, points based, age banded) and confirm the disparity component is computed identically in every case, varying only through the base rate the schedule resolved.

**Acceptance Scenarios**:

1. **Given** a graded-by-service base schedule with integration enabled, **When** two employees in different service bands both earn above the integration level, **Then** each receives their own band's base rate on recognized compensation and the *same* disparity rate on their excess.
2. **Given** an age-banded or points-based base schedule with integration enabled, **When** the scenario runs, **Then** integration applies without any shape-specific behavior or configuration.
3. **Given** integration is disabled, **When** any base rate shape runs, **Then** results are identical to results produced before this feature existed.

---

### User Story 3 - An illegal disparity rate stops the run (Priority: P1)

A consultant experimenting with plan designs sets a disparity rate of 8% on a 3% base. This is not a design decision — it is an allocation the plan could not legally make under §401(l). The run stops at configuration validation with a message naming the applicable limit and the value that violated it, rather than producing a cost figure that corresponds neither to the requested design nor to a legal one.

**Why this priority**: Co-equal. A silently clamped or silently accepted illegal rate produces a number a consultant may take to a client. The failure must be loud and must name the limit.

**Independent Test**: Configure a disparity rate above the permitted maximum, attempt to run, and confirm the run fails before any simulation work with an error naming the applicable limit, the configured rate, and the reason.

**Acceptance Scenarios**:

1. **Given** a base rate of 3% and a disparity rate of 8%, **When** validation runs, **Then** it fails with a message stating the permitted maximum is 3% (the lesser of base rate and disparity factor) and that 8% was configured.
2. **Given** a base rate of 8% and a disparity rate of 6% with the integration level set at the taxable wage base, **When** validation runs, **Then** it fails naming 5.7% as the applicable factor.
3. **Given** an integration level set below the taxable wage base such that a reduced disparity factor applies, **When** a disparity rate above that reduced factor is configured, **Then** validation fails naming the reduced factor, not 5.7%.
4. **Given** a legal configuration, **When** validation runs, **Then** it passes and the run proceeds.

---

### User Story 4 - Configure and review an integrated design in Studio (Priority: P2)

A consultant configures integration in the Studio plan design section — turning it on for whatever contribution type is already selected, choosing the integration level, and setting the disparity rate — then saves, reopens, and sees the design described accurately wherever it is rendered.

**Scoped down 2026-07-30**: the *cost comparison* half of this story was removed. Running a flat scenario and an integrated one and comparing total employer cost is existing functionality; this feature does not build it. What remains is configuring the design and describing it correctly.

**Why this priority**: The engine must be correct first (Stories 1–3, 5). But a design that can only be expressed in YAML is invisible to the people who use Studio, and a design rendered under the wrong description is worse than one rendered under none.

**Independent Test**: Configure integration in Studio, save, reopen, and confirm the settings round-trip; confirm the plan design modal and the scenario summary both name the integration level and disparity rate; confirm an illegal disparity rate is refused with the applicable limit named.

**Acceptance Scenarios**:

1. **Given** any contribution type is selected, **When** the plan design section is opened, **Then** integration can be enabled independently of that type — it is not a fifth contribution type.
2. **Given** integration is configured and saved, **When** the design is reopened, **Then** every integration setting round-trips unchanged.
3. **Given** an integrated design, **When** the plan design summary is displayed, **Then** it states both the base rate shape and the integration terms.
4. **Given** integration is disabled, **When** the plan design summary is displayed, **Then** it is unchanged from today's wording.
5. **Given** a disparity rate above the §401(l) limit is configured in Studio, **When** the simulation starts, **Then** it fails with the applicable limit named — the same refusal the YAML path gets.

---

### User Story 5 - Statutory wage base available by year (Priority: P2)

A multi-year projection needs the correct Social Security taxable wage base for each simulated year, including projected years, and needs to know which years are published figures and which are estimates.

**Why this priority**: A prerequisite for Story 1 in practice, but it is a data addition with independent value (the wage base is a statutory limit the engine will want for other purposes) and is independently verifiable.

**Independent Test**: Query the statutory limits for each simulated year and confirm a wage base is present, that published years match the published figures, and that projected years are flagged as estimated consistently with the other projected limits.

**Acceptance Scenarios**:

1. **Given** a simulation year with a published wage base, **When** the limit is read, **Then** it matches the published figure for that year.
2. **Given** a projected simulation year, **When** the limit is read, **Then** a value is present and the year is flagged as estimated, consistent with how the other projected statutory limits in the same record are flagged.
3. **Given** a database that was materialized before this feature, **When** a run starts, **Then** the stale statutory-limit data is detected and refreshed rather than failing with a missing-field error.

---

### Edge Cases

- **Compensation exactly at the integration level**: excess is zero, disparity is zero. Pinned by test.
- **Compensation above the recognized-compensation cap (401(a)(17))**: the cap applies **before** the split. Compensation is capped first, then the integration level is subtracted from the capped figure. Capping after the split would allocate disparity on compensation the plan is not permitted to recognize. Pinned by test.
- **Mid-year hire**: the integration level is **not** prorated. Plan documents measure plan-year compensation — already partial for a mid-year hire — against the full-year taxable wage base. A mid-year hire whose prorated compensation lands below the wage base therefore receives no disparity. This is correct but counterintuitive, so it is pinned by an explicit test rather than left to a comment.
- **Integration level above the taxable wage base**: not permitted under §401(l); rejected at validation.
- **Integration enabled with a zero disparity rate**: produces results identical to integration disabled. Allowed, not an error.
- **Ineligible employees and terminations excluded by eligibility rules**: receive zero total, therefore zero base and zero disparity. Integration does not alter who is eligible.
- **Integration level exceeds the recognized-compensation cap for a given year**: no employee can have excess compensation; every disparity amount is zero. Not an error.
- **Base rate of zero with a non-zero disparity rate**: rejected at validation, because permitted disparity may not exceed the base rate.

## Requirements *(mandatory)*

### Functional Requirements

**Statutory data**

- **FR-001**: The system MUST make the Social Security taxable wage base available as a year-indexed statutory limit alongside the existing year-indexed limits (recognized-compensation cap, HCE threshold, and so on).
- **FR-002**: Published wage base figures MUST be used where published (2024 = $168,600; 2025 = $176,100), and the 2026 figure MUST be verified against the official Social Security Administration announcement before merge rather than taken from the feature request or this spec.
- **FR-003**: Projected years MUST carry a wage base value produced by the same projection convention already used for the other statutory limits in records already flagged as estimated, and MUST remain flagged as estimated.
- **FR-004**: A database materialized before this feature MUST recover automatically when a run begins — the stale statutory-limit data is detected and refreshed — rather than failing with a missing-field error.

**Integration as a modifier**

- **FR-005**: Integration MUST be expressed as a modifier on top of whatever base rate the existing core rate shape resolved, NOT as a new core contribution status value. A new status would make integration mutually exclusive with the rate schedule and force a combinatorial explosion of statuses.
- **FR-006**: The system MUST support these integration settings under the employer core contribution configuration:
  - an **enabled** switch, defaulting to off;
  - a **level mode** with values *taxable wage base*, *percent of taxable wage base*, and *fixed dollar amount*;
  - a **level value** used by the latter two modes (a percentage, or a dollar amount);
  - a **disparity rate**, the additional rate applied to excess compensation.
- **FR-007**: With integration disabled, results MUST be identical to results produced before this feature, for every core rate shape. Byte-identical output is the acceptance bar.
- **FR-008**: The employer core contribution amount MUST be computed as: recognized compensation = the lesser of the employee's prorated plan-year compensation and the recognized-compensation cap; excess compensation = recognized compensation minus the integration level, floored at zero; total = base rate × recognized compensation + disparity rate × excess compensation.
- **FR-009**: The recognized-compensation cap MUST be applied **before** the integration level is subtracted.
- **FR-010**: The integration level MUST NOT be prorated for mid-year hires or mid-year terminations; the full-year level is compared against the already-prorated plan-year compensation.
- **FR-011**: Integration MUST apply uniformly across all core rate shapes with no shape-specific branching in the integration logic. The only thing a shape contributes is the base rate it resolved.

**Legality enforcement**

- **FR-012**: The system MUST reject, at configuration validation and before any simulation work begins, a disparity rate exceeding the maximum permitted under §401(l): the lesser of the base rate and the applicable disparity factor.
- **FR-013**: The applicable disparity factor MUST depend on the integration level relative to the taxable wage base, per the §401(l) safe harbor:

  | Integration level | Maximum disparity factor |
  | --- | --- |
  | Equal to the taxable wage base | 5.7% |
  | Above 80% but below 100% of the taxable wage base | 5.4% |
  | Above 20% but at or below 80% of the taxable wage base | 4.3% |
  | At or below the greater of 20% of the taxable wage base or $10,000 | 5.7% |
  | Above the taxable wage base | Not permitted |

- **FR-014**: The validation failure message MUST name the applicable limit, the configured disparity rate, and which constraint bound (base rate vs. disparity factor), so the user can correct the configuration without consulting the regulation.
- **FR-015**: The system MUST NOT silently clamp an illegal disparity rate. A clamped result corresponds neither to the requested design nor to a legal one, which is worse than either failing or honoring the request.
- **FR-016**: Where the base rate varies by employee (service-graded, age-banded, points-based), validation MUST evaluate the base-rate constraint against the schedule such that no employee can receive a disparity exceeding their own base rate.

**Audit output**

- **FR-017**: The contribution output MUST report, per employee per year, following the existing "value used / whether it bound" pattern of the recognized-compensation cap:
  - the **integration level applied**;
  - the **excess compensation**;
  - the **base component** and the **disparity component** of the contribution, reported separately;
  - the **taxable wage base** for the year.
- **FR-018**: For every output row, the base component plus the disparity component MUST equal the total employer core contribution amount.

**Reporting surface**

- **FR-019**: Integration MUST be configurable through the plan design interface, for every contribution type, and MUST reach the engine from that interface — a setting that validates but never reaches the calculation is indistinguishable from having no setting at all.
- **FR-020**: Wherever a plan design is rendered in prose, an integrated design MUST be described as integrated, naming the integration level and disparity rate. Rendering it as a plain flat or graded design is a materially wrong statement of the plan — and because the comparison surface labels both scenarios from the same function, a flat and an integrated scenario would otherwise appear under identical labels while showing different costs.

### Out of Scope

- **Employer match formulas.** Integrated match is a separate design with separate testing rules; the match calculation is untouched by this feature.
- **Non-safe-harbor integration** (general-test-based disparity, two-tier "offset" formulas). Only the §401(l) excess-allocation safe harbor is modeled.
- **Cumulative permitted disparity limits** across multiple plans or across an employee's career. Single-plan, single-year enforcement only.
- **Using the taxable wage base for any purpose other than the core contribution integration level** (for example FICA modeling or offset formulas).

### Key Entities

- **Statutory year limits**: the year-indexed record of legal limits. Gains a *Social Security taxable wage base* per year, alongside the existing recognized-compensation cap and HCE threshold, retaining the existing per-year estimated flag.
- **Employer core contribution configuration**: gains an *integration* group — enabled, level mode, level value, disparity rate — which sits beside, and does not replace, the existing status and rate schedules.
- **Employee core contribution record**: gains *integration level applied*, *excess compensation*, *base component*, *disparity component*, and *taxable wage base*, alongside the existing recognized compensation, cap, cap-applied flag, and total.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A consultant can reproduce a real integrated plan formula ("X% of pay plus Y% above the wage base") end to end and see the cost, without editing any calculation logic.
- **SC-002**: With integration disabled, output is byte-identical to pre-feature output across all four core rate shapes, verified by comparing full scenario results rather than spot checks.
- **SC-003**: Integration produces correct results under all four core rate shapes with no shape-specific integration logic, verified by running the same integration settings against each.
- **SC-004**: For 100% of output rows, base component + disparity component = total contribution amount.
- **SC-005**: 100% of employees whose recognized compensation is at or below the integration level receive zero disparity.
- **SC-006**: Every disparity-factor boundary in the FR-013 table is covered by a validation test, and every illegal configuration fails before any simulation work with the applicable limit named in the message.
- **SC-007**: The three ordering decisions — cap before split, integration level unprorated, illegal rate fails loudly — are each pinned by an explicit named test, so a future change that reverses one fails immediately.
- **SC-008**: The difference in total employer core cost between an otherwise-identical flat scenario and integrated scenario equals the integrated scenario's total disparity component exactly.
- **SC-009**: An integrated design is never described in the interface using wording that omits the integration; specifically, a flat scenario and an integrated scenario never render under identical plan-summary text.

## Relationship to issue #514

Issue #514's acceptance criteria are met in full, including *"Studio: integration is configurable and `PlanDesignModal` / `derivePlanSummary` describe it."*

The only scope reduction is the **cost comparison** itself: running two scenarios and comparing employer cost is existing functionality that this feature reuses rather than rebuilds. The issue's verification recipe (`planalign batch --scenarios flat_core integrated_core`, then compare) works as written against the shipped feature.

## Assumptions

1. **2026 wage base requires verification.** The feature request supplies only 2024 and 2025. The 2026 figure will be taken from the official SSA announcement at implementation time, not from any figure quoted in this spec or the issue.
2. **Projection convention for 2027+** follows whatever ramp the existing projected statutory limits in the same records already use; no new projection methodology is introduced.
3. **Integration is off by default**, so every existing configuration and scenario is unaffected without change.
4. **Integration does not affect eligibility.** Who receives a core contribution is determined entirely by the existing eligibility rules; integration only changes how much an eligible employee receives.
5. **The disparity rate is a single flat rate** applied to all excess compensation, not itself a schedule. A per-band disparity schedule is not requested and is not modeled.
6. **Base-rate constraint under varying schedules**: with a varying base rate, validation applies the constraint against the schedule's lowest rate, so no employee can receive a disparity exceeding their own base rate. This is the conservative reading and satisfies FR-016.
7. **Adding a field to the statutory limits data is a known path**, previously exercised when the recognized-compensation cap was added; existing machinery for detecting and refreshing stale materialized limit data is expected to cover it, subject to confirming that any fixed field-count check still behaves.
8. **Validation is testable without a database.** The §401(l) legality checks depend only on configuration values and the wage base for the year, so they can be tested independently of any simulation run.

## Dependencies

- The age-banded core rate shape has already landed, so integration must compose with it from day one.
- The recognized-compensation cap behavior and its audit fields already exist and set the pattern the new audit fields follow.
- Verification requires isolated per-scenario databases per the project's isolated-database rule; the shared development database is never built into for this work.
