# Feature Specification: Edge-Configuration Regression Matrix

**Feature Branch**: `124-edge-config-regression-matrix`
**Created**: 2026-07-24
**Status**: Draft
**Input**: Reduced GitHub issue #438, building on PR #452's multi-year invariant and determinism suite

## Overview

Extend the existing simulation safety net with a small set of configuration-specific regression scenarios. PR #452 verifies that a representative configuration remains internally consistent and deterministic across multiple years; this feature verifies that high-risk configuration combinations produce the intended business behavior.

The matrix is intentionally focused rather than exhaustive. It will cover four configuration combinations that have historically produced silent or cross-feature regressions: broad auto-enrollment with a hire-date cutoff, new-hire eligibility suppression interacting with auto-enrollment, tenure-graded employer matching, and auto-escalation with a low cap. Each case uses an isolated short simulation and targeted behavioral assertions. Full-output snapshots and broad combinatorial coverage are out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configuration branches are protected from regression (Priority: P1)

A developer changes enrollment, eligibility, matching, or escalation logic. The pre-merge checks exercise the focused edge configurations and report a failure when a configuration-specific expectation no longer holds, while the existing PR #452 invariants continue to protect general cross-year correctness.

**Why this priority**: The representative configuration covered by PR #452 cannot expose bugs that occur only when a feature switch or cross-feature combination changes. These are the configurations most likely to affect client results while still appearing healthy under defaults.

**Independent Test**: Run the focused matrix against a known-good revision, then deliberately break one configuration-specific rule and confirm only the relevant case reports the affected expectation and scenario.

**Acceptance Scenarios**:

1. **Given** a correct simulation revision, **When** the focused edge-configuration matrix runs, **Then** every case passes with its named behavioral assertions.
2. **Given** a change that ignores the hire-date cutoff for broad auto-enrollment, **When** the matrix runs, **Then** the broad-auto-enrollment case fails and identifies the affected eligibility boundary.
3. **Given** a change that enrolls new hires despite an eligibility-suppression rule, **When** the matrix runs, **Then** the suppression/auto-enrollment case fails and identifies the conflicting population.
4. **Given** a change that applies one match tier to all tenures, **When** the matrix runs, **Then** the tenure-graded matching case fails and identifies the expected tier distinction.
5. **Given** a change that allows auto-escalation above its configured low cap, **When** the matrix runs, **Then** the low-cap case fails and identifies the violating rate.

### User Story 2 - Analysts can trust targeted plan behavior (Priority: P2)

An analyst uses one of the supported edge configurations and receives results that reflect the configured enrollment, eligibility, matching, and escalation rules. The regression suite protects those outcomes without requiring the analyst to compare entire simulation databases or snapshots.

**Why this priority**: The value of the matrix is not merely test coverage; it is confidence that high-impact plan settings continue to mean what the configuration says they mean.

**Independent Test**: Run each scenario with a fixture population designed to cross the relevant boundary, then verify the targeted counts, statuses, rates, or contribution amounts described by that scenario.

**Acceptance Scenarios**:

1. **Given** eligible employees both before and after the configured hire-date cutoff, **When** broad auto-enrollment runs, **Then** only employees within the configured enrollment boundary are enrolled automatically.
2. **Given** new hires subject to an eligibility-suppression rule and other eligible employees, **When** enrollment processing runs, **Then** suppressed new hires remain unenrolled while eligible employees follow the configured auto-enrollment behavior.
3. **Given** employees with different completed service tenures and a tenure-graded match schedule, **When** employer matching runs, **Then** each employee receives the tier corresponding to their service tenure.
4. **Given** enrolled employees with auto-escalation enabled and a low configured cap, **When** escalation runs, **Then** no resulting deferral rate exceeds the cap.

### User Story 3 - The matrix is safe and practical to run (Priority: P3)

A developer runs the focused matrix locally or reviews it in pre-merge checks. Each case uses isolated simulation state, produces actionable diagnostics, and completes within a bounded time without modifying shared development artifacts.

**Why this priority**: Configuration coverage only helps if it is repeatable and affordable enough to run regularly. Isolation also prevents a regression test from creating misleading results through stale shared state.

**Independent Test**: Run the documented matrix command twice, confirm identical pass/fail results and targeted diagnostics, and verify that the shared development database is unchanged.

**Acceptance Scenarios**:

1. **Given** a clean checkout and the supported development environment, **When** the documented matrix command runs, **Then** all four cases complete within the agreed local time budget and report one result per case.
2. **Given** one case fails, **When** the developer reads the failure, **Then** it names the case, configuration boundary, expected behavior, observed behavior, and affected sample rows or employees.
3. **Given** two matrix runs execute concurrently, **When** both complete, **Then** they do not share or overwrite simulation state and produce equivalent results.

### Edge Cases

