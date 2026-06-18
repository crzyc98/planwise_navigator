# Feature Specification: Tenure-Graded Multi-Tier Employer Match Formula

**Feature Branch**: `099-tenure-graded-match`
**Created**: 2026-06-18
**Status**: Draft
**Input**: User description: "i have a match design that i can't model in the current system. it is one that varies by tenure but has different tiers, for those under 10 years of service it is 100% on first 2% and 50% on next 6% and for over ten years of tenure it is 100% on first 2% and 50% on next 8%"

## Clarifications

### Session 2026-06-18

- Q: The system already has a single-tier `tenure_based` match mode (match rate varies by tenure band, but each band has only one flat rate + one max deferral %). Should the new tenure-graded multi-tier capability replace/supersede that existing mode, or be added as a separate, independently-selectable mode? → A: Supersede/replace the existing single-tier `tenure_based` mode — old configs are expressed as a one-tier case of the new schema.
- Q: When should the system flag tenure-band configurations that contain gaps or overlaps (FR-008)? → A: Warn at save/edit time AND hard-block at simulation run time (defense in depth).
- Q: Is there a hard limit on the number of tenure bands (and tiers per band) the system must support for a single match formula? → A: No fixed limit — analyst-defined, bounded only by practical usability, not enforced as a hard cap.
- Q: Should the tenure bands used in this match formula reuse the system's centralized reporting tenure-band configuration (`config_tenure_bands.csv`), or be defined independently as part of the match plan design? → A: Independent — match-formula tenure bands are defined as part of the plan design, fully decoupled from the reporting tenure bands.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure a tenure-graded, multi-tier match formula (Priority: P1)

A plan analyst needs to model an employer match design where the match schedule itself (not just a single flat rate) changes based on an employee's years of service. For example: employees with under 10 years of service receive 100% match on the first 2% of pay deferred and 50% match on the next 6% deferred (up to 8% deferred); employees with 10+ years of service receive 100% on the first 2% and 50% on the next 8% deferred (up to 10% deferred). Today the system only allows the match *rate* to vary by tenure for a single deferral tier — it cannot apply a different multi-tier deferral schedule per tenure band.

**Why this priority**: This is the core capability gap. Without it, the analyst cannot model this plan design at all, blocking any downstream cost analysis, comparison, or reporting for this scenario.

**Independent Test**: Can be fully tested by configuring two tenure bands (under 10 years, 10+ years), each with its own ordered set of match tiers, running a simulation, and confirming the resulting match contribution amounts match the formula for employees in each band.

**Acceptance Scenarios**:

