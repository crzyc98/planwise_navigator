# Feature Specification: Configurable New-Hire Eligibility Rate + Optional Per-Employee Census Eligibility

**Feature Branch**: `103-new-hire-eligibility`
**Created**: 2026-06-29
**Status**: Draft
**Input**: GitHub issue [#357](https://github.com/crzyc98/planwise_navigator/issues/357) — "feat: Configurable new-hire eligibility rate + optional per-employee census eligibility" (supersedes #283)

## Clarifications

### Session 2026-06-29

- Q: When the census eligibility column contains an invalid value (not a recognized eligible/ineligible/empty state), how should the system behave? → A: Accept the import, surface a warning, and treat the invalid value as unspecified (eligible by default); the run proceeds.
- Q: When "match census eligibility" is enabled, the census-observed ineligible rate is computed over which denominator? → A: All census employees (total headcount), with blank/unspecified values counted as eligible.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Model a share of new hires as plan-ineligible (Priority: P1)

A benefits analyst wants to model the realistic situation where a portion of newly hired employees are not eligible for the DC (retirement savings) plan during the modeled window — for example, because of a job class, a probationary status, or a population the sponsor intentionally excludes. The analyst sets a single dial expressing "what percentage of new hires are not eligible," runs a multi-year simulation, and sees those employees never enroll, never contribute, and never receive employer match in the years they would otherwise have become eligible.

**Why this priority**: This is the core value of the feature and the most common sponsor need. It is fully self-contained: a single analyst-facing input produces a measurable change in simulation outputs (participation, contributions, match, and therefore total plan cost). The other stories build on the same per-employee gate this story establishes.

**Independent Test**: Set the new-hire ineligible percentage to a non-zero value (e.g., 10%) on an isolated multi-year simulation and confirm that approximately that share of each year's new-hire cohort produces zero enrollment, contribution, and match activity, while everyone else behaves exactly as before.

**Acceptance Scenarios**:

1. **Given** the new-hire ineligible percentage is 0% (default) and no census eligibility column is present, **When** a simulation is run, **Then** results are byte-for-byte identical to results produced before this feature existed (regression-safe).
2. **Given** the new-hire ineligible percentage is set to 10%, **When** a multi-year simulation is run, **Then** approximately 10% of each year's new-hire cohort never enroll, never contribute, and never receive employer match in the year they would otherwise have become eligible.
3. **Given** an employee has been deterministically marked ineligible, **When** the same scenario is re-run with the same random seed, **Then** the exact same set of employees is marked ineligible (reproducibility).
4. **Given** a new hire is marked ineligible, **When** the simulation generates plan events, **Then** no plan-eligibility event is recorded for that employee for the suppressed period, and the suppression reason is recorded for audit.

---

### User Story 2 - Carry explicit eligibility from the census file (Priority: P2)

An analyst has a census (the input population file) where certain existing employees are known to be plan-ineligible. The analyst adds an optional eligibility column to the census marking specific employees as eligible or ineligible. Employees flagged ineligible are excluded from participation regardless of the new-hire dial; employees with no value behave as eligible by default. Census files that do not include the column continue to work unchanged.

**Why this priority**: This gives analysts precise, per-employee control over the existing population, complementing the statistical new-hire dial. It is lower priority than P1 because it requires preparing census data, but it reuses the same per-employee gate, so it is a thin extension once P1 exists.

**Independent Test**: Provide a census that includes the eligibility column with some employees marked ineligible, run a simulation, and confirm those specific employees never enroll/contribute/receive match while all other employees are unaffected; then provide a census without the column and confirm behavior is unchanged.

**Acceptance Scenarios**:

1. **Given** a census employee is explicitly marked ineligible, **When** a simulation is run, **Then** that employee never enrolls, contributes, or receives employer match across all modeled years.
2. **Given** a census employee is explicitly marked eligible, **When** a simulation is run, **Then** existing timing/age/service eligibility logic still applies on top (the override does not force participation earlier than the normal rules allow).
3. **Given** a census employee has no value in the eligibility column (or the column is absent entirely), **When** a simulation is run, **Then** that employee is treated as eligible by default.
4. **Given** both an explicit census eligibility value and the new-hire dial could apply to the same employee, **When** eligibility is resolved, **Then** the explicit census value takes precedence for census employees and the dial governs only new hires.

---

### User Story 3 - Calibrate the new-hire dial to the census-observed rate (Priority: P3)

Instead of choosing a percentage by hand, an analyst wants synthetic new hires to statistically resemble the real population. The analyst enables a "match census eligibility" option so the effective new-hire ineligible rate defaults to the ineligible share observed in the census, rather than the literal dial value.

**Why this priority**: This is a convenience/realism refinement on top of P1 and P2. It is valuable but optional, and only meaningful once both the dial (P1) and the census column (P2) exist.

**Independent Test**: Provide a census with a known ineligible share, enable "match census eligibility," run a simulation, and confirm the new-hire ineligible share tracks the census-observed rate rather than the dial's literal value.

**Acceptance Scenarios**:

1. **Given** "match census eligibility" is enabled and the census carries an eligibility column with a known ineligible share, **When** a simulation is run, **Then** the new-hire ineligible share tracks that census-observed rate.
2. **Given** "match census eligibility" is disabled (default), **When** a simulation is run, **Then** the new-hire ineligible share uses the dial's literal value.
3. **Given** "match census eligibility" is enabled but the census does not carry the eligibility column, **When** a simulation is run, **Then** the system falls back to the dial's literal value (no observed rate to match).

---

### Edge Cases

- **Percentage boundaries**: A dial value of 0% leaves everyone eligible; a value of 100% marks every new hire ineligible. Values outside the 0–100% range are rejected with a clear validation message.
- **Eligible override does not accelerate eligibility**: Marking an employee "eligible" never makes them participate earlier than the normal age/service/timing rules permit; it only declines to suppress them. (Immediate-eligibility waivers that accelerate a new hire past the waiting period are explicitly out of scope.)
- **Multi-year correctness**: An employee marked ineligible stays consistently classified across all simulation years; the classification does not drift in year 2+ when state is carried forward from prior-year snapshots.
- **Already-enrolled employees**: The feature suppresses *future* participation for ineligible employees; it does not retroactively unwind contributions already recorded in a prior year for an employee who was eligible then.
- **Census column present but empty/all-null**: Treated identically to the column being absent — everyone defaults to eligible, and census-matching computes a 0% observed rate (0 ineligible ÷ total headcount).
- **Invalid census value**: An unrecognized value does not fail the import; it is surfaced as a warning and treated as unspecified (eligible by default).
- **Mixed population**: Census employees and synthetic new hires coexist; each is governed by its own rule (explicit census value vs. dial) with no cross-contamination.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an analyst-facing dial expressing the percentage of new hires that are not plan-eligible, accepting values from 0% to 100% inclusive, defaulting to 0%.
- **FR-002**: The system MUST mark a deterministic, reproducible subset of each year's new-hire cohort as ineligible such that the marked share matches the configured percentage and the same employees are selected on re-runs with the same seed.
- **FR-003**: The system MUST suppress all DC-plan participation (auto-enrollment, voluntary enrollment, contributions, and employer match) for any employee resolved as ineligible, for the period they are ineligible.
- **FR-004**: The system MUST support an optional per-employee eligibility value carried in the census input that can mark a specific employee as eligible or ineligible, with no value meaning "use default (eligible)."
- **FR-005**: The system MUST treat a census that omits the eligibility column as fully valid, with all employees defaulting to eligible.
- **FR-006**: The system MUST apply the following precedence when resolving eligibility: an explicit census eligibility value wins for census employees; the new-hire dial governs new hires.
- **FR-007**: The system MUST continue to apply all existing age, service, and timing eligibility rules on top of the override — an employee resolved as "eligible" still becomes a participant only when the normal rules allow.
- **FR-008**: The system MUST provide an optional "match census eligibility" setting that, when enabled and the census carries the eligibility column, sets the effective new-hire ineligible rate to the ineligible share observed in the census instead of the dial's literal value; when disabled or no column is present, the dial's literal value is used. The observed share MUST be computed over total census headcount (ineligible count ÷ total census employees), with blank/unspecified values counted as eligible.
- **FR-009**: The system MUST record, for audit, that an employee's plan eligibility was suppressed by an override (including a reason/source distinguishing it from normal ineligibility) and MUST NOT emit a plan-eligibility event for the suppressed period.
- **FR-010**: The system MUST classify each employee's eligibility consistently across all simulation years, including year 2 and beyond where workforce state is carried forward.
- **FR-011**: The system MUST validate the new-hire ineligible percentage and reject out-of-range values with a clear, actionable message.
- **FR-012**: The system MUST validate the census eligibility column's values (only the accepted eligible/ineligible/empty states). An unrecognized value MUST NOT fail the import; instead the system MUST surface a warning identifying the affected value(s) and treat each invalid value as unspecified (eligible by default), allowing the run to proceed.
- **FR-013**: When the default configuration is used (0% dial, no census column, census-matching off), the system MUST produce results identical to those produced before this feature existed.
- **FR-014**: The analyst MUST be able to configure both the dial and the census-matching option through the plan-configuration surface used to set up a scenario, with helper text estimating the approximate number of affected employees per year.

### Key Entities *(include if feature involves data)*

- **Employee eligibility override**: A per-employee classification with three states — eligible, ineligible, or unspecified (default eligible). For existing census employees it is a static attribute sourced from the census; for synthetic new hires it is derived deterministically from the dial.
- **New-hire ineligible rate (dial)**: A scenario-level percentage (0–100%, default 0%) expressing the share of each year's new-hire cohort to mark ineligible.
- **Census-matching setting**: A scenario-level on/off choice that, when on, replaces the dial's literal value with the ineligible share observed in the census.
- **Eligibility event / audit annotation**: The record of an employee becoming (or being suppressed from becoming) plan-eligible, including a reason/source that identifies override-driven ineligibility for transparency.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the default configuration (0% dial, no census column, census-matching off), a multi-year simulation produces results identical to the pre-feature baseline (zero differences in enrollment, contribution, and match outputs).
- **SC-002**: With the new-hire ineligible percentage set to 10%, the share of each year's new-hire cohort with zero enrollment, contribution, and match activity is within an acceptable tolerance of 10% (e.g., ±1 percentage point on a representative cohort), and the result is reproducible across identical re-runs.
- **SC-003**: 100% of census employees explicitly marked ineligible show zero enrollment, contribution, and match events across all modeled years.
- **SC-004**: With census-matching enabled, the realized new-hire ineligible share tracks the census-observed ineligible rate (ineligible count ÷ total census headcount) within an acceptable tolerance, and falls back to the dial value when no census column is present.
- **SC-005**: An analyst can configure both the dial and the census-matching option and run a scenario without editing files by hand, seeing an estimate of affected employees before running.
- **SC-006**: The feature is validated on an isolated multi-year simulation (not the shared development database), per the project's isolated-database rule.

## Assumptions

- The "modeled window" for ineligibility means the simulation horizon; an employee marked ineligible is suppressed for the duration they remain ineligible within that horizon. The feature does not model a later transition from ineligible to eligible within the window unless normal eligibility rules already provide it.
- The deterministic selection of ineligible new hires is keyed on a stable employee identifier combined with the simulation context so that re-runs with the same seed reproduce the same selection exactly.
- "Eligible" overrides are non-accelerating: they never grant participation earlier than the normal age/service/timing rules. Accelerating waivers (immediate eligibility based on prior experience) are explicitly out of scope, as called out in the source issue.
- The census eligibility column is optional and follows the same absent-column-defaults-to-default-value pattern already used for the per-employee auto-escalation opt-out flag (#316).
- Suppressing participation cascades correctly: an employee who never enrolls produces no contributions and therefore no employer match, so no separate contribution/match suppression logic is required.
- Studio UI controls for the dial and census-matching toggle are desirable and described here, but may be delivered as a fast follow-up; the core value (configurable behavior + measurable output change) does not depend on the UI being delivered in the same increment.

## Out of Scope

- Immediate-eligibility waivers that accelerate a new hire past the normal waiting period (the symmetric "eligible = TRUE accelerates participation" case).
- Modeling explicit transitions of an employee from ineligible to eligible partway through the horizon beyond what existing eligibility rules already produce.
- Retroactively unwinding contributions or match already recorded in a prior year for an employee who was eligible at that time.

## Related

- Pattern precedent: per-employee auto-escalation opt-out flag (#316).
- Eligibility event infrastructure: Feature 086 plan-eligibility events.
- Supersedes #283 (original waiver framing against a pre–Feature-086 architecture).
