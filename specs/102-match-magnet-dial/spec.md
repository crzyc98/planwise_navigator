# Feature Specification: Voluntary-Enrollment Match-Magnet Dial & Match-Ceiling Fidelity

**Feature Branch**: `102-match-magnet-dial`
**Created**: 2026-06-24
**Status**: Draft
**Input**: GitHub issue [#328](https://github.com/crzyc98/planwise_navigator/issues/328) — "Expose voluntary-enrollment match-magnet dial + fix match-ceiling not driving deferral selection (no-AE plans)"

## Context

For plans **without auto-enrollment (AE)** and **without auto-escalation**, the platform models voluntary enrollment behavior by assigning each new enrollee a deferral rate, and then "snapping" a configurable fraction of those enrollees up to the employer-match ceiling (a behavior we call the *match magnet* — it represents employees who defer just enough to capture the full match).

Two problems were reported by an analyst running a baseline scenario (no AE, stretch match 50% up to 6%, ~65% participation held flat via the voluntary enrollment rate):

1. **The match-magnet behavior is not steerable.** The fraction of enrollees who snap to the match ceiling is fixed deep in the model and cannot be adjusted per scenario, so when the analyst observes the average deferral *drifting down* year over year (the opposite of the expected hold-or-rise in the absence of AE), they have no lever to intervene.
2. **Changing the match ceiling does not change behavior.** Running baseline (match 50% on 6%) versus a scenario (match 50% on 10%) produced an **identical** deferral-rate distribution — including no growth in the share of employees at 10%+. Raising the ceiling should pull more voluntary enrollees toward the higher rate; it currently does not.

## Clarifications

### Session 2026-06-24

- Q: For match modes with no single deferral-based ceiling (service-graded, tenure-graded, points-based), what should the match magnet do? → A: Derive the ceiling from the max-deferral-percentage of the applicable service/tenure/points tier and snap to that — the magnet works in all match modes.
- Q: What bounds voluntary deferral selection once the internal 10% artifact is removed? → A: Add a new per-scenario "maximum employee deferral %" configuration field that bounds all voluntary deferral selection.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Match ceiling drives voluntary deferral selection (Priority: P1)

An analyst configures a plan's employer match and compares two scenarios that differ only in the match ceiling (e.g., 50% on the first 6% vs. 50% on the first 10%). The analyst expects the higher-ceiling scenario to show a larger share of voluntarily-enrolled employees deferring at the higher rate, and a higher average deferral, because employees who defer to capture the full match now have a higher target.

**Why this priority**: This is a correctness defect. Today scenarios that differ in match generosity produce indistinguishable workforce-deferral results, which silently invalidates match-design comparisons — the core purpose of the tool. Until this is fixed, the exposed dial (Story 2) would tune behavior against a ceiling that doesn't move.

**Independent Test**: Run two otherwise-identical multi-year scenarios in isolated databases, differing only in the configured match ceiling (6% vs 10%). Verify the deferral-rate distribution and average deferral are measurably higher in the 10% scenario.

**Acceptance Scenarios**:

1. **Given** a plan with no auto-enrollment and an employer match capped at 6%, **When** a baseline simulation runs, **Then** the voluntary-enrollee deferral distribution clusters at or below 6% per the match ceiling.
2. **Given** the same plan with the match ceiling raised to 10%, **When** the simulation runs, **Then** the share of voluntary enrollees at the higher deferral rate and the average voluntary deferral are both strictly higher than in the 6% scenario.
3. **Given** a match ceiling configured through the active employer-match formula, **When** the simulation runs, **Then** the match-magnet target rate equals that configured ceiling, regardless of whether any optional deferral-behavior modeling is enabled.

---

### User Story 2 - Analyst can tune the match-magnet dial per scenario (Priority: P2)

An analyst observes the average deferral degrading across simulation years in a no-AE plan and wants to intervene — for example, to model a stronger "defer-to-the-match" tendency in the population. The analyst can adjust the match-magnet controls as part of scenario configuration (both in the configuration file and in the Studio UI) without editing model internals.

**Why this priority**: This delivers the explicit "expose the dial" request and gives analysts a sanctioned intervention point. It depends on Story 1 being correct (the dial targets the match ceiling), but is independently valuable once the ceiling is wired correctly.

**Independent Test**: In an isolated scenario, change the match-magnet controls (toggle on/off; vary the snap fraction) and confirm the resulting voluntary-deferral distribution shifts in the expected direction, with no code changes required.

**Acceptance Scenarios**:

1. **Given** the match-magnet controls are surfaced in scenario configuration, **When** an analyst raises the snap fraction, **Then** a larger share of voluntary enrollees defers at the match ceiling and the average voluntary deferral rises.
2. **Given** the match magnet is disabled for a scenario, **When** the simulation runs, **Then** voluntary enrollees retain their demographically-assigned deferral rates with no snapping to the ceiling.
3. **Given** an analyst opens the relevant scenario-configuration screen in Studio, **When** they view match settings, **Then** the match-magnet controls are visible, editable, and persist with the rest of the scenario configuration.
4. **Given** a scenario that does not specify the match-magnet controls, **When** the simulation runs, **Then** the system applies the existing default behavior (backward compatible).

---

### User Story 3 - Deferral selection can reach the configured ceiling (Priority: P3)

An analyst sets a match ceiling at or above 10% and expects voluntary enrollees who snap to the match to actually appear in the "10% or more" band, rather than being held below it by an internal limit.

**Why this priority**: Removes a secondary artifact (an internal deferral cap) that prevents a configured ceiling at/above 10% from populating the top deferral band. Lower impact than Stories 1–2 but needed for high-ceiling designs to report correctly.

**Independent Test**: Configure a match ceiling of 10% and confirm voluntary enrollees who snap to the match are counted in the 10%+ band of the deferral distribution.

**Acceptance Scenarios**:

1. **Given** a match ceiling configured at 10%, **When** voluntary enrollees snap to the match, **Then** they appear at 10% in the deferral distribution (not capped below it).
2. **Given** a match ceiling configured above the per-scenario maximum employee deferral percentage, **When** the simulation runs, **Then** selected deferral rates are bounded by that configured maximum and the result is reported, not silently dropped.

---

### Edge Cases

- **No match configured / match disabled**: The match magnet has no ceiling to target; voluntary enrollees keep their demographically-assigned rates and no snapping occurs.
- **Employee's demographic rate already at or above the ceiling**: The magnet does not lower anyone's deferral; the higher rate is preserved.
- **Non-deferral-based match modes** (e.g., service-graded, tenure-graded, points-based): The match-magnet ceiling is derived from the max-deferral-percentage of the tier applicable to each employee (by service/tenure/points), so the magnet operates in all match modes rather than falling back to a stale default ceiling.
- **Conflicting configuration** (magnet enabled but snap fraction set to zero): Behaves as effectively disabled; result must be deterministic and reproducible.
- **Backward compatibility**: Existing scenarios that never set the new controls reproduce their prior results.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The match-magnet target ceiling MUST be derived from the scenario's active employer-match formula, so that the deferral rate enrollees snap to reflects the configured match ceiling.
- **FR-002**: Changing the configured match ceiling between two otherwise-identical scenarios MUST produce a measurably different voluntary-enrollee deferral distribution and average deferral.
- **FR-003**: Resolution of the match-magnet ceiling MUST NOT depend on any optional/secondary deferral-behavior modeling being enabled; the ceiling MUST track the active match formula on its own.
- **FR-004**: The system MUST expose match-magnet controls as part of scenario configuration: (a) an enable/disable toggle, and (b) the fraction of below-ceiling voluntary enrollees who snap to the match ceiling.
- **FR-005**: The match-magnet controls MUST be editable in the Studio web interface and persist with the rest of the scenario configuration, and MUST be carried through scenario copy/clone operations.
- **FR-006**: When a scenario does not specify the match-magnet controls, the system MUST apply the existing default behavior so that prior scenarios reproduce their results (backward compatible).
- **FR-007**: When the match magnet is disabled, voluntary enrollees MUST retain their demographically-assigned deferral rates with no snapping.
- **FR-008**: The match magnet MUST only raise a deferral rate toward the ceiling; it MUST NOT reduce an enrollee's deferral rate below their demographically-assigned rate.
- **FR-009**: Voluntary-enrollee deferral selection MUST be able to reach the configured match ceiling, including ceilings at or above 10%, bounded by the per-scenario maximum employee deferral percentage (FR-013) rather than by any lower internal limit.
- **FR-013**: The system MUST provide a per-scenario "maximum employee deferral %" configuration field that bounds all voluntary deferral selection (including magnet-snapped rates). It MUST be editable in scenario configuration and the Studio UI, MUST default to a value that preserves current behavior when unset, and selected rates MUST never exceed it.
- **FR-010**: Match-magnet behavior MUST remain deterministic and reproducible for a given random seed and configuration.
- **FR-011**: For match modes without a single deferral-based ceiling (service-graded, tenure-graded, points-based), the match-magnet ceiling MUST be derived from the max-deferral-percentage of the tier applicable to each employee (by their service/tenure/points), so the magnet operates in all match modes. It MUST NOT silently apply a stale default ceiling.
- **FR-012**: The match-magnet controls MUST be documented for analysts (where to set them, what they do, default values, and their interaction with the match ceiling).

### Key Entities *(include if feature involves data)*

- **Match-Magnet Configuration**: Scenario-level settings governing the "defer-to-the-match" behavior — an enable/disable flag, the snap fraction (share of below-ceiling voluntary enrollees pulled to the ceiling), and the maximum employee deferral percentage that bounds selected rates. Belongs to a scenario; defaults preserve current behavior when unset.
- **Employer-Match Formula**: The configured match design whose ceiling (the maximum employee deferral that earns a match) defines the magnet's target rate. Already part of scenario configuration; this feature makes the voluntary-enrollment logic read its ceiling reliably.
- **Voluntary-Enrollee Deferral Decision**: The per-employee outcome (selected deferral rate) produced for voluntary enrollment, which the match magnet may raise toward the ceiling.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Two otherwise-identical multi-year scenarios differing only in match ceiling (6% vs 10%) yield a higher average voluntary deferral in the 10% scenario, with the difference clearly attributable to the ceiling change (non-zero, beyond rounding).
- **SC-002**: In the 10% scenario from SC-001, the share of voluntary enrollees at 10%+ is strictly greater than in the 6% scenario.
- **SC-003**: An analyst can change match-magnet behavior for a scenario entirely through configuration (file and Studio UI) with zero edits to model internals, and see the deferral distribution shift in the expected direction.
- **SC-004**: Existing scenarios that do not set the new controls reproduce their prior deferral distributions exactly (no behavioral regression).
- **SC-005**: For a fixed configuration and random seed, repeated runs produce identical voluntary-deferral outcomes (reproducibility preserved).
- **SC-006**: Analyst-facing documentation enables a new analyst to locate and correctly adjust the match-magnet controls without engineering assistance.

## Assumptions

- The match-magnet controls are scoped at the **scenario** level (consistent with other match and enrollment settings), with sensible platform defaults when unset.
- The default snap fraction and default enabled/disabled state preserve **current** behavior, so this feature is non-breaking for existing scenarios.
- The "configured match ceiling" means the maximum employee deferral percentage that earns any employer match under the active formula (for tiered/stretch designs, the top tier's upper bound).
- Selected deferral rates remain bounded by the new per-scenario maximum employee deferral percentage (FR-013), which replaces the hard-coded internal limit that currently blocks the 10%+ band; its default preserves current behavior.
- Validation will follow project guidance: isolated, explicitly-configured databases (not the shared dev database), exercising the no-AE + stretch-match edge configuration across the full multi-year horizon.
- This feature does not introduce auto-enrollment or auto-escalation behavior; it only governs voluntary-enrollment deferral selection.