1. **Given** a plan design with tenure band "0-10 years" configured with tiers (100% on first 2% deferred, 50% on next 6% deferred), **When** an employee with 5 years of tenure defers 8% of pay, **Then** the system calculates a match equal to 100%×2% + 50%×6% = 5% of pay.
2. **Given** a plan design with tenure band "10+ years" configured with tiers (100% on first 2% deferred, 50% on next 8% deferred), **When** an employee with 12 years of tenure defers 10% of pay, **Then** the system calculates a match equal to 100%×2% + 50%×8% = 6% of pay.
3. **Given** the two tenure bands above, **When** an employee with 5 years of tenure defers 10% of pay (above their band's 8% max tier), **Then** the match is capped at the under-10-years schedule's maximum (5% of pay), and the deferral above 8% receives no additional match.
4. **Given** the two tenure bands above, **When** an employee with exactly 10.0 years of tenure is evaluated, **Then** they are matched using the "10+ years" schedule (lower bound inclusive, consistent with existing band conventions in the system).

---

### User Story 2 - Review and validate the configured match schedule before running a simulation (Priority: P2)

A plan analyst wants to see a clear, readable summary of the tenure-graded match schedule they've configured (each tenure band, its tiers, and the resulting maximum match percentage) before committing to a multi-year simulation run, so they can catch configuration mistakes early.

**Why this priority**: Prevents wasted simulation runs and costly rework caused by misconfigured tier boundaries or overlapping tenure bands; valuable but not a blocker to the core modeling capability in User Story 1.

**Independent Test**: Can be tested by configuring a tenure-graded match design and confirming the configuration summary view displays each tenure band with its tiers and computed maximum match percentage, without needing to run a full simulation.

**Acceptance Scenarios**:

1. **Given** a tenure-graded match formula with two bands configured, **When** the analyst views the configuration summary, **Then** each band's tenure range, tier breakdown, and resulting maximum effective match percentage are displayed.
2. **Given** tenure bands that overlap or leave a gap (e.g., one band ends at 8 years and the next starts at 10 years), **When** the analyst views or saves the configuration, **Then** the system flags the gap or overlap as a configuration issue before the design can be used in a simulation.

---

### User Story 3 - Model more than two tenure bands (Priority: P3)

A plan analyst wants the flexibility to define three or more tenure bands (e.g., 0-5, 5-10, 10+ years), each with its own independent multi-tier match schedule, to model more granular service-based match designs beyond the two-band example.

**Why this priority**: Extends the core capability for richer plan designs, but the two-band case in User Story 1 already delivers the requested business value; this is a generalization, not a new requirement. There is no fixed limit on the number of tenure bands or tiers per band — the system supports as many as an analyst defines, bounded only by practical usability rather than a hard cap.

**Independent Test**: Can be tested by configuring three tenure bands with distinct tier schedules and confirming each band's employees are matched per their own schedule.

**Acceptance Scenarios**:

1. **Given** three tenure bands each with distinct multi-tier schedules, **When** employees from each band defer pay, **Then** each employee's match is calculated using their own band's schedule.

---

### Edge Cases

- An employee's tenure crosses a tenure-band boundary partway through the plan year (e.g., turns 10 years of service in June) — the system must determine which schedule applies for that year using the same tenure-as-of-date convention used elsewhere in the system.
- An employee defers a rate below the first tier threshold (e.g., 1% when the first tier covers 0-2%) — only the partial first tier match applies, no error.
- An employee defers a rate above the highest configured tier for their band — the match is capped at the maximum defined for that band; deferral above the cap receives no match.
- Tenure bands are configured with a gap (no band covers a given tenure range) or an overlap (two bands cover the same tenure) — the system must surface this as a configuration problem rather than silently using a default or the first matching band.
- An employee has zero years of tenure (new hire) — must fall into the lowest-bound tenure band's schedule.
- A tenure band is configured with zero or only one tier (e.g., a flat rate band alongside multi-tier bands) — must still be supported without requiring every band to have the same number of tiers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support employer match formulas where the deferral-rate tier schedule (not just the match rate) varies depending on the employee's tenure band.
- **FR-002**: System MUST allow each tenure band to define its own independent, ordered list of match tiers, where each tier specifies a deferral percentage range and a match rate for that range.
- **FR-003**: System MUST support at least two tenure bands out of the box, matching the example design (under 10 years; 10 years and over), using a lower-bound-inclusive / upper-bound-exclusive convention consistent with existing tenure band handling in the system.
- **FR-003a**: This tenure-graded multi-tier capability MUST supersede the system's existing single-tier tenure-based match mode (where each tenure band has only one flat match rate and one max deferral percentage). Any plan design previously expressed in the single-tier mode MUST be representable as a one-tier special case of the new tenure band/tier schema, so analysts configure tenure-varying match designs through a single, unified mechanism going forward.
- **FR-004**: System MUST allow a tenure band's tier list to contain a different number of tiers, different deferral breakpoints, and different match rates than any other band — bands are not required to share a structure.
- **FR-005**: System MUST calculate each employee's match contribution by first determining their tenure band, then applying that band's tier schedule cumulatively to their actual deferral rate (i.e., 100% on the portion of deferral falling in the first tier, 50% on the portion falling in the next tier, and so on).
- **FR-006**: System MUST cap the match at the maximum deferral percentage covered by an employee's tenure band's tier schedule; deferral amounts above that cap receive no additional match.
- **FR-007**: System MUST let an analyst configure tenure band boundaries and their associated tier schedules without requiring engineering/code changes.
- **FR-008**: System MUST detect and flag tenure band configurations that contain gaps (uncovered tenure ranges) or overlaps (a tenure value matched by more than one band) at two points: (a) immediately when the analyst saves/edits the configuration, as a non-blocking warning so the issue is caught early; and (b) as a hard block preventing the configuration from being used in a simulation run until the gap/overlap is resolved.
- **FR-009**: System MUST reflect the tenure-graded match calculation in the generated match contribution events/results used for downstream cost reporting and scenario comparison, identical in form to match contributions produced by the system's existing (non-tenure-graded) match formulas.
- **FR-010**: System MUST provide a way for an analyst to review the configured tenure bands and their tier schedules (including the resulting maximum match percentage per band) prior to running a multi-year simulation.

### Key Entities

- **Tenure Band**: A range of employee years-of-service (minimum, maximum) that determines which match tier schedule applies to an employee. A match design may define multiple tenure bands that together should fully and exclusively cover the possible range of tenure values. These bands are defined independently as part of the match plan design and are decoupled from the system's centralized reporting tenure-band configuration (used for analytics/reporting elsewhere) — the two need not share boundaries.
- **Match Tier**: A single step within a tenure band's schedule, defined by a deferral percentage range (e.g., "first 2%" or "next 6%") and the match rate applied to deferrals within that range.
- **Tenure-Graded Match Formula**: The overall match design for a plan, composed of one or more Tenure Bands, each carrying its own ordered set of Match Tiers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst can fully configure the example two-band design (under 10 years: 100%/2% + 50%/6%; 10+ years: 100%/2% + 50%/8%) in a single configuration session without engineering assistance.
- **SC-002**: Match contribution amounts calculated by the system for employees in each tenure band match the expected formula result with 100% accuracy across a representative set of test deferral rates (including below-first-tier, mid-schedule, at-cap, and above-cap deferral rates).
- **SC-003**: 100% of misconfigured tenure-band schedules (gaps or overlaps) are caught and surfaced to the analyst before a simulation runs, with zero such configurations silently producing incorrect match results.
- **SC-004**: Analysts modeling a tenure-graded match design can produce the same downstream cost reports and scenario comparisons available for existing match formula types, with no missing or distorted figures attributable to the new formula type.
