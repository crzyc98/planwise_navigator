# Feature Specification: NDT 401(a)(4) General Test & 415 Annual Additions Limit Test

**Feature Branch**: `051-ndt-401a4-415-tests`
**Created**: 2026-02-19
**Status**: Draft
**Input**: User description: "Add 401(a)(4) general nondiscrimination test and 415 annual additions limit test to the NDT suite"

## Clarifications

### Session 2026-02-19

- Q: Which compensation should the 415 test use for the "100% of compensation" rule? → A: Uncapped gross compensation (W-2 pay / "415 compensation") per IRS rules, not 401(a)(17)-capped plan compensation.
- Q: How should the 401(a)(4) general test determine pass/fail when the ratio test fails? → A: Midpoint comparison — NHCE median contribution rate must be at least 70% of HCE median rate.
- Q: Should forfeitures allocated to participants be included in 415 annual additions? → A: No — forfeitures excluded due to data availability constraint. Forfeiture allocation data is not currently ingested via the participant census file. Known limitation; to be revisited when forfeiture data is available.
- Q: Should the 401(a)(4) test include employer match in the contribution rate, or NEC only? → A: Configurable per request. Default to NEC-only (since match is already tested via ACP), with option to include match for plans that require combined testing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run 401(a)(4) General Nondiscrimination Test (Priority: P1)

A plan administrator runs the 401(a)(4) general test to verify that the plan's employer contributions (non-elective contributions and, where applicable, matching contributions) do not disproportionately favor highly compensated employees. The system calculates each participant's employer contribution rate, groups participants by HCE/NHCE status, computes group averages, and applies the IRS ratio test. If the ratio test fails, the system runs the general test by analyzing the distribution of benefits across rate groups to determine whether NHCEs are disproportionately excluded from higher contribution tiers.

**Why this priority**: The 401(a)(4) test is a core IRS compliance requirement for qualified retirement plans. Failure can result in plan disqualification. It directly measures whether employer contributions are allocated fairly.

**Independent Test**: Can be fully tested by loading a scenario with known employer NEC and match amounts, running the test, and verifying pass/fail against hand-calculated expected results.

**Acceptance Scenarios**:

1. **Given** a completed simulation with employer NEC and match contributions calculated, **When** the administrator runs the 401(a)(4) test for a scenario and year, **Then** the system returns pass/fail, HCE average contribution rate, NHCE average contribution rate, the NHCE-to-HCE ratio, and margin to the passing threshold.
2. **Given** a plan where the HCE average employer contribution rate is 8% and the NHCE average is 6%, **When** the 401(a)(4) ratio test is applied, **Then** the ratio is 75% (6%/8%), which exceeds 70%, so the test passes with a margin of +5 percentage points.
3. **Given** a plan where the ratio test fails (NHCE average is less than 70% of HCE average), **When** the general test is triggered, **Then** the system compares the NHCE median contribution rate to the HCE median contribution rate and passes if the NHCE median is at least 70% of the HCE median.
4. **Given** a plan with service-based NEC (graded by years of service) where HCE employees have significantly longer average tenure than NHCEs, **When** the 401(a)(4) test runs, **Then** the system flags the plan as "elevated 401(a)(4) risk" due to the combination of service-based formula and tenure skew.
5. **Given** the administrator requests employee-level detail, **When** the test completes, **Then** each participant's employer contribution rate, HCE status, employer NEC amount, employer match amount, and plan compensation are visible.

---

### User Story 2 - Run 415 Annual Additions Limit Test (Priority: P1)

A plan administrator runs the Section 415 annual additions test to verify that no participant's total annual additions exceed the IRS limit. For each participant, the system sums employee elective deferrals, employer match contributions, and employer non-elective contributions, then compares the total to the lesser of the dollar limit (from published IRS limits) or 100% of the participant's compensation. The system flags participants who exceed the limit or approach it within a configurable warning threshold.

**Why this priority**: Section 415 violations require corrective distributions and can trigger plan disqualification. This is a per-participant compliance check that directly prevents regulatory breaches.

**Independent Test**: Can be fully tested by loading a scenario with known contribution amounts, running the test, and verifying each participant's total additions against the IRS limit.

**Acceptance Scenarios**:

1. **Given** a completed simulation with employee deferrals, employer match, and employer NEC calculated, **When** the administrator runs the 415 test for a scenario and year, **Then** the system returns a per-participant breakdown showing total annual additions, the applicable 415 limit, headroom remaining, and a pass/fail status.
2. **Given** a participant with $25,000 in deferrals, $15,000 in employer match, and $30,000 in employer NEC (total $70,000) in a year where the 415 dollar limit is $69,000, **When** the 415 test runs, **Then** the participant is flagged as a breach with $1,000 over the limit.
3. **Given** a participant earning $60,000 with $20,000 in total additions, **When** the 415 test applies the 100%-of-compensation rule, **Then** the applicable limit is $60,000 (lesser of $69,000 or $60,000) and the participant passes with $40,000 headroom.
4. **Given** the configurable warning threshold is set to 95%, **When** a participant's total additions reach 96% of their 415 limit, **Then** the participant is flagged as "at risk" even though they have not breached the limit.
5. **Given** a plan-level summary is requested, **When** the 415 test completes, **Then** the system shows overall pass/fail (pass only if zero breaches), the count of breached participants, the count of at-risk participants, and the maximum utilization percentage across all participants.

---

### User Story 3 - Compare 401(a)(4) and 415 Results Across Scenarios (Priority: P2)

A benefits consultant compares 401(a)(4) and 415 test results across multiple scenarios (e.g., baseline vs. high-growth) to evaluate how different plan designs or workforce compositions affect compliance outcomes.

**Why this priority**: Scenario comparison is a natural extension once individual tests work. It enables proactive plan design optimization.

**Independent Test**: Can be tested by running both tests against two scenarios and verifying the comparison output displays side-by-side results.

**Acceptance Scenarios**:

1. **Given** two completed scenarios with different plan designs, **When** the administrator runs 401(a)(4) tests for both in a single request, **Then** the results are returned side-by-side with each scenario's pass/fail, ratios, and margins.
2. **Given** two completed scenarios, **When** the administrator runs 415 tests for both, **Then** the results show each scenario's breach count, at-risk count, and maximum utilization percentage.

---

### Edge Cases

- What happens when no employer NEC or match contributions exist for a scenario? The 401(a)(4) test should return an informational result indicating no employer contributions to test (not an error).
- What happens when all participants are HCEs or all are NHCEs? The 401(a)(4) test should handle this gracefully: all-HCE returns an informational message (no NHCE comparison group); all-NHCE auto-passes.
- What happens when a participant has zero compensation? Both tests should exclude participants with zero compensation and note them in the excluded count.
- What happens when the IRS limits data does not contain the requested year? The system should return a clear error indicating missing IRS limit data for the requested year.
- What happens when the warning threshold is set to 100%? Only actual breaches are flagged; no "at risk" warnings are generated.
- What happens when a participant has catch-up contributions? Catch-up contributions (including SECURE 2.0 super catch-up for ages 60-63) are excluded from the 415 annual additions calculation per IRS rules.
- What happens when a plan allocates forfeitures directly to participant accounts? Forfeitures are not included in the 415 calculation due to a data availability constraint. The system should document this limitation in test output so administrators are aware that 415 results may understate total annual additions for such plans.

## Requirements *(mandatory)*

### Functional Requirements

#### 401(a)(4) General Test

- **FR-001**: System MUST calculate each participant's employer contribution rate as employer NEC divided by plan compensation (subject to the 401(a)(17) compensation limit) by default. When the "include match" option is enabled, the rate is (employer NEC + employer match) divided by plan compensation. The default is NEC-only because employer match is already tested separately via ACP.
- **FR-002**: System MUST classify participants into HCE and NHCE groups using the same prior-year compensation-based determination already used by the ACP test.
- **FR-003**: System MUST compute the average employer contribution rate for HCE and NHCE groups separately.
- **FR-004**: System MUST apply the ratio test: the plan passes if the NHCE average rate is at least 70% of the HCE average rate.
- **FR-005**: System MUST, when the ratio test fails, perform the general test using a midpoint comparison: the NHCE median contribution rate must be at least 70% of the HCE median contribution rate. The test passes if this threshold is met; otherwise, it fails.
- **FR-006**: System MUST flag plans where the employer NEC formula is service-based ("graded by service") AND the average HCE tenure exceeds the average NHCE tenure by a configurable margin (default: 3 years), indicating elevated 401(a)(4) risk.
- **FR-007**: System MUST output: overall pass/fail, HCE average rate, NHCE average rate, NHCE-to-HCE ratio, margin to passing threshold, applied test name (ratio or general), and service-based risk flag.
- **FR-008**: System MUST support optional employee-level detail showing each participant's employer contribution rate, NEC amount, match amount (when include-match is enabled), plan compensation, HCE status, and years of service.

#### 415 Annual Additions Limit Test