- A case has no employees crossing its target boundary: the case must fail fixture setup or report an explicit insufficient-population diagnostic rather than pass vacuously.
- A configuration block is omitted and receives its documented default: the case must assert the effective default where that default is part of the scenario.
- A configuration override conflicts with a base setting: the case must assert the effective override value and identify it in diagnostics.
- A low-cap escalation case begins with employees already at, above, or below the cap: the assertion must distinguish valid unchanged rates from invalid post-escalation rates.
- A short simulation produces zero events of an expected type for a valid reason: the fixture or expectation must make the reason explicit so the test does not silently lose coverage.
- A simulation fails before behavioral assertions can run: the result must report the simulation failure separately from a failed business-rule assertion.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a focused regression matrix containing exactly four initial scenarios: broad auto-enrollment with an early hire-date cutoff; new-hire eligibility suppression interacting with auto-enrollment; tenure-graded employer matching; and auto-escalation with a low cap.
- **FR-002**: Each scenario MUST use a small, purpose-built fixture population that includes employees on both sides of the relevant configuration boundary.
- **FR-003**: Each scenario MUST run as a short multi-year simulation sufficient to exercise the configured behavior and its immediate state transition, with the exact horizon documented alongside the scenario.
- **FR-004**: Each scenario MUST run in isolated simulation state and MUST NOT read from or write to the shared development database.
- **FR-005**: The broad-auto-enrollment scenario MUST verify that automatic enrollment respects the configured hire-date cutoff and does not enroll employees outside that boundary.
- **FR-006**: The eligibility-suppression scenario MUST verify that suppressed new hires remain excluded from enrollment while unaffected eligible employees follow the configured auto-enrollment behavior.
- **FR-007**: The tenure-graded matching scenario MUST verify that employees in distinct service-tenure bands receive the corresponding configured employer-match treatment.
- **FR-008**: The low-cap escalation scenario MUST verify that no resulting deferral rate exceeds the configured auto-escalation cap, including when starting rates are below, equal to, or above the cap.
- **FR-009**: Matrix assertions MUST be targeted to configuration-specific business outcomes such as enrollment status, eligibility status, match tier, contribution amount, or deferral rate; the matrix MUST NOT depend on byte-identical full-output snapshots.
- **FR-010**: The matrix MUST reuse the existing multi-year simulation and invariant-test support established by PR #452 wherever applicable, without duplicating general determinism or cross-year invariant checks.
- **FR-011**: Each scenario MUST produce a named, actionable diagnostic that includes the scenario, configuration boundary, expected result, observed result, and a bounded sample of affected employees or rows when it fails.
- **FR-012**: The matrix MUST distinguish simulation execution failures from business-rule assertion failures and MUST NOT evaluate behavioral assertions against a partially built simulation.
- **FR-013**: The matrix MUST be runnable through one documented local command and MUST execute in pre-merge validation with a bounded runtime appropriate for regular development use.
- **FR-014**: Adding a new configuration-dependent regression fix MUST have a documented path for adding a corresponding matrix scenario or targeted assertion without changing the semantics of existing cases.

### Key Entities

- **Edge-configuration scenario**: A named configuration and fixture population designed to exercise one high-risk interaction or boundary, with expected behavioral outcomes.
- **Targeted behavioral assertion**: A testable expectation about enrollment, eligibility, employer matching, contribution amounts, or deferral rates for an edge-configuration scenario.
- **Scenario diagnostic**: The failure information needed to identify the configuration case, expected and observed behavior, and affected sample records.
- **Isolated simulation run**: A disposable run-specific result set used for one matrix case, kept separate from all other cases and shared development artifacts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four initial edge-configuration scenarios pass on the known-good revision and fail when their corresponding business rule is deliberately violated.
- **SC-002**: Each scenario exercises at least one employee or record on both sides of its relevant configuration boundary, verified by fixture validation before simulation assertions run.
- **SC-003**: The matrix produces zero false passes for the four seeded regression mutations: cutoff bypass, eligibility-suppression bypass, tenure-tier flattening, and cap overflow.
- **SC-004**: A complete local matrix run finishes within 5 minutes on a typical development laptop and does not modify the shared development database.
- **SC-005**: 100% of failed cases identify the scenario and include expected-versus-observed values plus a bounded affected-record sample.
- **SC-006**: Two concurrent matrix runs produce equivalent case results without database or artifact collisions.
- **SC-007**: The matrix adds configuration-specific protection while leaving PR #452's existing invariant and determinism suite as the single source of coverage for general cross-year consistency and same-seed reproducibility.

## Assumptions

- PR #452's invariant, determinism, fixture, and isolated-run support are available and remain responsible for general simulation correctness; this feature adds only configuration-specific behavior checks.
- The first implementation uses four scenarios from issue #438. Additional configurations are added only when a concrete risk or regression justifies them.
- A short horizon of one or two projection years is sufficient for the initial cases; the exact horizon may vary by scenario if documented and justified by the behavior under test.
- Assertions use stable business outcomes and tolerances rather than complete event or snapshot equality. Deterministic repeated-run behavior remains covered by PR #452.
- The matrix runs against explicitly isolated databases and never treats the shared development database as validation ground truth.
- The initial matrix is intended for regular pre-merge validation. If runtime exceeds the stated budget, the scenarios should be reduced or split by responsibility before weakening the assertions.

## Dependencies

- PR #452 / Feature 113 provides the existing multi-year simulation harness, isolated-run conventions, diagnostics, and general invariant/determinism coverage.
- Existing configuration models and business rules for auto-enrollment, eligibility suppression, tenure-graded matching, and auto-escalation provide the behavior being protected.
- Issue #438 is superseded by this reduced specification once the feature is implemented; the original broad six-case proposal is intentionally narrowed.

## Out of Scope

- Exhaustive combinations of all configuration switches.
- Full-output snapshots, byte-for-byte scenario comparisons, or a second determinism framework.
- New enrollment, eligibility, matching, or escalation behavior.
- New user-facing configuration fields or Studio authoring surfaces.
- The zero/negative growth, custom demographic, and custom compensation cases from the original #438 proposal unless a later regression justifies adding them.
