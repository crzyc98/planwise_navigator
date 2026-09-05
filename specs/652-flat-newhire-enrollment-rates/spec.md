# Feature Specification: Explicit New-Hire Enrollment Rates and Deferral Spread

**Feature Branch**: `652-flat-newhire-enrollment-rates`
**Created**: 2026-09-04
**Status**: Draft
**Tracking Issue**: #652
**Input**: User description: "The `dc_plan.voluntary_enrollment_rate` control does not mean 'what % of new hires voluntarily enroll' — it is a multiplier on demographic enrollment probabilities, so setting it to 100% is a no-op. Let the analyst set two flat, deterministic rates for new hires (voluntary enrollment %, opt-out %) and let everything else fall into auto-enrollment."

## Context

Today an analyst who wants to model "all new hires voluntarily enroll" sets the voluntary enrollment rate to 100% and gets roughly 60% voluntary enrollment. The control is a multiplier applied on top of age-, income-, and job-level-based enrollment probabilities, so its maximum value leaves the underlying demographic ceiling (~58% average) intact. Three separate enrollment paths (proactive-voluntary, voluntary, auto-enroll) each draw independently, and opt-out is likewise derived from demographics, so no single number in the model corresponds to an analyst-stated percentage.

The observed reproduction (scenario "AE All Elig but 100% Voluntary", seed 42) splits eligible new hires across four outcomes despite the stated 100% voluntary setting, including a large "not enrolled" bucket that should be empty when auto-enrollment covers all eligible employees.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyst sets an exact new-hire voluntary enrollment percentage (Priority: P1)

A benefits analyst modeling a plan design states a new-hire voluntary enrollment assumption — for example, "60% of eligible new hires enroll on their own" — enters it as the voluntary enrollment rate, runs the simulation, and sees that assumption reproduced in the results.

**Why this priority**: This is the core defect. Until the stated number and the observed number match, every downstream participation, deferral, and cost projection built on this control is unexplainable to a client.

**Independent Test**: Run a multi-year simulation with the voluntary rate set to a known value and count eligible new hires whose enrollment source is voluntary. The share must equal the stated rate within rounding. Testable on its own with no other change in the feature.

**Acceptance Scenarios**:

1. **Given** auto-enrollment is on with all eligible employees in scope, **When** the analyst sets the new-hire voluntary enrollment rate to 60% and runs the simulation, **Then** approximately 60% of eligible new hires are recorded as voluntarily enrolled in their hire year.
2. **Given** the same configuration, **When** the analyst sets the rate to 100%, **Then** approximately 100% of eligible new hires are recorded as voluntarily enrolled, with no demographic reduction.
3. **Given** the same configuration, **When** the analyst sets the rate to 0%, **Then** no eligible new hire is recorded as voluntarily enrolled.
4. **Given** a fixed random seed, **When** the same configuration is run twice, **Then** the same individual new hires are selected as voluntary enrollees both times.

---

### User Story 2 - Analyst sets an exact new-hire opt-out percentage (Priority: P1)

The analyst states an opt-out assumption for auto-enrolled new hires — for example, "10% of auto-enrolled new hires opt out" — and sees exactly that share opting out, independent of the population's age and income mix.

**Why this priority**: Opt-out is the second half of the same control surface. Without it, the analyst can pin the voluntary share but the remainder still splits by an uncontrollable demographic model, so the overall participation number is still not a stated assumption.

**Independent Test**: Run with a known opt-out rate and count auto-enrolled new hires recorded as opted out versus participating. The share must equal the stated rate within rounding.

**Acceptance Scenarios**:

1. **Given** a new-hire voluntary rate of 60% and an opt-out rate of 10%, **When** the simulation runs, **Then** approximately 36% of eligible new hires are auto-enrolled and participating and approximately 4% are recorded as opted out of auto-enrollment.
2. **Given** a voluntary rate of 0% and an opt-out rate of 0%, **When** the simulation runs, **Then** 100% of eligible new hires are auto-enrolled and participating.
3. **Given** any voluntary rate and any opt-out rate with auto-enrollment covering all eligible employees, **When** the simulation runs, **Then** approximately 0% of eligible new hires end the hire year not enrolled.

---

### User Story 3 - Analyst reads the control and understands what it does (Priority: P2)

The analyst opens the scenario configuration screen and sees fields whose labels and help text state plainly that they are new-hire percentages, along with the new opt-out field.

**Why this priority**: The behavior fix is what matters, but the current label is the reason the wrong mental model formed. Correct labeling prevents the same misreading from recurring and is a prerequisite for the analyst to trust the numbers.

