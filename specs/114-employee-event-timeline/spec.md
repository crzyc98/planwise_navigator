# Feature Specification: Employee Event Timeline (Storyline) View

**Feature Branch**: `114-employee-event-timeline`
**Created**: 2026-07-15
**Status**: Draft
**Input**: GitHub issue #440 — "Studio: employee event timeline (storyline) view." The platform is event-sourced with UUID-stamped events, but no UI shows a single employee's history. A timeline view is the payoff feature of event sourcing: it makes results explainable and turns debugging sessions into a click. Requested: a Studio page to search an employee_id within a scenario and render their full event history as a vertical timeline with effective dates and key payload fields, alongside a per-year state strip from the workforce snapshot so event vs. state can be eyeballed for consistency; a read-only paginated API; deep-linking from anywhere an employee_id appears. Out of scope: editing/annotating events, cross-scenario comparison. Pure read over existing tables; no schema changes.

## Overview

Analysts and developers today answer "what happened to this employee?" by hand-writing database queries against the event and snapshot tables. This feature gives them a single view: find an employee within a scenario (by ID or by filtering on attributes), read their simulated career as a story (hired → became eligible → enrolled → deferral escalated → raised/promoted → terminated), check that story against the year-end state the simulation actually produced, and — for plan-design questions — place the same employee's story from a second scenario alongside it to see exactly where the two designs diverge for that person. It is strictly read-only — the event log's immutability is untouched.

## Clarifications

### Session 2026-07-15

- Q: May the view and retrieval interface expose the snapshot's identity fields (SSN, birth date)? → A: Yes, show everything — SSNs are already masked upstream at census creation, and birth date is acceptable to display. No additional masking or field exclusion is required in this feature.
- Q: Must users know the full exact employee_id, or does the system help them find one? → A: Autocomplete — typing a partial ID suggests matching employee IDs within the selected scenario to pick from. (Later in the session, attribute-based filtering was also brought into scope as a complementary discovery path — see next bullets.)
- Q: Should users be able to find employees by filtering on attributes (status, level, year, enrollment state) rather than only by ID? → A: Yes — in scope for this feature as a lower-priority story: filter the scenario's employees by attributes and click through to a timeline.
- Q: The source issue lists cross-scenario employee comparison as out of scope; keep it that way? → A: No — brought into scope for this feature: after landing on one employee's timeline, the user can select a second scenario and view the same employee's history side by side to see where the two scenarios diverge.
- Q: Does the timeline open at the beginning of the employee's story or at the most recent year? → A: Oldest-first — land on the employee's first simulation year and read forward in time; pagination proceeds from earliest year to latest.
- Q: The issue lists HCE_STATUS and match/core contribution events on the timeline, but the primary event history contains neither — match events live in a separate store, core contributions and HCE status exist only as (or not even as) year-end state. → A: The timeline shows every event type present in the primary event history (currently: hire, termination, promotion, raise, enrollment, enrollment change, eligibility, deferral escalation, deferral match response) plus employer match contribution events merged in from their separate store. Employer core amounts appear in the per-year state strip, not as timeline entries. HCE status is excluded until the platform records it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Look up an employee and read their event history (Priority: P1)

An analyst investigating a surprising simulation result picks a scenario, enters an employee_id, and sees that employee's complete recorded history as a vertical timeline: every event in chronological order, labeled by type and effective date, with the details that matter for that event type (compensation for hires/raises/promotions, deferral rate for enrollment and escalation events, job level for promotions).

**Why this priority**: This is the feature. Without it there is nothing to look at, and it alone replaces the manual-query workflow that motivated the issue.

**Independent Test**: Pick an employee known to have events in a built scenario, search for them, and verify the rendered timeline matches a direct query of the scenario's event history — same events, same order, same key values. Delivers standalone value with no other story implemented.

**Acceptance Scenarios**:

1. **Given** a built scenario containing events for employee "EMP_2025_001", **When** the analyst searches that employee_id, **Then** every recorded event for that employee appears in chronological order, each showing its event type, effective date, and type-appropriate detail fields.
2. **Given** an employee whose history spans multiple simulation years, **When** the timeline renders, **Then** events are visibly grouped by simulation year so the multi-year story reads top to bottom.
3. **Given** an employee_id with no data in the selected scenario, **When** the analyst searches it, **Then** the view states plainly that no records were found for that employee in this scenario — never a blank screen or an error.
4. **Given** an employee with employer match contribution events recorded for a year, **When** that year's timeline renders, **Then** the match contribution events appear in the timeline alongside the lifecycle events for that year.

---

### User Story 2 - Eyeball event history against year-end state (Priority: P2)

