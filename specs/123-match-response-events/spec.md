# Feature Specification: Match-Response Deferral Events in Client/Studio Simulations

**Feature Branch**: `123-match-response-events`
**Created**: 2026-07-23
**Status**: Draft
**Input**: GitHub issue #451 — "Deferral match-response events are absent from client simulations"

## Overview

Match-responsive deferral adjustments (feature 058) generate one-time, first-year events when active, enrolled participants deferring **below** the match-maximizing rate behaviorally increase their deferrals to capture "free money." That behavior is validated on the CLI/default configuration path, but it is **absent from client simulations produced through PlanAlign Studio / workspace scenarios**: their yearly event output contains no `deferral_match_response` records even when the modeling assumptions intend them.

The suspected cause is a configuration-path gap: the enable flag does not survive resolution from a Studio/workspace scenario to the simulation, and the typed configuration defaults the feature to **disabled** whenever its block is absent — so the feature silently does nothing and produces no diagnostic signal. This feature makes the configured behavior actually run for client/Studio scenarios, makes the enabled/disabled state visible in the resolved configuration, and adds regression coverage for the Studio configuration path and the fact-table integration.

This is a correctness/integration fix, **not** a re-design of the feature-058 behavioral model (participation rates, gap-closing splits, and match-mode math are unchanged).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configured match response actually runs for a client scenario (Priority: P1)

An analyst configures a PlanAlign Studio / workspace scenario for a client with match-responsive deferral adjustments enabled, using a plan whose census includes active, enrolled participants deferring below the match-maximizing rate. When they run the simulation, the first projection year produces the expected match-response deferral events, exactly as the default/CLI path would.

**Why this priority**: This is the reported defect and the core value — a documented, configured behavior currently produces no output for client scenarios, silently understating deferrals, contributions, and match cost. Without this, the feature is effectively unavailable to Studio users.

**Independent Test**: Run a Studio-shaped scenario configuration with the feature enabled and a census containing eligible below-threshold active enrolled participants; confirm first-year match-response events appear in the authoritative yearly events output. Delivers the fix on its own.

**Acceptance Scenarios**:

1. **Given** a Studio/workspace scenario with match response enabled and active, enrolled participants deferring below the match-maximizing rate, **When** the simulation runs, **Then** the first projection year's yearly events output contains one or more `deferral_match_response` events.
2. **Given** such a run, **When** the generated events are inspected, **Then** each carries `event_type = 'deferral_match_response'`, `event_category = 'match_response'`, and `event_details` beginning with `Match response:`.
3. **Given** an eligible below-threshold population under the current upward assumptions, **When** the first year is generated, **Then** approximately 40% of that population responds, and the count is deterministic for a fixed random seed.
4. **Given** the identical scenario run through the CLI/default path and through Studio, **When** both complete, **Then** both produce match-response events consistent with the same modeling assumptions (Studio is not silently degraded).

---

### User Story 2 - Enabled/disabled state is visible in the resolved configuration (Priority: P2)

An operator diagnosing why a client run did or did not produce match-response events can determine, from the resolved/exported scenario configuration, whether match-responsive deferral adjustment was enabled — without reading model internals, logs, or source code.

**Why this priority**: The defect was hard to diagnose precisely because the feature fails closed (defaults to disabled when its block is absent) with no visible signal. Configuration transparency turns a silent no-op into a self-explaining state and protects against future regressions of the same class.

**Independent Test**: Resolve a scenario with the feature enabled and another with it absent/disabled; confirm the resolved configuration each simulation consumes clearly and unambiguously exposes the enabled/disabled state for both.

**Acceptance Scenarios**:

1. **Given** a scenario with match response enabled, **When** its configuration is resolved for the run, **Then** the resolved configuration clearly indicates the feature is enabled.
2. **Given** a scenario whose configuration omits the match-response block, **When** its configuration is resolved, **Then** the resolved configuration clearly indicates the feature is disabled (the documented default), rather than being silently absent.
3. **Given** the employer-match ceiling / match-maximizing rate that defines the below-threshold population, **When** the configuration is resolved, **Then** that ceiling is represented correctly so a nonempty below-threshold population can be produced when one exists in the census.

---

### User Story 3 - Correct suppression: disabled, later years, and new hires (Priority: P2)

Match-response events are generated only where the assumptions intend them: not at all when the feature is disabled, only in the first projection year, and never for current-year new hires. Enabling the feature must not over-generate events into later years or onto ineligible participants.

**Why this priority**: A fix that makes events appear is only correct if it also preserves the intended boundaries. These are explicit design constraints and existing invariants that regression coverage must protect.

**Independent Test**: Run multi-year simulations with the feature enabled and disabled and inspect match-response event counts by year and participant type.

**Acceptance Scenarios**:

1. **Given** the feature disabled, **When** the simulation runs, **Then** zero match-response events are generated in any year.
2. **Given** the feature enabled, **When** projection years after the first are generated, **Then** they contain zero match-response events.
3. **Given** the feature enabled, **When** the first year is generated, **Then** participants hired in that same year are excluded from match-response generation.

### Edge Cases

