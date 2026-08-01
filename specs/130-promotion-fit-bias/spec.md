# Feature Specification: Trustworthy Promotion Rate from a Census Without Job Levels

**Feature Branch**: `130-promotion-fit-bias`
**Created**: 2026-08-01
**Status**: Draft
**Input**: GitHub issue [#511](https://github.com/crzyc98/planwise_navigator/issues/511) — "Promotion rate is over-inferred when the census has no `level_id`", found while implementing #458 (PR #509).

## Problem Statement

The parameter fitter recovers a client's promotion rate by comparing an employee's job level between two consecutive annual census snapshots: a move to a higher level is a promotion.

When the client's census carries an explicit job-level column, this works. When it does not — a common case — job level is derived from where the employee's compensation falls in the configured compensation bands, matching how the simulator's baseline workforce assigns levels. That derivation makes level a function of pay, so **any raise that pushes an employee across a band boundary is read as a promotion**. An ordinary merit raise does this on its own.

The measured effect is large, and it **gets worse the more history a client supplies**. In the synthetic grading harness, a population with a true 6% promotion rate fits at **9.1% over 3 snapshots and 15.2% over 5** — no promotions beyond the true ones are present in the data. (Issue #511 reported 16.8%, consistent with a longer history; the 3-snapshot default reproduces 9.1%.) Termination, which does not depend on band derivation, recovers cleanly. The bias is specific to promotion.

The mechanism is a wave, not a steady climb. Nobody leaves a compensation band except by crossing it, so an incumbent cohort drifts upward and piles against its ceiling: the per-year crossing rate runs 3.3% → 15.3% → 23.8% → 21.2% before decaying as employees who crossed settle at the bottom of the next band. Across the 2–5 snapshots the fitter accepts, that means the cumulative estimate gets *worse* the more history a client supplies — 3.3% at two snapshots, 14.2% at five. (It peaks near 16.4% around six, which is where issue #511's figure came from.)

Today the fitter emits the inflated number together with a prominent warning in the fit report and the CLI, documenting it as an upper bound. That is honest but not usable: an analyst handed a promotion hazard that may be 3x too high cannot run a credible projection from it, and has no way to tell how far off it is.

A second-order effect: merit is fitted from the median compensation growth of employees classified as **not promoted**. Over-classifying promotions removes the largest ordinary raises from that pool, so a biased promotion classification also biases the merit estimate. The two estimates are coupled, which is why "only count a band crossing as a promotion when the raise exceeds the merit band" is not a valid fix — it would define promotion in terms of a merit rate that is itself measured off the promotion classification.

## Clarifications

### Session 2026-08-01

- Q: When promotion is estimated from the raise distribution rather than measured from an explicit job-level column, does the result still carry age and tenure adjustments, or only a coarser rate? → A: Estimate a per-level promotion rate from the distribution, then assign each transition a promotion weight and fit the age and tenure adjustments from those weights through the existing hazard solver. The parameter pack's shape is identical on both paths.
- Q: How is the merit pool defined when the promotion hazard could not be fitted? → A: Merit is always a promotion-weighted median over all continued employees, on every path. Probable promotions are down-weighted rather than excluded, so the definition degrades gracefully instead of branching.
- Q: Is the "cannot separate promotions from ordinary raises" verdict global to the fit, or decided per job level? → A: Per job level. Levels that separate contribute fitted rates; levels that do not retain their configured default. The hazard is reported not fitted overall only when the separating levels cover too little of the experienced exposure (default: under half).
- Q: How is a job-level column that is present but only partially populated handled? → A: Route by coverage, not mere presence. At or above a stated coverage threshold (default 95% of experienced exposure) the column is authoritative and unpopulated rows are excluded from promotion exposure; below it the column is ignored and the estimated path is used. The report states which route was taken and the observed coverage.
- Q: Which of the thresholds gating a promotion fit are analyst-adjustable? → A: The two coverage thresholds (job-level coverage, exposure coverage) are adjustable; the per-level separation test is fixed. Tuning the separation test is indistinguishable from manufacturing a promotion rate. Non-default threshold values are recorded in the report and the pack provenance.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fit a promotion rate from a census with no job-level column (Priority: P1)

An analyst receives a client census with two to five annual snapshots and no job-level column — just employee id, compensation, hire date, birth date, and enrollment fields. They run the fitter to produce a parameter pack, and expect the promotion hazard in that pack to reflect the client's actual promotion behavior, not the rate at which merit raises happen to cross a compensation band boundary.

**Why this priority**: This is the whole defect. Without it, the promotion hazard in every level-less parameter pack is unusable, which undermines the value of fitting from client history at all.

**Independent Test**: Take the synthetic population with a known promotion rate, strip its job-level column, run the fit, and assert the recovered promotion rate lands within the accuracy bar of the truth — the same assertion already applied to termination.

**Acceptance Scenarios**:

1. **Given** a census history with a known 6% promotion rate and no job-level column, **When** the analyst fits parameters from it, **Then** the reported promotion rate is within the stated accuracy tolerance of 6%, not the 9.1%–15.2% produced by band-crossing classification.
2. **Given** the same census history **with** a fully populated job-level column, **When** the analyst fits parameters from it, **Then** the promotion rate is measured directly from level moves and is unchanged from today's behavior — a sufficiently populated column remains authoritative.
3. **Given** a census with no job-level column, **When** the fit completes, **Then** the fit report states which method produced the promotion rate and what evidence supported it, so the number can be defended to a client.
4. **Given** two fits of the same population — one with the job-level column, one without — **When** both packs are inspected, **Then** they contain the same promotion hazard seed data files with the same structure, differing only in the fitted values.

---

### User Story 2 - Know when the promotion rate cannot be trusted, and be told so plainly (Priority: P1)

Separating promotion raises from ordinary raises depends on the two being distinguishable in the client's data. Some histories will not support it: a client whose promotion increases are small, whose ordinary-raise spread is wide, or whose exposure is thin. The analyst must be told explicitly when this is the case, rather than handed a number that silently reverts to the old bias.

**Why this priority**: A wrong-but-confident promotion rate is worse than no promotion rate. This is the guardrail that makes User Story 1 safe to rely on, and it must ship with it.

**Independent Test**: Construct a census history where promotion raises and ordinary raises overlap heavily, run the fit, and assert the promotion hazard is reported as not fitted, with the configured default retained and the reason stated.

**Acceptance Scenarios**:

1. **Given** a census where promotion raises and ordinary raises are not distinguishable at any level, **When** the analyst fits parameters, **Then** the promotion hazard is listed among the parameters that could not be fitted, the configured default is retained in the pack, and the report explains why.
2. **Given** a census where junior levels separate cleanly but senior levels do not, and the separating levels hold most of the headcount, **When** the analyst fits parameters, **Then** the junior levels carry fitted rates, the senior levels retain their defaults, and the report names which levels fell back.
3. **Given** a census where only a thin minority of the population sits in levels that separate, **When** the analyst fits parameters, **Then** the promotion hazard is reported not fitted overall rather than published on the strength of that minority.
4. **Given** the promotion hazard could not be fitted, **When** the analyst runs a simulation with the resulting parameter pack, **Then** the simulation runs successfully using the retained default promotion hazard, and the run's provenance records that promotion was not fitted.
5. **Given** the promotion hazard was fitted successfully, **When** the analyst reads the fit report, **Then** the report distinguishes this case from the not-fitted case without ambiguity — no run leaves the analyst guessing which they got.

---

### User Story 3 - Merit estimate is no longer distorted by promotion misclassification (Priority: P2)

The same analyst reads the fitted per-level merit rates in the pack. Those rates must reflect the client's ordinary raise behavior, not a pool artificially stripped of its largest ordinary raises by an over-eager promotion classification.

**Why this priority**: A real but secondary consequence of the same defect. It matters for projection accuracy but does not block using the pack, and it is largely fixed as a by-product of getting promotion classification right.

**Independent Test**: Fit the level-stripped synthetic population and assert the recovered per-level merit rate is within tolerance of the truth used to generate it — an assertion that fails today because promotion over-classification removes the top raises from the merit pool.

**Acceptance Scenarios**:

1. **Given** a census with a known merit rate and a known promotion rate and no job-level column, **When** parameters are fitted, **Then** both the merit rate and the promotion rate are recovered within tolerance of their true values.
2. **Given** the promotion hazard could not be fitted, **When** parameters are fitted, **Then** merit is still fitted from the promotion-weighted median, and the report states that the weighting could not be sharpened by a usable promotion classification.
3. **Given** a census **with** an explicit job-level column, **When** merit is fitted under the promotion-weighted definition, **Then** the resulting per-level merit rates match the current release's ex-promotions result — the new definition is a generalization, not a change, on the clean path.

---

### User Story 4 - Preserve the job-level column end to end so the problem never arises (Priority: P3)

When a client census does carry a job-level column, every step that touches the census before fitting — notably anonymization — must carry that column through. The cheapest fix for any given engagement is for the column to survive to the fitter.

**Why this priority**: Not a fix for the defect, but a check that the clean path is not being closed off elsewhere. Low cost, and it removes the problem entirely for clients who supply the column.

**Independent Test**: Run a census containing a job-level column through the anonymizer and assert the column is present, unmodified, in the output.

**Acceptance Scenarios**:

1. **Given** a source census containing a job-level column, **When** it is anonymized, **Then** the output census still contains that column with its original values.
2. **Given** an anonymized census that retains a job-level column at or above the coverage threshold, **When** it is fitted, **Then** the fitter measures promotions directly from level moves and issues no derivation warning.
3. **Given** anonymization that dropped or blanked the job-level column, **When** the result is fitted, **Then** the run falls to the estimated path and the report attributes the loss of the authoritative route to missing coverage — the degradation is visible, not silent.

---

### Edge Cases

- **Thin exposure**: a level or cell has too few observations to establish whether the raise distribution separates. The result must fall back to the not-fitted or shrunk-toward-prior path rather than reading noise as structure.
- **No compensation change recorded**: employees whose compensation is identical across snapshots (frozen pay, missing data). These contribute no evidence about promotion and must not be counted in a way that deflates the rate.
- **Off-cycle adjustments**: raises far outside any plausible ordinary or promotion range (market adjustments, corrections, part-time to full-time changes). These must not be absorbed into either component.
- **Pay cuts and zero raises**: negative compensation growth cannot be a promotion under any reading, but must not be silently dropped from exposure.
- **Highest job level**: employees already at the top level cannot be promoted. Their raises are all ordinary and must not be attributed to a promotion component.
- **Client whose promotion increase happens to equal their ordinary increase**: genuinely unidentifiable. Must resolve to not-fitted, not to a coin flip.
- **Exposure-coverage gate sits exactly at the boundary**: the separating levels cover precisely the threshold share of exposure. The comparison must be defined so the outcome is deterministic, not dependent on floating-point noise.
- **A level with no employees at all**: contributes no exposure and must neither separate nor count against the coverage gate.
- **A threshold set to a nonsensical value** (negative, above 100%, or zero): must be rejected at the point of entry with a clear message, not silently clamped into a fit that then looks legitimate.
- **Job-level column present but sparsely populated**: coverage lands just either side of the threshold. The routing decision must be deterministic at the boundary, and the report must make the near-miss visible so the analyst can see how close the run came to the other route.
- **Job level present in one snapshot but not the next**: a transition can only be directly measured with a level at both ends. These count against coverage and are excluded from promotion exposure when the authoritative route is taken.
- **Job-level column present but constant for every employee across all years**: coverage is complete, yet no promotion is ever observable. The result is a measured rate of zero, which must be distinguished in the report from a rate that could not be fitted.
- **Two-snapshot minimum**: only one transition year of evidence. Must still produce either a fit with honest exposure counts or an explicit not-fitted result.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the census carries an explicit job-level column populated at or above the coverage threshold, the system MUST continue to measure promotions directly from observed level moves, unchanged from current behavior. A sufficiently populated column is always authoritative.
- **FR-001a**: The system MUST decide whether a job-level column is authoritative by its **coverage** — the share of experienced exposure carrying a level on both snapshots of a transition — and not by the column's mere presence. The default threshold is 95% of experienced exposure.
- **FR-001b**: When coverage is at or above the threshold, transitions lacking a level MUST be excluded from promotion exposure rather than silently band-derived. Excluding them MUST NOT remove them from termination exposure or any other fit.
- **FR-001c**: When coverage is below the threshold, the job-level column MUST be ignored for promotion classification and the estimated path used instead. A partially populated column MUST NOT produce a fit that mixes directly-measured and band-derived promotions without saying so.
- **FR-001d**: The report MUST state the observed coverage and which route it selected, on every run where a job-level column is present at all.
- **FR-002**: When the census does not carry an explicit job-level column, the system MUST NOT report a promotion rate derived solely from compensation-band crossings.
- **FR-003**: When the census does not carry an explicit job-level column, the system MUST estimate the promotion rate by separating promotion-sized raises from ordinary-raise behavior in the observed compensation-growth distribution, without defining promotion in terms of a merit rate measured off the same classification.
- **FR-003a**: The estimated promotion rate MUST be resolved per job level, and each transition MUST then carry a promotion weight derived from that estimate, so that the age and tenure adjustments are fitted from the same evidence the directly-measured path uses.
- **FR-003b**: A parameter pack produced from an estimated promotion rate MUST have the same shape as one produced from a directly-measured rate — the same hazard seed data covering base rate, age adjustments, and tenure adjustments. No consumer of a parameter pack may need to distinguish the two.
- **FR-004**: The system MUST determine, **per job level**, whether the observed data supports that separation. A level that separates contributes its estimated rate; a level that does not retains its configured default rate and is marked as such.
- **FR-004a**: The system MUST report the promotion hazard as not fitted overall — retaining the configured default throughout — when the levels that separated cover less than half of the experienced exposure. A hazard resting on a small corner of the population MUST NOT be presented as fitted.
- **FR-004b**: When the promotion hazard is fitted overall but some levels did not separate, the report MUST name those levels and state that they retain their default, so partial coverage is never mistaken for full coverage.
- **FR-005**: The fit report MUST state, for every run, which of three states the promotion hazard is in: measured directly from an explicit job-level column; estimated from the raise distribution; or not fitted with the default retained.
- **FR-006**: When the promotion hazard is estimated from the raise distribution, the report MUST present the evidence behind it — exposure, estimated event count, and the degree of separation observed — at the same level of detail as the existing hazard evidence tables.
- **FR-007**: When the promotion hazard is not fitted, the system MUST list it among the parameters that could not be fitted, with a plain-language reason, alongside the existing entries for cost-of-living and the level-factor constants.
- **FR-008**: The merit estimate MUST be computed as a promotion-weighted median compensation growth over all continued employees, where each transition's weight reflects how likely it is to have been an ordinary raise rather than a promotion. Probable promotions are down-weighted, not excluded outright.
- **FR-008a**: FR-008 MUST apply on every path — whether the promotion hazard was directly measured, estimated, or not fitted. There is one merit definition, not a per-path variant. On the directly-measured path the weights are the observed promoted flag, reproducing today's ex-promotions behavior.
- **FR-008b**: When the promotion hazard is not fitted, merit MUST still be fitted, and the report MUST state that the merit weighting could not be sharpened by a usable promotion classification, so the analyst can judge how much promotion contamination may remain.
- **FR-009**: A parameter pack in which the promotion hazard was not fitted MUST remain a valid, runnable pack — the configured default promotion hazard is carried forward and the simulation runs normally.
- **FR-010**: The provenance recorded for a simulation run driven by a parameter pack MUST make it possible to determine whether the promotion hazard in that pack was fitted or defaulted.
- **FR-011**: Anonymizing a census MUST preserve an explicit job-level column present in the source.
- **FR-012**: The existing warning about level derivation MUST be replaced by wording that matches the new behavior. The system MUST NOT continue to emit an inflated promotion number described as an upper bound.
- **FR-013**: The graded recovery test MUST cover the no-job-level case, asserting recovery of both the promotion rate and the merit rate against known truth, and MUST also assert the not-fitted outcome for a population where separation is genuinely impossible.
- **FR-014**: Fitting a promotion rate MUST NOT require any census column the fitter does not already accept. No new client data requirement is introduced.
- **FR-015**: The job-level coverage threshold (FR-001a) and the exposure-coverage gate (FR-004a) MUST be adjustable by the analyst at fit time, alongside the existing minimum-exposure and credibility controls.
- **FR-016**: The per-level separation test itself MUST NOT be adjustable. Its strictness is a property of the method, not a per-engagement setting.
- **FR-017**: When either adjustable threshold is set away from its default, the system MUST record the value used in both the fit report and the parameter pack's provenance, so a reviewer can see that a threshold was moved and to what.

### Key Entities

- **Census snapshot**: one annual point-in-time roster of employees with compensation, hire date, birth date, and optionally an explicit job level. Two to five consecutive snapshots form a history.
- **Job-level coverage**: the share of experienced exposure whose transitions carry an explicit job level at both ends. Determines whether the column is treated as authoritative.
- **Transition**: one employee observed across two consecutive snapshots, carrying their prior job level, prior and later compensation, derived compensation growth, and outcome flags (continued, terminated, promoted).
- **Promotion classification state**: which of the three states (directly measured / estimated / not fitted) produced the promotion result for a given run, plus the evidence supporting it. On the estimated path it also carries a per-level separation verdict and the share of experienced exposure the separating levels cover.
- **Promotion hazard fit**: the fitted promotion rate decomposed the way the simulator consumes it — a base rate with age, tenure, and level adjustments — carrying its exposure, event count, and credibility. Identical in shape whether the rate was directly measured or estimated; on the estimated path the event count is an expected count derived from per-transition promotion weights rather than a whole-number tally.
- **Promotion weight**: per transition, the likelihood that it was a promotion rather than an ordinary raise. It is 0 or 1 on the directly-measured path and a fraction on the estimated path. Aggregated over a cell it gives the expected promotion events the age and tenure adjustments are fitted from; inverted, it gives the merit weighting of FR-008.
- **Merit estimate**: the per-level ordinary raise rate, measured as a promotion-weighted median over all continued employees, carrying the effective exposure that weighting produced.
- **Unfittable parameter**: a named parameter the data cannot speak to, with a reason and the retained default. Promotion may now join this set.
- **Parameter pack**: the fitted artifact — hazard seed data, other seed data, a configuration fragment, and the fit report — consumed by a simulation run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a census history with a known 6% promotion rate and no job-level column, the fitted promotion rate is within 1.5 percentage points of the truth — the same tolerance termination already meets — replacing today's 9.1% (3 snapshots) / 15.2% (5 snapshots).
- **SC-001a**: The fitted promotion rate no longer degrades as the history lengthens. Recovery at 5 snapshots is at least as accurate as at 3, reversing the current behavior where more client data yields a worse estimate.
- **SC-002**: On the same history, the fitted per-level merit rate is within 1 percentage point of the truth, closing the coupled merit distortion.
- **SC-003**: On a census history where promotion and ordinary raises genuinely overlap at every level, the run reports the promotion hazard as not fitted in 100% of cases, and never emits an estimated rate.
- **SC-003a**: On a census history where only some levels separate, every level's status in the report matches its true separability, and the overall fitted/not-fitted verdict matches the exposure-coverage rule in 100% of cases.
- **SC-004**: Every fit run states its promotion classification state unambiguously; an analyst reading only the fit report can determine in under one minute whether the promotion number is measured, estimated, or defaulted.
- **SC-005**: Promotion-rate accuracy on a census that carries an explicit job-level column is unchanged from the current release — no regression on the clean path.
- **SC-006**: A parameter pack whose promotion hazard was not fitted completes a multi-year simulation successfully, with no additional analyst intervention required.
- **SC-007**: A census carrying a job-level column retains that column through anonymization in 100% of cases.
- **SC-007a**: A census whose job-level column is populated below the coverage threshold never produces a directly-measured promotion rate, and the coverage figure appears in the report on every run where the column exists.
- **SC-008**: No client engagement requires additional census columns beyond those the fitter already accepts.
- **SC-009**: A fit run with a threshold moved off its default is identifiable as such from the report and from the pack's provenance alone, without access to the command that produced it, in 100% of cases.

## Assumptions

- The simulator's own model of raises — an ordinary raise built from a cost-of-living component plus a per-level merit component, and a separately configured promotion increase — is a reasonable description of how client compensation actually moves. Separating promotion from merit relies on this.
- Client promotion increases are materially larger than client ordinary increases in the typical case. Where they are not, the honest outcome is not-fitted, and that is accepted (see FR-004).
- The existing credibility-shrinkage and minimum-exposure machinery continues to govern thin cells; this feature changes what counts as a promotion event, not how thin evidence is handled.
- Cost-of-living remains a policy input held at its configured value and is not fitted; this feature does not change that.
- The compensation-banding rule used to derive job level stays as it is. The bands remain the correct grouping for hazard cells; only their use as a *promotion signal* is at issue.
- The synthetic grading harness is the authority for accuracy claims, since real client histories carry no ground truth.
- The tolerance figures in SC-001 and SC-002 are proposed against the existing termination tolerance; they should be confirmed once the chosen estimation approach is graded.
- The two threshold defaults — 95% job-level coverage and half of exposure for the coverage gate — are starting points chosen for defensibility, not measured optima. Because both are analyst-adjustable (FR-015), a default that proves slightly wrong is recoverable per engagement rather than blocking.
- Analysts are trusted not to tune the adjustable thresholds until a number appears. FR-017's provenance recording is the control on this, not a hard limit.

## Out of Scope

- Changing how job level is derived from compensation for any purpose other than promotion detection.
- Fitting the cost-of-living rate, the level-discount or level-dampener constants, or match response — these remain explicitly unfittable.
- Changing the simulator's own promotion or compensation logic. This feature changes only what the fitter infers from history.
- Any change to how parameter packs are applied to a simulation run.
- Any user interface work in the web studio.

## Dependencies

- The parameter fitter and its current level-derivation warning (issue #458, PR #509).
- The synthetic census fixture with a known promotion rate and explicit job level, and the existing round-trip recovery assertions.
- The census anonymizer (issue #449), for the column-preservation requirement.
- The run provenance metadata that records parameter-pack identity, for the fitted-versus-defaulted requirement.
