# Feature Specification: Correct Employer Contribution Eligibility Service Credit

**Feature Branch**: `136-eligibility-tenure-offset`
**Created**: 2026-08-11
**Status**: Draft
**Input**: GitHub issue [#559](https://github.com/crzyc98/planwise_navigator/issues/559) — "Employer core/match tenure waiting period is off by one year after the start year (2-year wait behaves as 1-year)"

## Problem Statement

The employer contribution eligibility gate credits every employee with one more year of service than they have actually earned, in every simulation year after the first. As a result, a plan design with a service waiting period longer than one year is enforced only in the opening year of a projection and is silently satisfied a year early thereafter.

A modeled 2-year waiting period therefore produces the same multi-year cost as a 1-year waiting period. Analysts comparing plan designs see no cost difference between the two, and the cost of the longer waiting period is overstated.

**Observed evidence** (three scenarios, Census Large workspace, differing only in the core waiting period):

| Scenario | 2025 | 2026 | 2027 | 2028 | 2029 |
|----------|------|------|------|------|------|
| Baseline (no wait) | $261.91M | $279.42M | $301.31M | $324.85M | $348.64M |
| 1-Year Wait | $243.34M | $254.29M | $275.51M | $297.48M | $319.83M |
| 2-Year Wait | $207.46M | $254.29M | $275.51M | $297.48M | $319.83M |

Years 2026–2029 are identical to the cent between the 1-year and 2-year designs; only the opening year diverges. In 2029 alone, 8,691 employees with one completed year of service received a core contribution under a 2-year requirement — **$47.86M of misattributed employer cost in a single year**. Across the projection, 60,903 of 74,842 employee-year records carried an inflated service credit.

The waiting-period setting itself is carried correctly through configuration; the defect is purely in how service is counted at the point of the eligibility decision.

## Scope

**In scope**

- The service-credit basis used to decide employer **core** (non-elective) contribution eligibility.
- The service-credit basis used to decide employer **match** eligibility, which is governed by the same calculation and is affected identically.
- Permanent automated checks that prevent the service basis from silently drifting again.

**Out of scope**

- Any change to how waiting periods are configured, or to the Studio interface for setting them.
- Any change to contribution formulas, rates, proration, or vesting.
- Retroactive correction of previously saved scenario results. Existing saved runs remain as they are; re-running a scenario produces corrected figures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Multi-year waiting periods produce distinct costs (Priority: P1)

A plan analyst models the same population under a 1-year and a 2-year non-elective waiting period and compares projected employer cost across a five-year horizon. They expect the longer waiting period to defer more employees out of eligibility in every year, producing a visibly lower cost curve throughout — not just in the opening year.

**Why this priority**: This is the defect as experienced by the user and the reason the projections are currently wrong. Delivering only this restores correct cost modeling for every affected plan design.

**Independent Test**: Run two multi-year scenarios differing only in the core waiting period (1 year vs 2 years) in isolated databases, and compare the employer cost by year. Fully testable without any other story.

**Acceptance Scenarios**:

1. **Given** two scenarios identical except for a core waiting period of 1 year versus 2 years, **When** both are run across five simulation years, **Then** the employer core cost differs between them in every year of the projection, not only the first.
2. **Given** a scenario with a 2-year core waiting period, **When** the projection completes, **Then** no employee with fewer than 2 completed years of service is treated as eligible for a core contribution in any year.
3. **Given** a scenario with a 3-year core waiting period, **When** the projection completes, **Then** the eligible population is strictly smaller than under a 2-year waiting period in every year of the projection.
4. **Given** a scenario with a 1-year core waiting period, **When** the projection completes, **Then** results are unchanged or the change is fully explained by employees who genuinely had less than one year of service.

---

### User Story 2 — Match waiting periods are corrected alongside core (Priority: P1)

An analyst models an employer match with a multi-year service requirement. They expect the match waiting period to be honored in every projection year on the same service basis as the core waiting period.

**Why this priority**: Match eligibility is decided by the same calculation, so it carries the identical defect. Correcting core while leaving match wrong would ship a known error and leave the two gates on different service bases.

**Independent Test**: Run a scenario with match eligibility enforcement enabled and a 2-year match service requirement; verify no employee below that service level receives a match in any year.

**Acceptance Scenarios**:

1. **Given** match eligibility enforcement is enabled with a 2-year service requirement, **When** a multi-year projection runs, **Then** no employee with fewer than 2 completed years of service receives an employer match in any year.
2. **Given** identical service requirements are configured for core and match, **When** a projection runs, **Then** both gates classify the same employee-years as service-qualified.

---

### User Story 3 — The service basis cannot silently drift again (Priority: P2)

A developer changes a model in the workforce or contribution pipeline. They expect an automated check to fail immediately if the service figure used for eligibility decisions ever diverges from the workforce record's authoritative service figure.

**Why this priority**: The absence of exactly this check is why the defect survived from its introduction to production use across client-facing comparisons. It does not fix the defect on its own, so it ranks below P1, but it is what makes the fix durable.

**Independent Test**: Deliberately reintroduce an offset in the eligibility service figure and confirm the automated check fails.

**Acceptance Scenarios**:

1. **Given** the pipeline is built for any simulation year, **When** the automated data checks run, **Then** a check verifies that the service figure used for eligibility matches the workforce record's service figure for every employee, and fails if any record diverges.
2. **Given** a waiting period of any length is configured, **When** the automated checks run, **Then** a check verifies no employee below the configured service requirement is marked eligible, and fails if any is.

---

### Edge Cases

- **Employees terminating mid-year.** The workforce record recomputes service for a terminating employee as of the termination date, which can differ from a simple year-over-year increment. In the observed run, 689 experienced terminations carried a workforce service figure of 0 while the eligibility gate credited them with 2 — a two-year divergence, wider than the general one-year offset. The corrected basis must state explicitly which figure governs a terminating employee, and treat that consistently.
- **Employees hired during the simulation year.** New hires have no prior-year record. These are handled correctly today and must remain so; the correction must not begin including or excluding first-year hires as a side effect.
- **The opening simulation year.** The opening year is currently correct because no prior-year record exists. The correction must leave opening-year results unchanged — this is the strongest available regression signal.
- **Rehires and employees with a broken service record.** An employee with a prior-year record but a reset service figure must not accumulate credit for years not actually worked.
- **A zero-year (no) waiting period.** With no service requirement, eligibility must be unaffected by this change in every year.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The employer core eligibility decision MUST evaluate the configured service requirement against the employee's completed years of service as recorded on the authoritative workforce record for the year being decided.
- **FR-002**: The employer match eligibility decision MUST use the same service basis as FR-001.
- **FR-003**: An employee whose completed years of service are below the configured requirement MUST NOT be treated as eligible, in any simulation year, unless an explicitly configured exception (such as an allowance for first-year hires) applies.
- **FR-004**: The service figure reported on eligibility records for audit MUST equal the service figure on the corresponding workforce record for the same employee and year, so that eligibility decisions can be independently reconciled.
- **FR-005**: The system MUST enforce the service requirement identically in the opening simulation year and in every subsequent year; no year may apply a different service basis.
- **FR-006**: The system MUST apply a single, documented service basis for terminating employees across both the eligibility gate and any service-graded contribution rate, so that one employee is not simultaneously judged under two different service figures.
- **FR-007**: An automated check MUST fail the build when the eligibility service figure diverges from the workforce record's service figure for any employee-year.
- **FR-008**: An automated regression check MUST verify, across a multi-year projection and for waiting periods of at least 2 and 3 years, that no employee below the requirement is marked eligible.
- **FR-009**: Existing configurations MUST continue to work unchanged; no new or renamed configuration setting is introduced by this correction.

### Key Entities

- **Employee service record**: The authoritative per-employee, per-year record of completed years of service, maintained by the workforce state pipeline. This is the single source of truth the eligibility decision must consult.
- **Eligibility determination**: The per-employee, per-year decision on whether an employee qualifies for employer core and match contributions, together with the service figure and reason code recorded for audit.
- **Waiting period configuration**: The plan-design setting expressing minimum years of service required for core and (independently) for match contributions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Re-running the three reported scenarios produces employer cost figures that differ between the 1-year and 2-year waiting periods in **all five** projection years, where four of five years are currently identical.
- **SC-002**: Zero employees below the configured service requirement are credited with an employer core or match contribution, across every year of a multi-year projection, for waiting periods of 2 and 3 years.
- **SC-003**: The service figure recorded on every eligibility record matches the corresponding workforce record for 100% of employee-years — currently 60,903 of 74,842 records diverge in a single year.
- **SC-004**: Opening-year results for all three reported scenarios are unchanged, confirming the correction is confined to the defective years.
- **SC-005**: A projection with no service requirement produces results identical to before the correction, confirming no unintended change to the most common configuration.
- **SC-006**: Deliberately reintroducing the service offset causes an automated check to fail, demonstrating the defect can no longer reach production silently.

## Assumptions

- **Correct intent of a waiting period**: "N years of service" means an employee qualifies once they have completed N full years, evaluated against the year-end workforce record — the basis the opening year already uses and the one that produced the correct opening-year figures.
- **The opening year is correct today** and is therefore a valid regression baseline. This follows from the opening year having no prior-year record to consult.
- **Direction of the cost correction**: costs for waiting periods of 2+ years will fall in the affected years, since employees are currently qualifying early. Cost increases would indicate a further problem.
- **No result migration**: previously saved scenario results are not retroactively corrected. Analysts must re-run any scenario with a 2+ year waiting period to obtain valid figures.
- **Blast radius is bounded to 2+ year waiting periods**: a 1-year requirement is largely unaffected in practice, because an employee with at least one true year of service also clears the bar under the inflated figure. This is why the defect went unnoticed. It must be confirmed rather than presumed.
- **Communication**: because client-facing plan-design comparisons involving 2+ year waiting periods are wrong today, affected prior analyses should be identified and re-run. Determining which client deliverables are affected is a business follow-up outside this specification.

## Clarifications Resolved

- **CL-001** *(resolved 2026-08-11)*: Align service-graded and points-based rate selection with the eligibility basis. FR-006 already requires one documented service basis for gating and rate selection; limiting the correction to the gate would leave the specification internally inconsistent and retain a known audit mismatch.

- **CL-002** *(resolved 2026-08-11)*: Use service measured through the termination date, exactly as recorded by the authoritative workforce record. Existing termination exception settings may allow a terminated employee through a status gate, but they do not change completed service or permit year-end credit for time not worked.