- **FR-009**: System MUST calculate each participant's total annual additions as: employee elective deferrals (excluding catch-up contributions) + employer match + employer NEC. Forfeitures allocated to participant accounts are excluded from this calculation due to a data availability constraint (forfeiture allocation data is not currently ingested via the participant census file). This is a known limitation; plans that allocate forfeitures directly to participant accounts may understate total annual additions.
- **FR-010**: System MUST determine each participant's applicable 415 limit as the lesser of the IRS dollar limit for the test year or 100% of the participant's uncapped gross compensation ("415 compensation" / W-2 pay), which is not subject to the 401(a)(17) cap.
- **FR-011**: System MUST retrieve the IRS 415 annual additions dollar limit from the centralized IRS limits data for the applicable year.
- **FR-012**: System MUST flag any participant whose total annual additions exceed their applicable 415 limit as a "breach."
- **FR-013**: System MUST flag any participant whose total annual additions equal or exceed a configurable warning threshold (default 95%) of their applicable 415 limit as "at risk."
- **FR-014**: System MUST output per-participant: pass/fail/at-risk status, total annual additions, applicable 415 limit, headroom (limit minus additions), and utilization percentage (additions divided by limit).
- **FR-015**: System MUST output plan-level summary: overall pass/fail (fail if any breaches), breach count, at-risk count, and maximum utilization percentage across all participants.

#### Shared Requirements

- **FR-016**: Both tests MUST consume the same participant census and contribution inputs already used by the existing ADP and ACP tests.
- **FR-017**: Both tests MUST follow the same output structure and patterns as existing NDT tests (pass/fail, margin, optional participant-level detail).
- **FR-018**: Both tests MUST support multi-scenario comparison, allowing results from multiple scenarios to be returned in a single request.
- **FR-019**: Both tests MUST be accessible through the same interface patterns as the existing ACP test (same workspace/scenario/year selection flow).

### Key Entities

- **Employer Contribution Rate**: A participant's employer NEC (or NEC + match when include-match is enabled) divided by plan compensation. The core metric for 401(a)(4) testing.
- **Annual Additions**: The sum of all contributions allocated to a participant's account in a limitation year: employee deferrals (excluding catch-up), employer match, and employer NEC. The core metric for 415 testing.
- **415 Limit**: The IRS maximum annual additions allowed per participant, defined as the lesser of a published dollar amount or 100% of uncapped gross compensation ("415 compensation").
- **Rate Group**: A band of contribution rates used in the 401(a)(4) general test to analyze benefit distribution across HCE and NHCE populations.
- **Service-Based Risk Flag**: An indicator that a plan's NEC formula varies by service and HCE tenure skews meaningfully higher than NHCE tenure, creating elevated nondiscrimination risk.

## Assumptions

- The existing workforce snapshot contains or can be joined to obtain: employee elective deferrals, employer match amounts, employer NEC amounts, plan compensation (prorated and capped), and years of service.
- HCE determination logic (prior-year compensation with fallback) is identical to the existing ACP test and will be reused directly.
- The 415 annual additions dollar limit will be available from the same IRS limits data source used for other IRS thresholds (HCE threshold, 402(g) limits, etc.).
- Catch-up contributions (age 50+ and SECURE 2.0 ages 60-63) are already tracked separately from base elective deferrals and can be excluded from the 415 calculation.
- The "meaningful margin" for HCE vs. NHCE tenure skew in the service-based risk flag defaults to HCE average tenure exceeding NHCE average tenure by more than 3 years. This is a configurable threshold.
- The 401(a)(4) general test (when the ratio test fails) uses a simplified midpoint comparison (NHCE median vs. HCE median at 70% threshold) rather than the full IRS cross-testing methodology, which is sufficient for plan monitoring and early warning purposes.
- The configurable warning threshold for the 415 test defaults to 95% and is adjustable per request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Plan administrators can run the 401(a)(4) general test for any completed scenario and year and receive a pass/fail result with supporting metrics within the same response time as the existing ACP test.
- **SC-002**: Plan administrators can run the 415 annual additions test for any completed scenario and year and receive per-participant results identifying all breaches and at-risk participants.
- **SC-003**: 100% of known 415 breaches in test data are correctly identified (zero false negatives on limit violations).
- **SC-004**: The 401(a)(4) ratio test produces correct pass/fail results when validated against hand-calculated examples for at least 5 distinct plan configurations (flat NEC, service-based NEC, NEC + match, high HCE concentration, balanced workforce).
- **SC-005**: Service-based risk flags correctly identify plans where the combination of graded NEC and tenure skew creates elevated nondiscrimination risk.
- **SC-006**: Both tests support multi-scenario comparison, enabling side-by-side compliance analysis across at least 2 scenarios in a single request.
- **SC-007**: Both tests follow identical output patterns to the existing ACP test, requiring no new learning curve for users already familiar with the NDT suite.