Alongside each simulation year's events, the analyst sees that year's snapshot state for the employee — employment status, compensation, enrollment/deferral state, and contribution totals (employee contributions, employer match, employer core) — so they can confirm the events explain the state, or spot the year where they diverge.

**Why this priority**: This is the debugging payoff called out in the issue (the cross-year state-bug class). The timeline is useful without it, so it ranks second, but this is what turns the page from a viewer into a diagnostic tool.

**Independent Test**: Load the timeline for an employee with snapshots in at least two years and verify each year's state strip matches a direct query of the snapshot for that employee and year, positioned with that year's events.

**Acceptance Scenarios**:

1. **Given** an employee with a snapshot for simulation year 2026, **When** the analyst views 2026 in the timeline, **Then** a state strip for that year shows the employee's status, compensation, deferral rate, enrollment state, and contribution totals as of that year's snapshot.
2. **Given** a year where the snapshot contradicts the events (e.g., terminated status with no termination event that year), **When** the analyst compares the year's events to its state strip, **Then** the discrepancy is evident from the juxtaposition alone — the system does not need to detect or flag it.
3. **Given** an employee present in snapshots but with zero recorded events (e.g., a baseline employee untouched by the simulation), **When** the analyst searches them, **Then** the per-year state strips still render, with the events area explicitly empty rather than treated as "employee not found."

---

### User Story 3 - Deep-link into an employee's timeline (Priority: P3)

Anywhere Studio displays an employee_id — a results table, a future data-quality drill-down, a validation failure — the user can follow a link straight to that employee's timeline in that scenario, and can share that link with a colleague.

**Why this priority**: Adoption and workflow glue. The timeline is fully usable via manual search; deep-linking removes friction and enables the "debugging session becomes a click" promise, but it can ship after the core view.

**Independent Test**: Construct the link (scenario + employee_id) by hand, open it in a fresh browser session, and verify it lands directly on that employee's populated timeline — no originating page required.

**Acceptance Scenarios**:

1. **Given** a link encoding a valid scenario and employee_id, **When** it is opened, **Then** Studio lands on the timeline view already loaded with that employee's history in that scenario.
2. **Given** a link whose employee_id has no data in the given scenario, **When** it is opened, **Then** the timeline view opens with the same clear "no records found" treatment as manual search (User Story 1, scenario 3).

---

### User Story 4 - Find employees worth inspecting by filtering on attributes (Priority: P4)

An analyst who doesn't have a specific employee_id in hand filters the scenario's employees by attributes — employment status, job level, simulation year, enrollment/participation state, presence of escalations — to surface a shortlist (e.g., "employees terminated in 2026 who had deferral escalations"), then clicks any row to open that employee's timeline.

**Why this priority**: It removes the last dependence on hand-written queries — today, *finding* an interesting employee is itself a query. It ranks below the timeline itself and the state strip because ID autocomplete (US1) already covers the common "I have an ID from a log" entry path.

**Independent Test**: Apply a filter combination with a known matching population in a built scenario, verify the result list matches a direct query of the snapshot for those criteria, and verify clicking a row lands on that employee's timeline.

**Acceptance Scenarios**:

1. **Given** a built scenario, **When** the analyst filters by employment status "terminated" and simulation year 2026, **Then** the list shows exactly the employees matching those criteria in that year, with enough identifying columns (ID, status, level, compensation) to choose among them.
2. **Given** a filter result list, **When** the analyst selects an employee, **Then** they land on that employee's timeline (User Story 1) for the same scenario.
3. **Given** filter criteria matching no employees, **When** the filter is applied, **Then** the list states plainly that no employees match — never a blank or error state.
4. **Given** filter criteria matching a very large population, **When** the list renders, **Then** results are paginated and remain responsive rather than loading the full population at once.

---

### User Story 5 - Compare the same employee across two scenarios (Priority: P5)

While viewing an employee's timeline, the analyst selects a second scenario and sees the same employee's history from both scenarios side by side, aligned by simulation year — so they can pinpoint exactly where two plan designs diverge for that person (e.g., enrolled a year earlier under auto-enrollment, higher match under a richer formula, same termination either way).

**Why this priority**: This is the plan-design payoff — scenario deltas explained at the level of one human story instead of aggregate charts. It ranks last because it depends on the single-scenario timeline being complete, and it is the most architecturally involved slice (each scenario is an isolated dataset).

**Independent Test**: Build two scenarios from the same census with a deliberate plan-design difference, open one employee's timeline in scenario A, add scenario B for comparison, and verify each column faithfully matches that scenario's underlying data and that the seeded divergence is visible at the year it occurs.

**Acceptance Scenarios**:

1. **Given** an employee present in two scenarios built from the same census, **When** the analyst adds the second scenario to the timeline view, **Then** both histories render side by side aligned by simulation year, each column labeled with its scenario and complete per that scenario's data.
2. **Given** the side-by-side view, **When** a year's events or state differ between the scenarios (e.g., different enrollment date, deferral rate, or match amount), **Then** the difference is identifiable at that year from the juxtaposition — the analyst can point to where the stories diverge.
3. **Given** an employee who exists in the first scenario but not the second (e.g., a simulated new hire generated only in one run), **When** comparison is requested, **Then** the second column states plainly that the employee has no records in that scenario, while the first column remains fully rendered.
4. **Given** a comparison view, **When** the analyst shares its address, **Then** the link reopens the same two-scenario comparison for that employee (extending User Story 3's deep-linking).

---

### Edge Cases

- **Snapshot-only employees**: an employee can exist in year-end snapshots with no events at all; the view must distinguish "no events" from "employee not found" (covered by US2 scenario 3).
- **High-volume histories**: long multi-year runs can produce many events per employee (escalations, match responses, match contributions each year); the view and its API must page by simulation year rather than load an unbounded history.
- **Empty or unbuilt scenario**: if the scenario has no workforce data at all, the view should say the scenario has no queryable results — not imply the specific employee is missing.
- **Same-day events**: multiple events can share an effective date (e.g., hire and eligibility). Ordering must be deterministic and stable across loads, following the lifecycle's natural order where dates tie.
- **Input hygiene**: searches should tolerate leading/trailing whitespace and case differences in the entered employee_id rather than demanding an exact byte match.
- **Mixed-generation data**: if the scenario database carries results from multiple runs (config drift), the view shows what is recorded, as recorded — surfacing run-provenance concerns is out of scope here.
- **Comparison with mismatched year ranges**: the two scenarios may cover different simulation year spans (e.g., 2025–2027 vs 2025–2029); the side-by-side view must align the overlapping years and clearly mark years present in only one scenario, not silently truncate.
- **Comparison where IDs don't correspond**: census employees share IDs across scenarios built from the same census, but simulation-generated hires get run-specific IDs; when the employee is absent from the second scenario, the view says so (US5 scenario 3) rather than implying the scenarios disagree.
- **Comparing a scenario with itself**: selecting the same scenario twice should be prevented or clearly harmless (two identical columns), never an error.
- **Filter over a large scenario**: attribute filters matching tens of thousands of employees must paginate; the filter list is a discovery aid, not a bulk-export surface.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to select a scenario and look up an employee within it by employee_id, with lookup tolerant of surrounding whitespace and letter case.
- **FR-001a**: As the user types a partial employee_id, the system MUST suggest matching employee IDs within the selected scenario for the user to pick from (autocomplete).
- **FR-002**: The system MUST display every event recorded for that employee in the scenario's primary event history — covering all event types present in the store (currently: hire, termination, promotion, raise, enrollment, enrollment change, eligibility, deferral escalation, deferral match response) — without filtering any type out, including types added in the future.
- **FR-003**: The system MUST also display the employee's employer match contribution events from their separate store, merged into the same chronological timeline.
- **FR-004**: Each timeline entry MUST show the event type, effective date, and the detail fields relevant to that type — at minimum compensation values for hire/raise/promotion, deferral rates (old and new where recorded) for enrollment/escalation events, job level for promotions, and amount for match contributions.
- **FR-005**: Events MUST be ordered chronologically by effective date with a deterministic tiebreaker, so the same employee renders identically on every load.
- **FR-006**: Events MUST be grouped by simulation year, ordered oldest-first (the view lands on the employee's first simulation year and reads forward in time), and both the display and the retrieval interface MUST paginate by simulation year from earliest to latest so large histories load incrementally.
- **FR-007**: For each simulation year present, the system MUST show a state strip from that year's workforce snapshot including at minimum: employment status, compensation, enrollment state, current deferral rate, employee contribution totals, employer match amount, and employer core amount. Identity fields (employee SSN as stored — already masked at census creation — and birth date) MAY be displayed without further masking; no snapshot field needs to be excluded for privacy reasons.
- **FR-008**: An employee present in snapshots but absent from the event history MUST still render their per-year state strips, with the events area explicitly marked empty.
- **FR-009**: A lookup with no matching data MUST produce an explicit "no records found for this employee in this scenario" state, distinct from the empty-scenario state and never a blank page or error.
- **FR-010**: The system MUST expose a read-only retrieval interface returning an employee's merged event history and per-year snapshot state for a given scenario, paginated by simulation year, honoring the same access controls as the rest of Studio's scenario data.
- **FR-011**: The timeline view MUST be reachable by a stable, shareable address encoding the scenario and employee_id, so any surface showing an employee_id can link to it and users can pass links to colleagues.
- **FR-012**: The view MUST provide no mechanism to create, edit, delete, or annotate events or snapshots — strictly read-only. This applies equally to the filter list and the comparison view.
- **FR-013**: Users MUST be able to filter the selected scenario's employees by attributes — at minimum employment status, job level, simulation year, enrollment/participation state, and presence of deferral escalations — and open any result's timeline directly from the list.
- **FR-014**: The filter result list MUST show enough identifying columns to choose among matches (at minimum employee_id, status, level, compensation), MUST paginate large result sets, and MUST state plainly when no employees match.
- **FR-015**: From an employee's timeline, users MUST be able to select one additional scenario and view the same employee's timeline and per-year state from both scenarios side by side, aligned by simulation year, with each side clearly labeled by scenario.
- **FR-016**: In comparison view, each scenario's column MUST be as complete and faithful as the single-scenario view (FR-002 through FR-008 apply per scenario); years present in only one scenario MUST be visibly marked, and an employee absent from one scenario MUST be reported as such in that column without degrading the other.
- **FR-017**: Comparison is limited to two scenarios at a time; the shareable address (FR-011) MUST also encode a comparison view (both scenarios + employee_id) so comparisons can be deep-linked and shared.

### Key Entities

- **Employee Event**: one immutable occurrence in an employee's simulated lifecycle, identified by a unique event id; carries employee_id, scenario identity, event type, effective date, simulation year, and type-specific details (compensation values, old/new deferral rates, job level, contribution amount).
- **Employer Match Contribution Event**: an employer match contribution recorded for an employee in a year; stored separately from the primary event history but presented in the same timeline.
- **Yearly Workforce State**: the employee's year-end snapshot for a simulation year — status, compensation, enrollment/deferral state, contribution and employer-amount totals — used as the cross-check against that year's events.
- **Scenario**: the named simulation dataset (one isolated database per scenario) within which lookups and filters occur; the unit of selection for this feature. Comparison view reads two scenarios at once, each faithfully from its own dataset.
- **Employee Filter**: a set of attribute criteria (status, level, year, enrollment/participation state, escalation presence) evaluated against a scenario's year-end snapshots to produce a clickable shortlist of employees.

## Assumptions

- HCE status determination is not currently recorded as an event or snapshot field, so it does not appear in the timeline or state strip; when the platform records it, FR-002's "all event types present" clause picks it up automatically.
- Employer core contributions exist only as year-end amounts, so they belong to the state strip (FR-007), not the timeline.
- "Balance-relevant fields" from the issue is interpreted as the snapshot's contribution totals and employer amounts; the platform does not track account balances.
- Deep links from specific existing pages (which surfaces get the link affordance first) is a rollout detail decided during planning; FR-011 only guarantees the stable address exists.
- The view reads whichever scenario databases Studio already has access to; no new data movement or retention behavior is introduced. Comparison view opens a second scenario's dataset read-only alongside the first.
- Cross-scenario identity relies on census employee IDs being shared across scenarios built from the same census; the feature does not attempt to match simulation-generated hires across scenarios (they carry run-specific IDs and are reported as absent from the other scenario).
- Two scenarios is the comparison limit for this feature; three-plus-way comparison, aggregate scenario diffing, and highlighting/computing differences automatically (beyond visual juxtaposition) are possible follow-ups.
- Attribute filters evaluate year-end snapshot state; filtering on event-level predicates (e.g., "had a raise larger than X") is out of scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst can go from "I have an employee_id" to reading that employee's full multi-year history in under 30 seconds, with zero hand-written queries.
- **SC-002**: For any employee in a built scenario, the timeline is complete and faithful: every event a direct query of the underlying stores returns for that employee appears in the view, with matching dates and values — verified exactly, not sampled.
- **SC-003**: Given a seeded event-vs-state inconsistency (e.g., terminated status with no termination event), a reviewer unfamiliar with the feature can locate the inconsistent year from the view alone, without running a query.
- **SC-004**: First page of results (the employee's first simulation year) renders within 3 seconds on a typical multi-year scenario database.
- **SC-005**: A shared link to a specific employee's timeline — or to a two-scenario comparison — opens directly to that populated view in a fresh session, with no manual re-entry of scenario or employee_id.
- **SC-006**: An analyst with no employee_id in hand can go from a question ("who was terminated in 2026 with escalations?") to reading a matching employee's timeline in under one minute, using attribute filters alone — zero hand-written queries.
- **SC-007**: Given two scenarios built from the same census with a seeded plan-design difference, a reviewer can identify the simulation year where a specific employee's outcomes diverge using the side-by-side view alone, and each column matches a direct query of its own scenario exactly.
