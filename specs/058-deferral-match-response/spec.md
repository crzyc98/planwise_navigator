# Feature Specification: Match-Responsive Deferral Adjustments

**Feature Branch**: `058-deferral-match-response`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Generate match-responsive deferral adjustment events when the match formula creates a gap between employee deferrals and the match-maximizing rate"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upward Deferral Response to Match Improvement (Priority: P1)

A plan administrator configures a new or improved employer match formula for a simulation scenario. When the simulation runs, employees whose current deferral rates fall below the match-maximizing rate respond behaviorally — a configurable portion increase their deferrals to capture some or all of the new match, reflecting real-world "free money" behavior.

**Why this priority**: This is the core value proposition. Without upward response, the simulation unrealistically shows employees leaving employer match dollars on the table when a match is added or improved. This is the most common real-world scenario (employers adding/improving matches) and has the largest financial impact on simulation accuracy.

**Independent Test**: Can be fully tested by running a simulation where employee census deferrals cluster below the configured match-maximizing rate and verifying that a configurable percentage of employees generate upward deferral adjustment events in Year 1.

**Acceptance Scenarios**:

1. **Given** employees with census deferral rates of 3% and a newly configured 100% match on the first 6% of deferrals, **When** the simulation runs Year 1, **Then** approximately 40% of below-max employees generate upward deferral adjustment events, with 60% of responders moving to 6% and 40% partially closing the gap.
2. **Given** employees already deferring at or above the match-maximizing rate (e.g., 8% deferral with a 6% match max), **When** the simulation runs, **Then** no upward adjustment events are generated for those employees.
3. **Given** the match-responsive feature is enabled with default configuration, **When** deferral adjustments are generated, **Then** adjusted rates flow through the deferral rate state accumulator and are used in all subsequent match calculations, escalations, and contribution computations.

---

### User Story 2 - Downward Deferral Response to Match Reduction (Priority: P2)

When an employer reduces or removes a match formula, a smaller configurable portion of employees who were deferring above the new match-maximizing rate reduce their deferrals. This models the weaker but real behavioral response to reduced incentives (loss aversion means fewer employees respond downward than upward).

**Why this priority**: While less common than match improvements, match reductions do occur. Modeling the asymmetric behavioral response (weaker downward than upward) adds realism. This scenario has meaningful cost implications when employers are evaluating match reduction proposals.

**Independent Test**: Can be tested by running a simulation where employee census deferrals cluster above the configured match-maximizing rate and verifying that approximately 15% of above-max employees generate downward adjustment events.

**Acceptance Scenarios**:

1. **Given** employees deferring at 8% and a match formula with a 3% match-maximizing rate, **When** the simulation runs Year 1, **Then** approximately 15% of above-max employees generate downward adjustment events, with 70% of responders dropping to 3% and 30% partially decreasing.
2. **Given** a match formula is completely removed (no employer match), **When** the simulation runs, **Then** the match-maximizing rate is 0%, making all enrolled employees with any deferral candidates for downward response, with the configured participation rate (default 15%) determining how many actually reduce.
3. **Given** default configuration, **When** downward responses are generated, **Then** the downward participation rate (15%) is significantly lower than the upward participation rate (40%), reflecting asymmetric behavioral economics.

---

### User Story 3 - Feature Toggle and Configuration (Priority: P2)

Plan administrators can enable or disable match-responsive behavior and tune all behavioral parameters (participation rates, maximize vs. partial split, partial increase factor) through the simulation configuration without requiring code changes.

**Why this priority**: Configurability is essential for scenario analysis. Different clients have different employee populations with varying behavioral characteristics. Administrators need to model conservative, moderate, and aggressive response assumptions.

**Independent Test**: Can be tested by running the same simulation twice — once with the feature enabled and once disabled — and confirming that disabled runs produce zero match-response events while enabled runs produce the expected distribution.

**Acceptance Scenarios**:

1. **Given** `deferral_match_response.enabled: false` in configuration, **When** the simulation runs, **Then** zero match-response deferral adjustment events are generated and simulation results match pre-feature behavior exactly.
2. **Given** custom configuration with `upward_response.participation_rate: 0.80`, **When** the simulation runs, **Then** approximately 80% of below-max employees respond (not the default 40%).
3. **Given** downward response is specifically disabled (`downward_response.enabled: false`) while the overall feature is enabled, **When** the simulation runs, **Then** only upward adjustments are generated.

---

### User Story 4 - All Match Mode Compatibility (Priority: P3)

Match-responsive deferral adjustments work correctly across all four match calculation modes: deferral-based, service-based (graded by service), tenure-based, and points-based. Each mode has its own method for determining the match-maximizing deferral rate.

**Why this priority**: The system supports multiple match modes, and the feature must work consistently across all of them. However, deferral-based matching is the most common mode, so the other modes are lower priority.

