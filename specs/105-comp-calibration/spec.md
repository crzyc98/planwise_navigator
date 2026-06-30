# Feature Specification: Fast Compensation Calibration Mode

**Feature Branch**: `105-comp-calibration`
**Created**: 2026-06-29
**Status**: Draft
**Input**: Issue #280 — "Fast Compensation Calibration Mode". Let analysts tune average-compensation growth parameters (target growth rate, COLA, merit, new-hire age/level mix, per-level compensation ranges) in a ~2–4 minute loop instead of the current ~11-minute full 5-year simulation, WITHOUT sacrificing accuracy, by reusing the platform's already-validated compensation math and skipping all DC-plan work.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tune compensation policy to a growth target from the CLI (Priority: P1)

A compensation analyst has a target average-compensation growth rate (e.g. 3.5% per year) and a set of policy levers (COLA, merit budget, new-hire age/level mix, per-level compensation ranges). Today they must run a full multi-year simulation (~11 minutes), read the resulting growth, adjust one lever, and re-run — turning a 15-minute exercise into a 1–2 hour session. They want a fast calibration command that accepts the same compensation parameters as the full simulation and returns trustworthy per-year comp-growth feedback in a few minutes, so they can iterate quickly toward their target.

**Why this priority**: This is the core value of the feature — the fast tune-and-read loop. Without it, nothing else matters. It is independently shippable as a CLI-only capability and immediately useful to the analyst.

**Independent Test**: Run the calibration command for a year range against a prepared database with a chosen compensation config, and confirm it returns a per-year table of average compensation, year-over-year growth vs. target, headcount, and the new-hire-vs-existing comp gap — and that it completes materially faster than the full simulation.

**Acceptance Scenarios**:

1. **Given** a target database that has had one full simulation build, **When** the analyst runs the calibration command for a multi-year range with a chosen COLA/merit/target-growth/new-hire-mix configuration, **Then** the system returns a per-year summary of average compensation, year-over-year growth rate, the delta from the target growth rate, headcount, and the new-hire-vs-existing average-comp gap.
2. **Given** the same compensation configuration, **When** the analyst compares the calibration output to a full simulation run, **Then** the per-year average compensation and year-over-year growth figures are identical (exact, not approximate).
3. **Given** a default invocation with no database flag, **When** the analyst runs calibration, **Then** the run uses an isolated calibration database and does not modify the shared development database.
4. **Given** a multi-year range, **When** calibration runs, **Then** it completes materially faster than the full simulation for the same range (target: roughly 3–5× faster).

---

### User Story 2 - Iterate interactively without restarting (Priority: P2)

After a first calibration run, the analyst wants to adjust one or two levers (e.g. nudge COLA up, lower merit) and immediately see the new per-year growth, without re-typing the full command or rebuilding everything that did not change.

**Why this priority**: This is what turns the tool from "fast" into "interactive" and delivers the headline 15-minute-session experience. It depends on Story 1 but adds clear additional value.

**Independent Test**: Start an interactive calibration session, change a single compensation parameter, and confirm the per-year results refresh quickly and reflect the new parameter, without exiting and restarting the command.

**Acceptance Scenarios**:

1. **Given** an interactive calibration session is open, **When** the analyst changes a compensation parameter and re-runs, **Then** updated per-year average-comp and growth-vs-target results appear without restarting the session.
2. **Given** an interactive session, **When** the analyst changes only one lever, **Then** the refreshed result reflects only that change and remains exact relative to a full simulation under the new configuration.

---

### User Story 3 - Calibrate visually from Studio sliders (Priority: P3)

A less command-line-oriented analyst wants to drag sliders for target growth, COLA, merit, and new-hire mix in the web Studio and watch per-year average-compensation and growth-vs-target charts update, so they can find a policy that hits their target by feel.

**Why this priority**: Broadens access to non-CLI users and provides the visual feedback loop, but the analytical value is already delivered by Stories 1–2.

**Independent Test**: Open the Studio calibration panel, move a slider, and confirm a calibration run is triggered and the per-year charts update to reflect the new parameter values.

**Acceptance Scenarios**:

1. **Given** the Studio calibration panel, **When** the analyst adjusts the target-growth, COLA, merit, or new-hire-mix slider, **Then** a calibration run is triggered and per-year average-comp and growth-vs-target charts update.
2. **Given** a slider change, **When** the resulting charts render, **Then** the displayed comp-growth values match what the CLI calibration produces for the same parameters.

---

### Edge Cases