**Independent Test**: Open the scenario configuration screen and confirm the voluntary field is labeled as a new-hire percentage and the opt-out field is present and editable.

**Acceptance Scenarios**:

1. **Given** the scenario configuration screen, **When** the analyst views the enrollment settings, **Then** the voluntary control is labeled as a new-hire voluntary enrollment percentage rather than a generic "voluntary enrollment rate".
2. **Given** the scenario configuration screen, **When** the analyst views the enrollment settings, **Then** a new-hire opt-out percentage field is available and accepts values from 0% to 100%.

---

### User Story 4 - Continuing-employee behavior is preserved (Priority: P2)

An analyst who has only changed new-hire assumptions sees continuing (non-new-hire) employees enroll and convert year over year exactly as they did before.

**Why this priority**: The new controls are scoped to new hires by design. Silently changing the continuing population would make year-over-year comparisons and existing calibrations invalid, and would confound validation of Stories 1 and 2.

**Independent Test**: Compare continuing-employee enrollment counts before and after the change for a scenario whose new-hire rates match its previous demographic outcome.

**Acceptance Scenarios**:

1. **Given** a scenario with the new controls in place, **When** the simulation runs, **Then** enrollment decisions for employees who are not new hires in the simulation year continue to follow the demographic model.
2. **Given** the demographic model for continuing employees, **When** the analyst changes the new-hire voluntary rate, **Then** continuing-employee enrollment outcomes are unaffected.

---

### User Story 5 - Deferral rates look like real elections, not table lookups (Priority: P2)

An analyst looking at the deferral-rate distribution for new hires sees a realistic spread of elections rather than every person in a demographic cell sitting on the identical rate.

**Why this priority**: Independent of who enrolls, the *rate* they enroll at is currently a table lookup with no variation — 264 of 621 new hires in the reproduction all sit at exactly 6%. Real elections scatter. This undermines the credibility of any deferral-driven cost projection, and it is the reason adjusting the demographic table appears to do nothing to the visible clustering.

**Independent Test**: Run with the spread enabled and confirm that a single demographic cell produces a distribution of whole-percent rates at or above its table value rather than a single spike. Testable with no reference to the enrollment-rate work.

**Acceptance Scenarios**:

1. **Given** the spread is enabled, **When** the simulation runs, **Then** employees in one demographic cell are distributed across whole-percentage rates from the cell's table value up to 4 points above it, with the table value the most common single outcome.
2. **Given** the spread is enabled, **When** the simulation runs, **Then** no employee receives a rate *below* their cell's table value — the table value acts as a floor.
3. **Given** the spread is disabled or unset, **When** the simulation runs, **Then** every employee receives exactly their cell's table value, unchanged from today.
4. **Given** a fixed seed, **When** the same configuration is run twice, **Then** each employee receives the identical rate both times.

---

### Edge Cases