**Independent Test**: Can be tested by running simulations with each of the four match modes and verifying that the correct match-maximizing rate is calculated for each mode and that adjustment events reference the right target rate.

**Acceptance Scenarios**:

1. **Given** deferral-based match with tiers covering 0-3% at 100% and 3-5% at 50%, **When** the match-maximizing rate is calculated, **Then** it equals 5% (the upper bound of the highest tier).
2. **Given** service-based match where an employee's service tier has `max_deferral_pct: 0.06`, **When** the match-maximizing rate is calculated, **Then** it equals 6%.
3. **Given** points-based match where an employee's points tier has `max_deferral_pct: 0.08`, **When** the match-maximizing rate is calculated, **Then** it equals 8%.

---

### User Story 5 - Integration with Auto-Escalation (Priority: P3)

Match-responsive deferral adjustments are additive to the existing auto-escalation (AIP) mechanism. When an employee's deferral rate is increased by a match response, subsequent auto-escalation events build from the new adjusted rate, not the original pre-response rate.

**Why this priority**: Correct interaction between these two deferral-modifying mechanisms is critical for long-term simulation accuracy, but is largely handled by the existing state accumulator architecture.

**Independent Test**: Can be tested by running a multi-year simulation (e.g., 2025-2027) where match response raises an employee from 3% to 6% in Year 1, then verifying that auto-escalation in Year 2 raises them from 6% to 7% (not from 3% to 4%).

**Acceptance Scenarios**:

1. **Given** an employee at 3% deferral, match response moves them to 6% in Year 1, and auto-escalation is configured at +1%/year with a 10% cap, **When** Year 1 runs and the employee is also eligible for escalation, **Then** both adjustments apply: match response sets the rate to 6%, then escalation increases it to 7%.
2. **Given** an employee at 3% deferral with match response moving them to 6% in Year 1, and auto-escalation configured at +1%/year, **When** Year 2 runs, **Then** the employee's deferral rate escalates from 7% to 8% (building from the Year 1 combined result).
3. **Given** match-responsive adjustment plus escalation raises an employee to the auto-escalation cap (10%), **When** subsequent years run, **Then** no further escalation events are generated for that employee.

---

### Edge Cases

- What happens when an employee's census deferral rate exactly equals the match-maximizing rate? No adjustment event is generated — the employee is already optimally positioned.
- What happens when the match formula has no practical maximum (e.g., flat percentage match on all deferrals)? The match-maximizing rate is treated as the plan's maximum allowed deferral rate or the IRS 402(g) limit, whichever is lower.
- What happens when an employee is newly hired in the same year as match response processing? New hires already have match-optimization logic in the voluntary enrollment model; match response events only apply to employees who were enrolled in a prior year.
- What happens when an employee has been terminated before match response events are processed? Terminated employees are excluded from match-response adjustments.
- What happens with partial-year employees (hired mid-year)? They are eligible for match response if enrolled, and their adjusted rate applies for the remainder of the year.
- What happens when the configured match-maximizing rate is below an employee's current deferral and the feature is set to upward-only? No adjustment — downward adjustments are a separate, independently configurable behavior.
- What happens when an employee is eligible for both match-response and auto-escalation in the same year? Both apply: match response fires first (setting the new baseline rate), then auto-escalation increments from that adjusted rate.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate one-time deferral adjustment events when enrolled employees' current deferral rates fall below the match-maximizing rate implied by the configured match formula.
- **FR-002**: System MUST calculate the match-maximizing deferral rate correctly for all four match modes:
  - Deferral-based: upper bound of the highest match tier
  - Service-based: `max_deferral_pct` from the employee's service year tier
  - Tenure-based: `max_deferral_pct` from the employee's tenure tier
  - Points-based: `max_deferral_pct` from the employee's points tier
- **FR-003**: System MUST apply a configurable participation rate to determine what fraction of affected employees respond (default 40% upward, 15% downward).
- **FR-004**: System MUST distribute responding employees into two sub-groups: those who move to the match-maximizing rate ("maximizers") and those who partially close the gap, with configurable split percentages. The partial gap-closing factor (default 0.50) applies symmetrically in both upward and downward directions.
- **FR-005**: System MUST support asymmetric response rates where downward participation is independently configurable and defaults to a lower rate than upward participation. Asymmetry is modeled through participation rates (default 40% upward, 15% downward), not through the partial gap-closing factor.
- **FR-006**: System MUST use deterministic random assignment (seeded by employee ID and simulation year) so that results are reproducible across identical simulation runs.
- **FR-007**: System MUST allow the feature to be completely disabled via configuration, producing zero match-response events when disabled.
- **FR-008**: System MUST allow downward response to be independently disabled while upward response remains active.
- **FR-009**: Adjusted deferral rates MUST flow through the deferral rate state accumulator so that downstream models (match calculations, contribution calculations, escalation events) use the updated rates.
- **FR-010**: Match-response adjustments MUST be additive to auto-escalation — the adjusted rate becomes the new baseline for future escalation calculations.
- **FR-011**: System MUST apply match-response adjustments only in the first simulation year (with architecture supporting future "gradual" multi-year rollout).
- **FR-012**: System MUST only generate adjustment events for actively employed, enrolled employees — excluding terminated, unenrolled, and newly-hired employees (who already have match optimization in enrollment).
- **FR-013**: System MUST record each adjustment as a distinct event with audit fields: previous rate, new rate, match-maximizing target rate, response type (maximize/partial), and match mode used.
- **FR-014**: System MUST cap adjusted deferral rates at the configured maximum deferral rate (auto-escalation cap) and the IRS 402(g) elective deferral limit.

