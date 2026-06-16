# Feature Specification: Tenure-Based Match — Year 1 Tier Assignment and Infinity Display

**Feature Branch**: `098-tenure-match-tier-bug`
**Created**: 2026-06-15
**Status**: Draft
**Input**: Bug report — tenure-based match assigns everyone the lowest tier in the first simulation year; Config Summary displays `None` instead of `∞` for open-ended final tiers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Correct Tier Assignment in First Simulation Year (Priority: P1)

A plan administrator configures tenure-based match tiers (e.g., 0–5 yrs → 6% max deferral, 5–10 yrs → 8%, 10+ yrs → 10%) and runs a simulation. Every employee should receive the match rate corresponding to their actual years of service — including in the first year of any simulation run. Currently all employees are assigned to the lowest tier (0–5 years) in Year 1, regardless of actual tenure.

**Why this priority**: Incorrect match amounts in Year 1 makes all financial projections for that year wrong. An employee with 15 years of service erroneously receives a 6%-cap match instead of 10%, materially understating employer cost.

**Independent Test**: Configure a scenario with three tenure tiers, seed the census with employees of known tenure (e.g., 2, 7, 12 years), run a single-year simulation, and verify each employee's match amount reflects their actual tier.

**Acceptance Scenarios**:

1. **Given** tenure-based tiers (0–5 / 5–10 / 10+ yrs) and a census with employees spanning all three brackets, **When** the first simulation year runs, **Then** each employee's employer match is calculated using the tier matching their actual years of service — not uniformly the lowest tier.
2. **Given** an employee with 12 years of service in the census, **When** Year 1 runs, **Then** their employer match cap is 10% of compensation (not 6%).
3. **Given** an employee with 3 years of service, **When** Year 1 runs, **Then** their match cap is 6% of compensation (correct lowest tier, not a regression).
4. **Given** a multi-year simulation (e.g., 2025–2027), **When** examining match data for every year, **Then** tier assignment is correct in all years including Year 1.

---

### User Story 2 — Infinity Symbol for Open-Ended Final Tier in Config Summary (Priority: P2)

When a plan administrator starts a simulation, the Config Summary panel printed to the terminal should display `∞` for the upper bound of any open-ended tier (one with no maximum), not the raw value `None`. This affects all match modes that support open-ended tiers.

**Why this priority**: Displaying `None` reads as a Python error to non-technical users and erodes confidence in the output, even though the underlying calculation is unaffected.

**Independent Test**: Configure any tenure-based scenario where the final tier has no upper bound, start the simulation, and confirm the Config Summary log line shows `∞` (not `None`) for that tier.

**Acceptance Scenarios**:

1. **Given** a tenure-based match with a final tier of `10+ years` (no upper bound), **When** the simulation starts and prints the Config Summary, **Then** the log reads `10–∞ yrs` (not `10–None yrs`).
2. **Given** any tier where the upper bound is null or absent, **When** the Config Summary renders, **Then** the display shows `∞` for that bound consistently across tenure-based, graded-by-service, and points-based modes.

---

### Edge Cases

- Employee hired during the first simulation year (tenure = 0): should land in the lowest tier — correct behavior that must not regress.
- Continuation run starting at Year 2+: Year 1 of the continuation must also assign tiers correctly using prior-year tenure carried forward.
- A scenario switched from deferral-based to tenure-based mid-project: first tenure-based year must use actual census tenure values, not default to zero.
- `max_years` stored explicitly as `None` vs. simply absent from the tier dict: both cases must display `∞`.
- Employee with a missing hire date in the census: system must default to the lowest tier and log a warning.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST assign each employee to the tenure tier matching their actual years of service as of December 31 of the simulation year, in every simulation year including the first.
- **FR-002**: When an employee's years-of-service cannot be resolved (e.g., missing hire date), the system MUST assign the lowest tier and log a warning identifying the affected employee IDs.
- **FR-003**: The Config Summary panel MUST display `∞` wherever a tier's upper bound is null or absent, for all match modes that support open-ended tiers.
- **FR-004**: The `applied_years_of_service` field in the match output data MUST reflect the actual tenure value used for tier selection, enabling post-run verification of which tier each employee received.
- **FR-005**: A fix to Year 1 tier assignment MUST NOT alter correct tier assignment in Year 2 or later years.

### Key Entities

- **Tenure Match Tier**: A configuration record with `min_years`, `max_years` (nullable for open-ended), `match_rate`, and `max_deferral_pct`. Determines which employer match cap applies to each employee.
- **Years of Service**: Integer years of service for an employee in the current simulation year, sourced from the workforce data. Drives which tier is selected.
- **Config Summary**: Pre-run console panel displaying the active match mode and tier details, generated from the written YAML config file before the simulation runs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a simulation with employees spanning all configured tenure tiers, zero employees in Year 1 receive a match amount inconsistent with their actual tenure bracket (verified by comparing `applied_years_of_service` to known census tenure).
- **SC-002**: The Config Summary for any scenario with an open-ended final tier contains `∞` and never contains the string `None` in a tier label.
- **SC-003**: Multi-year simulations (3+ years) show statistically consistent employer match percentages across all years when the workforce tenure distribution is stable — Year 1 is not an outlier.
- **SC-004**: All existing tests for deferral-based and graded-by-service match modes continue to pass without modification after the fix is applied.

## Assumptions

- The Year 1 lowest-tier bug is caused by `years_of_service` resolving to 0 for all employees in Year 1, most likely because the workforce snapshot join in the match calculation model returns NULL tenure for that year (causing `COALESCE(tenure, 0)` to default everyone to 0). The fix must ensure tenure data is available from the snapshot before match calculations run.
- The `None` display bug is a Python formatting issue: `dict.get('max_years', '∞')` returns the stored `None` value when the key exists but is `None`, rather than using the fallback default. The fix is a null-coalescing expression.
- Both bugs are independent and can be fixed and tested separately.