- **Auto-enrollment disabled**: When auto-enrollment is off, the voluntary rate still selects its stated share of eligible new hires; the remainder stays not enrolled rather than being auto-enrolled, and the opt-out rate has no effect.
- **Auto-enrollment scope narrower than eligibility**: When auto-enrollment applies to only part of the eligible new-hire population (for example, by hire-date cutoff), non-voluntary new hires outside that scope stay not enrolled. The "no one is left not enrolled" guarantee holds only for new hires who are in auto-enrollment scope.
- **New hires not eligible in their hire year**: New hires who do not meet eligibility in their hire year (for example, under a waiting period) are excluded from both rates; they enter the eligible population in the year they become eligible, and are treated by the new-hire rates in that first eligible year.
- **Rates at the boundaries**: 0% and 100% must be exactly honored, not approximately — 100% voluntary leaves nobody for auto-enrollment, and 100% opt-out leaves no auto-enrolled participants.
- **Rates outside 0–100%**: Values outside the valid range are rejected with a clear message at configuration time rather than silently clamped mid-run.
- **Very small new-hire cohorts**: With few eligible new hires in a year, the realized share is limited by integer counts; the outcome must be the closest achievable split and must remain deterministic for a fixed seed.
- **Spread pushing a rate past the maximum**: An employee whose spread would exceed the configured maximum deferral rate is capped at that maximum. Cells whose table value already sits at the maximum therefore cannot spread at all.
- **Spread interacting with match-maximizing behavior**: The existing behavior that pulls some employees up to the employer-match ceiling continues to apply after the spread. An employee spread above the ceiling is not pulled back down.
- **Both rates omitted**: A scenario that sets neither rate keeps the existing demographic behavior for both decisions, unchanged from before this feature.
- **One rate set, the other omitted**: The set rate applies as a flat fraction while the omitted one keeps its demographic behavior. The four-outcome guarantee in FR-003 holds only when the voluntary rate is set.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let an analyst express new-hire voluntary enrollment as a direct fraction of eligible new hires (0% to 100%), not as a multiplier on demographic probabilities.
- **FR-002**: The system MUST let an analyst express new-hire opt-out as a direct fraction of auto-enrolled new hires (0% to 100%), independent of demographics.
- **FR-003**: For eligible new hires within auto-enrollment scope, given voluntary rate P and opt-out rate Q, the system MUST produce approximately P voluntarily enrolled, (1−P)×(1−Q) auto-enrolled and participating, (1−P)×Q opted out, and 0 not enrolled.
- **FR-004**: The system MUST decide each new hire's voluntary enrollment through a single decision, so that a new hire cannot be selected by one enrollment path and independently reconsidered by another.
- **FR-005**: Selection of which specific new hires enroll voluntarily and which opt out MUST be deterministic and reproducible for a given random seed and configuration.
- **FR-006**: The system MUST continue to assign a deferral rate to voluntarily enrolled new hires using the existing demographic deferral-rate selection; only the enroll/don't-enroll decision changes.
- **FR-007**: Enrollment decisions for employees who are not new hires in the simulation year MUST continue to use the existing demographic model, and MUST NOT be scaled by the new new-hire rates.
- **FR-008**: The system MUST validate both rates at configuration time and reject values outside 0% to 100% with a message naming the offending field.
- **FR-009**: The scenario configuration interface MUST label the voluntary control explicitly as a new-hire voluntary enrollment percentage and MUST expose the new-hire opt-out percentage as an editable field.
- **FR-010**: Simulation results MUST continue to distinguish the four new-hire enrollment outcomes (voluntary, auto-enrolled participating, opted out, not enrolled) so the stated rates can be verified against the output.
- **FR-011**: The system MUST record which enrollment mechanism produced each new-hire enrollment, so an analyst can reconcile the realized shares against the configured rates.
- **FR-012**: Leaving the new-hire voluntary enrollment rate unset MUST preserve the existing demographic new-hire enrollment behavior, so that scenarios saved before this change and carrying no explicit rate reproduce their previous results.
- **FR-013**: Setting the new-hire voluntary enrollment rate to any explicit value, including 100%, MUST apply the new flat-rate meaning. Scenarios that stored an explicit value before this change will therefore change behavior; this is intended, because those values previously did not express what the analyst entered.
- **FR-014**: The system MUST NOT introduce a second, separately-named voluntary enrollment control. There is one voluntary enrollment setting whose unset state means "use demographics" and whose set state means "this exact fraction of eligible new hires".
- **FR-015**: The new-hire opt-out rate MUST follow the same convention: unset preserves the existing demographic opt-out behavior for auto-enrolled new hires, and any explicit value applies as a flat fraction.
- **FR-016**: Documentation and in-product help describing the enrollment controls MUST state the new meaning, the unset-versus-set distinction, and the expected outcome distribution.
- **FR-017**: The system MUST support an upward-only deferral-rate spread, in which a demographic cell's table value acts as a floor and employees are distributed across whole-percentage rates from that floor up to a configurable maximum lift (default 4 percentage points).
- **FR-018**: The distribution across the lift MUST decay from the floor upward, with the floor the most common single outcome. Target weights are 40% at the floor and 30% / 15% / 10% / 5% at +1 through +4 percentage points.
- **FR-019**: No employee MUST receive a deferral rate below their demographic cell's table value under the spread.
- **FR-020**: The spread MUST be off by default. When it is off, every employee receives exactly their cell's table value, unchanged from today.
- **FR-021**: Spread assignment MUST be deterministic and reproducible for a given seed, and MUST be drawn independently of the existing match-maximizing behavior so that the two do not correlate.
- **FR-022**: The maximum voluntary deferral rate MUST default to 15%, raised from 10%, so that the higher demographic cells have room to spread.
- **FR-023**: The spread MUST apply consistently to every path that assigns a demographic deferral rate, including new-hire voluntary enrollment and year-over-year conversion, so that one population is not visibly smoother than another.

### Key Entities