- **Missing prerequisite data**: The compensation-only build depends on certain non-compensation tables already existing in the target database (stale-but-present). If the target database has never had a full build, calibration MUST fail fast with a clear, actionable message telling the analyst to build a baseline first — never silently produce wrong or empty numbers.
- **Single-year range**: Year-over-year growth is undefined for the first year of a range; the output must present the first year without a growth figure (or clearly mark it) rather than fabricating one.
- **Invalid year range**: An end year earlier than the start year, or a malformed range, must be rejected with a clear message.
- **Parameter out of range**: A nonsensical parameter (e.g. negative COLA, a new-hire mix that does not sum correctly) must be reported clearly rather than producing misleading growth numbers.
- **Concurrent access to the shared database**: Default isolated-database behavior must prevent calibration from corrupting or being blocked by activity on the shared development database.
- **Stale non-compensation data is acceptable**: Non-compensation columns in the target database may remain stale during calibration; calibration MUST guarantee these stale values never influence the compensation metrics it reports.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a calibration mode, invoked for a year range, that produces per-year compensation-growth results.
- **FR-002**: Calibration MUST accept the same compensation parameters as the full simulation — target growth rate, COLA, merit, new-hire age/level mix, and per-level compensation ranges — and apply them identically.
- **FR-003**: Compensation-growth metrics produced by calibration (per-year average compensation and year-over-year growth rate) MUST be exact relative to a full simulation run under the same configuration — produced by the same validated logic, not an approximation.
- **FR-004**: Calibration MUST reuse the platform's existing validated workforce and compensation logic — the deterministic hire/termination/quota solver, mid-year compensation proration, band-aware merit/COLA/promotion logic, and the existing compensation-growth analysis — rather than reimplementing any of it.
- **FR-005**: Calibration MUST skip all work that does not affect compensation — retirement-plan eligibility, enrollment, deferral, vesting, contributions, employer match, highly-compensated-employee determination, forfeitures, and their state accumulators — in order to run materially faster.
- **FR-006**: Calibration MUST run against an isolated calibration database by default and MUST NOT modify the shared development database unless the analyst explicitly directs output elsewhere.
- **FR-007**: Calibration MUST accept an explicit configuration source and an explicit database target so analysts can point it at a specific config and database.
- **FR-008**: Calibration output MUST present, per year: average compensation, year-over-year growth rate, the delta between actual and target growth, headcount, and the average-compensation gap between new hires and existing employees.
- **FR-009**: Calibration MUST support an interactive mode in which the analyst can change compensation parameters between iterations and re-run without restarting the session.
- **FR-010**: The system MUST guarantee that stale non-compensation data present in the target database never influences the compensation metrics calibration reports.
- **FR-011**: If the target database lacks the prerequisite data needed for a compensation-only run, calibration MUST fail fast with a clear, actionable message rather than producing incorrect or empty results.
- **FR-012**: The Studio interface MUST provide a calibration panel with sliders for target growth, COLA, merit, and new-hire mix that triggers a calibration run and displays per-year average-compensation and growth-vs-target charts.
- **FR-013**: Calibration values shown in Studio MUST match the values the CLI calibration produces for the same parameters.
- **FR-014**: Calibration MUST NOT introduce any *new* event-sourcing machinery, audit exports, or retirement-plan calculations of its own. It reuses the existing workforce/compensation event-generation logic purely as a build dependency for the compensation metrics; any event rows it materializes are a reused byproduct of that shared logic, not a calibration deliverable, and calibration produces no separate per-employee audit trail or audit report.

### Key Entities *(include if feature involves data)*

- **Calibration Run**: A single execution of calibration over a year range under a specific compensation configuration against a specific (default isolated) database. Produces the per-year compensation-growth result set.
- **Compensation Parameter Set**: The tunable levers an analyst adjusts — target growth rate, COLA, merit, new-hire age/level mix, per-level compensation ranges — shared identically with the full simulation.
- **Per-Year Compensation Result**: For each simulation year: average compensation, year-over-year growth rate, delta vs. target, headcount, and new-hire-vs-existing average-comp gap.
- **Calibration Database**: The isolated database a calibration run reads from and writes its compensation subgraph into, distinct from the shared development database.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A 5-year calibration run completes materially faster than the equivalent full simulation — roughly 3–5× faster (target ~2–4 minutes vs. ~11 minutes).
- **SC-002**: Per-year average compensation and year-over-year growth produced by calibration match a full simulation under the same configuration exactly (identical values, verified by direct comparison), including under a non-default compensation configuration.
- **SC-003**: An analyst can complete a full tune-and-read calibration session (multiple parameter adjustments to reach a target growth rate) in about 15 minutes, down from 1–2 hours today.
- **SC-004**: Calibration leaves the shared development database unchanged on every default run (verified before/after).
- **SC-005**: When prerequisite data is missing, calibration fails within seconds with a clear, actionable message in 100% of cases, and never reports incorrect compensation numbers.
- **SC-006**: From the Studio panel, adjusting any of the four sliders (target growth, COLA, merit, new-hire mix) triggers a calibration run and updates the per-year charts, with values matching the CLI for the same parameters.

## Assumptions

- The full compensation and workforce math (deterministic hire/termination solver, mid-year proration, band-aware merit/COLA/promotion logic, and the compensation-growth analysis) is already implemented, validated, and the single source of truth; calibration reuses it verbatim and does not re-derive any of it.
- "Exact" means the compensation columns are produced by the identical validated logic that the full simulation uses, so they match value-for-value — this replaces the original issue's weaker "within ±1%" criterion, which assumed a re-implementation that could only approximate.
- Calibration is intended to run against a database that has already had at least one full build (the "stale-but-present" prerequisite), so the non-compensation tables the snapshot and event stream depend on already exist; how that prerequisite is satisfied is a design decision for planning, but the analyst-facing guarantee (exact comp metrics, stale non-comp data never influencing them, fail-fast when prerequisites are missing) is fixed here.
- The four headline Studio sliders (target growth, COLA, merit, new-hire mix) are the v1 surface; per-level compensation ranges are tunable via configuration/CLI in v1 and need not be a Studio slider.
- Standard configuration and database selection conventions used by the full simulation apply to calibration as well.

## Out of Scope

- Any pure-code re-implementation or approximation of the workforce or compensation math.
- Retirement-plan (DC) calculations of any kind — eligibility, enrollment, deferral, vesting, contributions, employer match, highly-compensated-employee status, forfeitures.
- New event-sourcing machinery built *for* calibration — calibration-specific audit exports or per-employee event audit trails. (Reusing the existing event-generation logic as a build dependency is in scope; building a parallel calibration audit trail is not.)
- Multi-scenario sweep/optimization automation beyond a single calibration run at a time (the interactive loop is manual parameter adjustment, not an automated search).
