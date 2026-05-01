# Feature Specification: Match Formula as Enrollment Deferral Rate Magnet

**Feature Branch**: `084-fix-match-magnet`
**Created**: 2026-04-30
**Status**: Draft
**Input**: User description: "Fix: Match Formula as Enrollment Deferral Rate Magnet"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Realistic Match-Driven Enrollment Clustering (Priority: P1)

An actuary configures a DC plan with a generous employer match (e.g., 200% match on the first 5% of pay) and runs a workforce simulation. Today, the simulation assigns deferral rates using only employee demographics, ignoring the match formula entirely. The actuary expects simulated employees to behave like real employees: a meaningful share will recognize the "free money" opportunity and elect to contribute at least enough to capture the full match.

**Why this priority**: This is the core behavioral realism gap. Without it, simulated contribution rates are systematically too low for plans with strong match formulas, producing inaccurate plan cost projections and inaccurate average deferral statistics.

**Independent Test**: Configure any match formula, run a single-year simulation, query the enrollment deferral rate distribution, and verify that a measurable fraction of new enrollees elect the match-maximizing rate.

**Acceptance Scenarios**:

1. **Given** a plan with a match formula that fully vests at 5% deferral, **When** employees enroll (both proactively and through voluntary enrollment), **Then** approximately 40–50% of employees whose demographic-based rate was below 5% elect exactly 5%, compared to near 0% without a match.
2. **Given** a plan with a match formula that fully vests at 3% deferral, **When** employees enroll, **Then** the match-maximizing rate (3%) shows a measurable concentration in the deferral distribution.
3. **Given** a plan with no match formula configured, **When** employees enroll, **Then** the deferral rate distribution is unchanged from the demographic-only baseline (no spurious clustering).

---

### User Story 2 - Match Magnet Works Across All Match Formula Types (Priority: P2)

A benefits analyst switches between different match formula structures (flat match, tiered match, safe harbor) and expects the magnet behavior to always snap to the correct threshold derived from the active formula — not a hardcoded value.

**Why this priority**: The current broken implementation hardcodes thresholds (3%, 5%, 6%) based on formula name, so a custom "200% match up to 7%" formula would use the wrong threshold. This story ensures correctness for any configured formula.

**Independent Test**: Configure a non-standard match formula (e.g., full match up to 7%), run the simulation, and verify that clustering occurs at 7%, not at a hardcoded 3%, 5%, or 6%.

**Acceptance Scenarios**:

1. **Given** a tiered match with the highest employee contribution threshold at 7%, **When** employees enroll, **Then** the clustering target is 7%, not a hardcoded value.
2. **Given** a simple flat match capped at 4%, **When** employees enroll, **Then** the clustering target is 4%.
3. **Given** the match formula changes between simulation scenarios (scenario A vs. scenario B), **When** each scenario is simulated independently, **Then** each simulation clusters at its own formula's threshold.

---

### User Story 3 - Configurable Magnet Strength (Priority: P3)

A plan modeler wants to tune how strongly the match formula attracts enrollees toward the threshold — for example, representing a workforce with low financial literacy (weak magnet, lower percentage) versus a highly engaged workforce (strong magnet, higher percentage).

**Why this priority**: A single hardcoded magnet probability cannot represent the range of real-world plan populations. Configurability lets analysts model different workforce awareness levels without changing plan design parameters.

**Independent Test**: Set the magnet probability to 0% (disabled), verify no clustering; set it to 80%, verify roughly 80% of eligible enrollees cluster at the match threshold.

**Acceptance Scenarios**:

1. **Given** the magnet probability is set to 0%, **When** employees enroll, **Then** zero clustering occurs at the match threshold (pure demographic rates).
2. **Given** the magnet probability is set to a custom value (e.g., 70%), **When** employees enroll, **Then** approximately 70% of employees with sub-threshold demographic rates elect the match-maximizing rate.
3. **Given** the magnet is enabled with default probability, **When** an employee's demographic rate already meets or exceeds the match threshold, **Then** their rate is not affected by the magnet (no downward pressure).

---

### Edge Cases