- **Feature block absent entirely**: treated as disabled (documented default); the run succeeds with zero match-response events and the resolved configuration reflects "disabled."
- **Enabled but no eligible population**: all active enrolled participants already defer at or above the match-maximizing rate — the run succeeds with zero match-response events, and this is distinguishable (via the resolved configuration showing "enabled") from the disabled case.
- **Enabled but employer-match ceiling exported as empty/zero**: no below-threshold population can form; this should be recognizable as a configuration-export problem rather than a silent absence of behavior.
- **Studio scenario overrides a base configuration**: an explicit disable in an override must win over an enabled base, and vice versa, with the resolved configuration reflecting the effective value the simulation consumed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The resolved configuration a simulation consumes MUST clearly and unambiguously expose whether match-responsive deferral adjustment is enabled, including when the source scenario omits the feature block (in which case it MUST resolve to the documented disabled default rather than being silently absent).
- **FR-002**: The Studio/workspace scenario configuration path MUST preserve the match-response enabled flag (and its governing settings) end-to-end to the simulation, without silently dropping or overriding it during resolution/merge of base and override configurations.
- **FR-003**: When the feature is enabled and one or more eligible participants exist (active, enrolled, deferring below the match-maximizing rate, and not hired in the current year), the **first** projection year MUST generate `deferral_match_response` events, and those events MUST reach the authoritative yearly events output (`fct_yearly_events`).
- **FR-004**: Each generated match-response event MUST carry `event_type = 'deferral_match_response'`, `event_category = 'match_response'`, and `event_details` beginning with the literal prefix `Match response:`.
- **FR-005**: Match-response events MUST be generated only in the first simulation year; all later projection years MUST generate zero match-response events.
- **FR-006**: Current-year new hires MUST be excluded from match-response event generation.
- **FR-007**: When the feature is disabled (explicitly or by default), the simulation MUST generate zero match-response events in every year, and results MUST otherwise match feature-disabled behavior.
- **FR-008**: Under the current upward assumptions, approximately 40% of the eligible below-threshold population MUST respond, and the responding set MUST be deterministic for a given random seed and configuration.
- **FR-009**: The employer-match ceiling / match-maximizing rate that defines the below-threshold population MUST be represented correctly in the resolved configuration so that a nonempty below-threshold population is produced whenever one exists in the census.
- **FR-010**: Automated regression coverage MUST protect (a) the Studio/workspace configuration path that carries the enabled flag to the simulation and (b) the integration of generated match-response events into the authoritative yearly events output, using a Studio-style scenario configuration with active, enrolled participants below the match ceiling.

### Key Entities *(include if feature involves data)*

- **Match-response deferral event**: A one-time, first-year record representing a participant's behavioral deferral increase toward the match-maximizing rate. Identified by `event_type = 'deferral_match_response'` and `event_category = 'match_response'`, with human-readable `event_details` prefixed `Match response:` and the audit fields defined by feature 058 (previous rate, new rate, target match-maximizing rate, response type, match mode).
- **Resolved scenario configuration**: The effective configuration a run consumes after base/override merge and resolution, including the match-response enabled flag and the employer-match ceiling. Its clarity about the enabled/disabled state is itself a requirement of this feature.
- **Eligible below-threshold population**: The set of participants that can generate match-response events in the first year — active, enrolled, deferring below the match-maximizing rate, and not hired in the current year.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a Studio/workspace scenario with the feature enabled and a census containing eligible below-threshold active enrolled participants, the first projection year's yearly events output contains at least one match-response event (currently zero).
- **SC-002**: 100% of generated match-response events carry `event_category = 'match_response'` and `event_details` beginning with `Match response:`.
- **SC-003**: The count of first-year responders equals approximately 40% of the eligible below-threshold population (within an agreed tolerance) and is identical across repeated runs with the same seed and configuration.
- **SC-004**: Projection years after the first contain zero match-response events, and runs with the feature disabled contain zero match-response events in every year.
- **SC-005**: An operator can determine whether match response was enabled for a given run solely from its resolved configuration, for both the enabled and the omitted/disabled cases, without inspecting model internals or logs.
- **SC-006**: Automated tests covering the Studio/workspace configuration path and the fact-table integration are part of the standard suite and fail if either the enabled flag is dropped in resolution or generated events do not reach the authoritative yearly events output.

## Assumptions

- The behavioral model from feature 058 (participation rates — default ~40% upward — gap-closing split, match-mode math, first-year-only timing, new-hire exclusion, deterministic-by-seed generation) is correct and unchanged; this feature only ensures it runs and is observable for client/Studio scenarios.
- Scope is the **upward, below-threshold** response described in the issue. Downward (above-threshold) response shares the same enable/resolution path and is not expected to regress, but is not the subject of the new assertions here.
- "Client simulation" refers to simulations produced through the PlanAlign Studio / workspace scenario configuration path generally, not a single named client dataset.
- "Approximately 40%" is validated against a documented tolerance or an exact expected responder count for a fixed seed and fixture census, chosen so the regression test is deterministic and not flaky.
- The authoritative first-year yearly events output is `fct_yearly_events`, consistent with the existing event-sourcing architecture.
- All behavioral validation uses isolated, explicitly-configured scenario databases (never the shared dev database), consistent with project testing practice.

## Dependencies

- Feature 058 (Match-Responsive Deferral Adjustments) provides the underlying event model (`int_deferral_match_response_events`) and configuration schema this feature makes reachable and observable from the Studio/workspace path.
- The Studio/workspace scenario configuration resolution/merge path and the typed configuration layer that defaults the feature to disabled when its block is absent.