- **Eligible new hire**: An employee hired in the simulation year who meets plan eligibility in that year. This is the denominator for the voluntary enrollment rate.
- **New-hire voluntary enrollment rate**: An analyst-stated fraction, 0% to 100%, of eligible new hires who enroll on their own in their hire year.
- **New-hire opt-out rate**: An analyst-stated fraction, 0% to 100%, of auto-enrolled new hires who opt out.
- **Enrollment outcome**: One of four mutually exclusive end-of-hire-year states — voluntarily enrolled, auto-enrolled and participating, opted out of auto-enrollment, or not enrolled.
- **Enrollment source**: The mechanism that produced an enrollment, used to reconcile realized shares against configured rates.
- **Deferral rate assignment**: The contribution percentage given to an enrolled employee, still selected from the demographic table and unchanged by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With a voluntary rate of 60% and an opt-out rate of 10%, the realized shares of eligible new hires are within 2 percentage points of 60% voluntary, 36% auto-enrolled participating, and 4% opted out, in every simulated year. (2 points, not 1: selection is a per-employee draw rather than an exact count, so a cohort of ~870 deviates about 1.7 points at one standard deviation.)
- **SC-002**: With a voluntary rate of 100%, at least 99% of eligible new hires are voluntarily enrolled.
- **SC-003**: With a voluntary rate of 0% and an opt-out rate of 0%, at least 99% of eligible new hires are auto-enrolled and participating.
- **SC-004**: With auto-enrollment covering all eligible employees, no more than 1% of eligible new hires end their hire year not enrolled, in every simulated year.
- **SC-005**: Two runs with the same seed and configuration select the identical set of individual new hires for voluntary enrollment and for opt-out.
- **SC-006**: Continuing-employee enrollment counts are unchanged from the pre-change baseline for a scenario in which the new-hire rates are set to reproduce the previous demographic outcome.
- **SC-007**: An analyst can predict the new-hire enrollment split from the two configured numbers alone, without reference to the population's age or income mix.
- **SC-008**: An analyst reading the configuration screen can state what each of the two controls does without consulting source code or a data dictionary.
- **SC-009**: A scenario that sets neither rate produces new-hire enrollment counts identical to the pre-change baseline, in every simulated year.
- **SC-010**: With the spread enabled, no demographic cell contains more than 45% of its members at any single deferral rate, in every simulated year. (Today the figure is 100%.)
- **SC-011**: With the spread enabled, zero employees hold a deferral rate below their demographic cell's table value.
- **SC-012**: With the spread disabled, deferral rates are identical to the pre-change baseline for every employee.
- **SC-013**: An analyst can see, from the deferral-rate distribution alone, that rates were elected rather than assigned — no cell renders as a single spike.

## Assumptions

- The two rates apply to new hires only. Continuing employees, year-over-year conversion, and re-enrollment stay on the existing demographic model.
- The enrollment rates govern the enroll/don't-enroll and opt-out decisions only. The deferral percentage for those who do enroll continues to come from the demographic deferral-rate table, now with the optional upward spread applied to it.
- The spread raises average deferral rates and therefore projected employer match cost. This is intended: today's averages are artificially low because every member of a cell sits exactly on the floor.
- Raising the maximum deferral rate from 10% to 15% changes results on its own, independently of the spread, because four cells in the demographic table (mature/executive, senior/high at 12%, senior/executive at 15%) are currently clamped down to 10%. This is an accepted behavior change, not a side effect of the spread.
- "New hire" means an employee whose hire date falls in the simulation year, matching the existing new-hire classification in results.
- The denominator for the voluntary rate is eligible new hires, not all new hires; ineligible new hires are outside the scope of both rates.
- When auto-enrollment is disabled or its scope excludes a new hire, the "everything else auto-enrolls" rule does not apply to that new hire and they stay not enrolled.
- Deterministic selection continues to be seed-driven and reproducible, consistent with the platform's existing reproducibility guarantee.
- The setting's unset state is already distinguishable from an explicit value throughout the configuration path, so no new field or migration is required to tell the two apart.
- The demographic new-hire enrollment model is retained to serve the unset case. Retiring it in favour of a single flat path with a stated default is possible follow-on work, not part of this feature.
- Realized shares are exact within integer rounding for a given cohort size; small cohorts will not land precisely on the stated percentage.
- The opt-out rate replaces the demographic opt-out model for auto-enrolled new hires only; opt-out behavior for other populations is unchanged.

## Out of Scope

- Changing demographic enrollment, deferral-rate, or opt-out behavior for continuing employees.
- Changing the *values* in the demographic deferral-rate table, or re-calibrating them to offset the spread's upward shift. The spread raises average deferral rates by design.
- Changing eligibility rules, waiting periods, or auto-enrollment scope semantics.
- Adding segment-varying (by age, income, or job level) new-hire enrollment or opt-out rates.
- Changing deferral rates for census employees, who carry their actual rates from the input file and are unaffected by the demographic table.
- Retroactively recomputing results of previously completed simulation runs.