- What happens when the match formula has no defined maximum employee contribution threshold (e.g., an open-ended formula)? — The magnet should not apply; rates fall back to demographic baseline.
- What happens when a plan has a match configured but match is disabled in the scenario? — The magnet should not apply.
- What happens when an employee's demographic-based rate is already at or above the match threshold? — No change; the magnet only pulls rates upward, never downward.
- What happens when the match-maximizing rate exceeds the 10% enrollment deferral ceiling? — The capped rate (10%) is used; no employee is pushed above the ceiling.
- What happens for non-deferral-based match formulas (e.g., tenure-based match where the threshold varies per employee)? — The magnet applies only to deferral-based formulas; other formula types are unaffected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The simulation MUST apply a match-threshold attraction effect to employees enrolling during both the proactive enrollment window and the standard voluntary enrollment process.
- **FR-002**: The match-maximizing deferral rate MUST be derived from the actual configured match formula tiers, not from hardcoded values tied to formula names.
- **FR-003**: The magnet MUST only pull deferral rates upward — employees whose demographic-based rate already meets or exceeds the match threshold MUST NOT have their rate modified.
- **FR-004**: The fraction of eligible employees attracted to the match threshold MUST be configurable via a single probability parameter, with a default of 45%.
- **FR-005**: The magnet behavior MUST be independently togglable (enabled/disabled) without affecting any other enrollment parameters.
- **FR-006**: When the match formula is disabled or not configured, the magnet MUST have no effect on enrollment deferral rates.
- **FR-007**: The magnet MUST produce deterministic results — identical simulation inputs (including random seed) MUST yield identical enrollment deferral distributions across runs.
- **FR-008**: For non-deferral-based match formulas (tenure-based, points-based), the magnet MUST remain inactive; these formula types are out of scope for this fix.
- **FR-009**: The existing 10% enrollment deferral ceiling MUST be respected — the magnet MUST NOT push any employee above the ceiling.
- **FR-010**: The pre-magnet demographic rate MUST be preserved in the simulation record alongside the post-magnet elected rate to support audit and scenario comparison.

### Key Entities

- **Match Formula**: Defines the employer contribution structure; contains one or more contribution tiers, each specifying the employee deferral range and the corresponding match rate. The highest employee contribution threshold across all tiers is the "match-maximizing rate."
- **Enrollment Event**: A record of an employee choosing to participate in the DC plan, including their elected deferral rate and the date of election.
- **Magnet Probability**: A scalar parameter (0.0–1.0) controlling what fraction of below-threshold enrollees snap to the match-maximizing rate. Default: 0.45.
- **Deferral Rate**: The percentage of an employee's compensation they elect to contribute to the plan. Bounded to 1%–10% for new enrollees by the enrollment ceiling.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any plan with a deferral-based match formula, the fraction of new enrollees electing the match-maximizing rate increases by at least 35 percentage points compared to the no-magnet baseline when the default magnet probability (45%) is applied.
- **SC-002**: When the magnet probability is set to 0%, the enrollment deferral distribution is statistically identical to the pre-fix baseline (no unintended side effects).
- **SC-003**: The match-maximizing rate used by the magnet matches the highest employee contribution threshold in the configured tiers within 0.01% for all deferral-based formula configurations.
- **SC-004**: Simulation results are fully reproducible — running the same scenario twice with the same seed produces identical enrollment deferral distributions.
- **SC-005**: Both the proactive enrollment path and the voluntary enrollment path exhibit the magnet effect, confirmed by querying each enrollment event type independently.
- **SC-006**: Employees already at or above the match threshold show zero change in their elected deferral rate due to the magnet (strictly upward-only behavior).
- **SC-007**: Downstream simulation outputs (plan cost projections, average deferral statistics, employer match expense) all reflect the updated enrollment deferral distribution without errors or missing values.

## Assumptions

- Scope is limited to deferral-based match formulas (where a single match-maximizing deferral rate can be computed at simulation setup time). Tenure-based and points-based formulas, which require per-employee threshold computation, are deferred to a future enhancement.
- The 45% default magnet probability is based on financial literacy research showing approximately 40–50% of employees who are aware of a match formula will optimize their contribution to capture the full match at the moment of enrollment. This is intentionally slightly higher than the post-enrollment adjustment rate (40%) because enrollment is a deliberate decision moment.
- The existing 10% enrollment deferral ceiling remains unchanged; the magnet operates within that constraint.
- No changes to the UI, API, or configuration file format are required beyond adding two new optional parameters with safe defaults.
- The fix applies only at the moment of initial enrollment. Existing enrollees whose rates were set under the prior logic are not retroactively adjusted by this change.