### Key Entities

- **Match-Response Deferral Adjustment Event**: A one-time event recording an employee's deferral rate change in response to the match formula. Key attributes: employee ID, previous deferral rate, new deferral rate, target match-maximizing rate, response category (maximize/partial/none), match mode, simulation year.
- **Match-Maximizing Rate**: The deferral rate at which an employee captures the maximum possible employer match under the current formula. Varies by match mode and may vary per employee (for service/tenure/points modes).
- **Deferral Match Response Configuration**: The set of behavioral parameters controlling participation rates, response distribution, and timing. Stored in simulation configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When the feature is enabled and employees' census deferrals cluster below the match-maximizing rate, the simulation generates upward adjustment events for the configured percentage of affected employees (within 5% tolerance due to deterministic randomness).
- **SC-002**: The distribution of adjusted rates matches configuration: the configured split between maximizers and partial responders holds across a population of 100+ employees (within 10% tolerance).
- **SC-003**: Employer match costs in simulation output increase measurably when employees respond upward to a new match formula, compared to a disabled-feature baseline — demonstrating that adjusted deferrals flow through to match calculations.
- **SC-004**: Multi-year simulations show escalation continuing from the match-response-adjusted rate, not the original census rate, confirming correct state accumulator integration.
- **SC-005**: When the feature is disabled, simulation results are byte-identical to pre-feature behavior (no events generated, no cost differences).
- **SC-006**: All four match modes (deferral-based, service-based, tenure-based, points-based) produce correct match-maximizing rate calculations verified against manually computed expected values.
- **SC-007**: Downward response participation rate is observably lower than upward response rate in scenarios where both directions are active, confirming asymmetric modeling.
- **SC-008**: Every match-response event includes complete audit trail fields (previous rate, new rate, target rate, response type, match mode) enabling full reconstruction of the behavioral modeling decision.

## Clarifications

### Session 2026-02-21

- Q: When both match-response and auto-escalation are eligible in Year 1, which applies and in what order? → A: Both apply in Year 1. Match response fires first (setting the new baseline), then auto-escalation applies on top of the adjusted rate. An employee could go 3% → 6% (match response) → 7% (escalation) in a single year.
- Q: When the match is completely removed, what threshold determines downward response eligibility? → A: The match-maximizing rate is 0%. All enrolled employees with any deferral above 0% are candidates, with the participation rate (default 15%) limiting actual response volume.
- Q: What factor do partial downward responders use to close the gap? → A: Same as upward (0.50). Partial responders close 50% of the gap in both directions. Asymmetry between upward and downward behavior is modeled through the participation rate (40% vs. 15%), not the partial factor.

## Assumptions

- Census deferral rates implicitly encode the prior incentive structure. If employees cluster below the match-maximizing rate, the system assumes there is an opportunity for behavioral response without needing to know the historical plan design.
- The behavioral response is modeled as a one-time adjustment in the first simulation year. Gradual multi-year rollout is deferred to a future enhancement.
- Employee selection for response uses deterministic hashing (employee ID + simulation year as seed) to ensure reproducibility. The exact assignment algorithm follows existing patterns in the voluntary enrollment model.
- New hires in the simulation's first year are excluded from match-response events because they already receive match-optimized deferral rates through the existing voluntary enrollment decision model.
- When no match formula is configured (employer match disabled), the match-maximizing rate is 0%. No upward response events are generated (there is nothing to optimize toward). If downward response is enabled, all enrolled employees with deferral rates above 0% are candidates, with the participation rate limiting actual reductions.
- Partial responders close a configurable fraction of the gap between their current rate and the match-maximizing rate, rounded to the nearest 0.5% increment for realism.
- The IRS 402(g) elective deferral limit and the plan's configured maximum deferral rate both serve as hard caps on any adjusted rate.

## Dependencies

- Requires the deferral rate state accumulator (`int_deferral_rate_state_accumulator`) to be functional and support merging a new event source.
- Requires match formula configuration (match tiers, service tiers, tenure tiers, or points tiers) to be loaded before match-response processing.
- Requires the enrollment state accumulator to identify which employees are currently enrolled and at what rate.
- Must execute after enrollment events and before the final deferral rate state accumulator output in the pipeline stage order.
