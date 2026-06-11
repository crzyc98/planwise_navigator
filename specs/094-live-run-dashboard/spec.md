# Feature Specification: Live Simulation Run Dashboard

**Feature Branch**: `094-live-run-dashboard`
**Created**: 2026-06-10
**Status**: Draft
**Input**: User description: "When running a scenario in the UI there is a running log that isn't really useful, and there is a placeholder for real-time stats. Improve the running-scenario view with meaningful live information."

## Clarifications

### Session 2026-06-10

- Q: How fresh must the live event-type counts be during a run? → A: Update at year/stage boundaries — counts are exact when each year's event generation completes; no mid-run database queries while the simulation holds write locks. Progress and throughput still update continuously.
- Q: What happens to the current raw per-employee event stream panel? → A: Removed entirely; the milestone activity feed fully replaces it. Deep debugging remains in the existing run logs (simulation.log / run detail page).
- Q: How durable must the milestone/activity history be? → A: In-memory for the active run only; page refresh/reconnect replays it. History does not survive an API server restart mid-run.
- Q: How should the unreliable real-time WebSocket telemetry be scoped within this feature? → A: Full reliability overhaul as part of this feature: correct reconnect with exponential backoff, full state resync on (re)connect, staleness detection, and guaranteed terminal-state delivery so the UI never hangs in "running".
- Q: If the live connection cannot be (re)established, what should the dashboard do? → A: Automatically fall back to periodic status polling over the regular API (slower cadence) with a visible degraded-connection indicator.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See Meaningful Live Stats While a Simulation Runs (Priority: P1)

An analyst starts a scenario from the Simulation Control screen. Instead of a placeholder box labeled "Real-time Performance Graph Placeholder," they see live, simulation-meaningful statistics updating as the run progresses: cumulative event counts broken down by type (hires, terminations, promotions, raises, enrollments), the current simulation year and how many years remain, and per-year progress. The analyst can tell at a glance whether the run is producing plausible results (e.g., hires roughly tracking growth targets) before it even finishes.

**Why this priority**: This is the core gap the user identified — the screen reserves space for real-time stats but shows nothing. During multi-minute, multi-year runs, the analyst currently has no insight into what the simulation is actually doing. Live business-level stats deliver the most value per unit of screen space.

**Independent Test**: Start any multi-year simulation and observe the stats panel. It can be fully tested by verifying that event-type counts and year progress update during the run and match the final database totals when the run completes.

**Acceptance Scenarios**:

1. **Given** a simulation is running, **When** a year's event generation completes, **Then** the dashboard shows exact cumulative counts per event type updated through that year, without manual refresh.
2. **Given** a 3-year simulation, **When** year 2 begins, **Then** the dashboard clearly indicates "Year 2 of 3" with per-year completion shown alongside overall progress.
3. **Given** a simulation completes, **When** the analyst compares the final on-screen event counts to the stored results, **Then** the counts match.
4. **Given** no simulation is running, **When** the analyst views the screen, **Then** the stats area shows an informative idle state rather than empty placeholders.

---

### User Story 2 - Useful Activity Feed Instead of Raw Event Noise (Priority: P2)

Today the right-hand "Event Stream" panel shows individual employee-level events (e.g., one row per hire with an employee ID), which scrolls past too quickly to read and conveys nothing actionable. The analyst instead sees a milestone-oriented activity feed: stage transitions ("Year 2025: Event Generation started"), per-year summaries ("Year 2025 complete — 142 hires, 98 terminations, 12.3s"), warnings, and errors. Each entry is timestamped and the most recent entries are visible without scrolling.

**Why this priority**: The user explicitly called the current log "not really useful." Replacing noise with milestones turns the panel into a genuine monitoring tool, but the run is still observable without it via User Story 1.

**Independent Test**: Run a simulation and verify the feed contains one entry per stage transition and per completed year (rather than hundreds of per-employee rows), with warnings/errors surfaced distinctly.

**Acceptance Scenarios**:

1. **Given** a running simulation, **When** a workflow stage begins or completes, **Then** a timestamped milestone entry appears in the activity feed.
2. **Given** a simulation year completes, **When** the analyst reads the feed, **Then** a single summary entry shows that year's headline numbers (event counts, duration).
3. **Given** a warning or validation issue occurs during the run, **Then** it appears in the feed visually distinguished from informational milestones.
4. **Given** a long-running simulation, **When** the analyst leaves and returns to the screen, **Then** the feed still shows the run's milestone history, not just entries received while the screen was open.

---

### User Story 3 - Live Performance Trend Chart (Priority: P3)

In the space currently occupied by the placeholder, the analyst sees a small live chart of run performance over time — events processed per second and memory usage — so they can spot slowdowns or memory pressure during long runs.

**Why this priority**: Useful for power users diagnosing slow runs, but the numeric tiles already show instantaneous values; the trend view is an enhancement on top of Stories 1–2.

**Independent Test**: Run a simulation and verify the chart accumulates data points over the duration of the run and renders the trend without degrading UI responsiveness.

**Acceptance Scenarios**:

1. **Given** a running simulation, **When** telemetry updates arrive, **Then** the chart appends points and shows the trend for the duration of the run.
2. **Given** a run lasting many minutes, **When** the chart accumulates many points, **Then** the display remains readable and the page remains responsive.
3. **Given** the simulation completes or is stopped, **Then** the final trend remains visible until the analyst navigates away.

---

### User Story 4 - Reliable Live Telemetry (Priority: P1)

Today the live connection feeding the run screen is unreliable: reconnection behaves incorrectly (retry backoff and the retry cap are broken), updates missed while disconnected are lost forever, and if the connection drops near the end of a run the screen can stay stuck on "running" even though the simulation finished. The analyst gets a dependable feed: brief network blips recover automatically and silently, reconnecting always resynchronizes to the run's true current state, and if a live connection cannot be maintained at all the dashboard automatically degrades to periodic status updates with a visible indicator — so the screen always converges to the truth.

**Why this priority**: Every other story renders data from this channel; the user explicitly reported it "doesn't work well." Without a reliable feed, the dashboard's stats, feed, and chart cannot be trusted.

**Independent Test**: Kill and restore the network (or the connection) at various points during a run and verify the dashboard recovers, resyncs to true state, and always reaches the correct terminal state.

**Acceptance Scenarios**:

1. **Given** a running simulation, **When** the live connection drops briefly, **Then** it reconnects automatically with increasing backoff between attempts and the analyst sees at most a momentary staleness indicator.
2. **Given** updates were missed while disconnected, **When** the connection is re-established, **Then** the dashboard resynchronizes to the run's current full state (progress, stats, milestones) rather than resuming from stale values.
3. **Given** the live connection cannot be established after repeated attempts, **When** the run is still active, **Then** the dashboard automatically falls back to periodic status polling, keeps updating at the slower cadence, and shows a degraded-connection indicator.
4. **Given** the run reaches a terminal state (completed, failed, cancelled) while the client is disconnected or degraded, **Then** the dashboard still detects and displays the terminal state — it never remains stuck on "running".

---

### Edge Cases

- Telemetry connection drops mid-run: the dashboard indicates stale/disconnected state (e.g., "last update 30s ago"), reconnects automatically, and resyncs full state on reconnect rather than silently freezing values.
- Live connection unavailable for an extended period (e.g., proxy blocks it): the dashboard degrades to periodic polling and still reaches the correct terminal state.
- Simulation fails partway through a year: the activity feed must show the failure with the stage and year where it occurred; stats panels should freeze at last-known values, clearly marked as a failed run.
- Very fast runs (single year, small census): the dashboard should still render sensible final stats even if the run finishes before multiple updates arrive.
- Browser refresh mid-run: reopening the screen during an active run should restore current progress, stats, and milestone history rather than starting from an empty view.
- Simulation is stopped by the user: the dashboard reflects the cancelled state and stops updating.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: While a simulation is running, the system MUST display cumulative event counts grouped by event type (at minimum: hires, terminations, promotions, raises, enrollments), refreshed automatically at each year/stage boundary as that year's event generation completes; counts MUST be exact for all completed years. Mid-year streaming of counts is explicitly out of scope.
- **FR-002**: The system MUST display per-year progress (current simulation year, total years, and within-year stage progress) in addition to overall run progress.
- **FR-003**: The system MUST remove the raw per-employee event stream from the run screen entirely (no verbose toggle) and replace it with a milestone activity feed containing stage transitions, per-year completion summaries, warnings, and errors, each timestamped. Per-employee debugging detail remains available via the existing run logs.
- **FR-004**: Per-year completion summaries in the feed MUST include that year's event counts and elapsed duration.
- **FR-005**: Warnings and errors in the activity feed MUST be visually distinct from informational milestones.
- **FR-006**: The system MUST replace the performance graph placeholder with a live trend chart of throughput (events/second) and memory usage over the run's duration.
- **FR-007**: When no simulation is running, the dashboard MUST present a meaningful idle state (e.g., summary of the most recent run or a prompt to start one) instead of empty panels or placeholder text.
- **FR-008**: If live updates stop arriving while a run is marked active, the dashboard MUST indicate staleness (time since last update) within 30 seconds.
- **FR-009**: When a user opens or refreshes the screen during an active run, the dashboard MUST restore current progress, cumulative stats, and the milestone history accumulated so far.
- **FR-010**: When a run completes, fails, or is cancelled, the dashboard MUST freeze at final values and clearly label the terminal state.
- **FR-011**: Final on-screen cumulative event counts MUST match the persisted results of the run.
- **FR-012**: The live telemetry connection MUST reconnect automatically after a drop, using increasing backoff between attempts and a bounded retry limit that is actually enforced (the current retry logic miscounts attempts and MUST be corrected).
- **FR-013**: On every (re)connect during an active run, the dashboard MUST receive a full state snapshot (progress, cumulative stats, milestone history) so missed incremental updates never leave the display stale.
- **FR-014**: If the live connection cannot be maintained, the dashboard MUST automatically fall back to periodic status polling at a slower cadence and display a degraded-connection indicator; it MUST return to live updates if the connection is later restored.
- **FR-015**: Terminal states (completed, failed, cancelled) MUST be reliably delivered to the dashboard even across disconnects or degraded mode — the screen MUST never remain indefinitely in a "running" display for a run that has ended.

### Key Entities

- **Run Telemetry Snapshot**: The current state of an active run — run identifier, scenario, current year, total years, current stage, overall and per-year progress, instantaneous performance metrics.
- **Live Event Statistics**: Cumulative counts of generated events grouped by event type and by simulation year for the active run.
- **Milestone Entry**: A timestamped record of a significant run occurrence — stage start/completion, year completion summary, warning, error, or terminal state — with a severity level.
- **Performance Sample**: A timestamped point of throughput and memory usage used to render the trend chart.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: During an active run, an analyst can answer "what year is it on, how far along is it, and how many of each event type has it generated?" within 5 seconds of looking at the screen.
- **SC-002**: Event-type counts refresh within 5 seconds of each simulation year's event generation completing, and progress/throughput indicators visibly update at least every 5 seconds throughout the run.
- **SC-003**: The activity feed for a 5-year run contains on the order of dozens of entries (milestones), not hundreds-to-thousands (per-employee events), and every stage transition and year completion is represented.
- **SC-004**: Final dashboard event counts match persisted run results with 100% accuracy.
- **SC-005**: After a mid-run page refresh, the restored view reflects the run's true current state (progress, stats, milestones) within 3 seconds.
- **SC-006**: The dashboard remains responsive (no visible jank or frozen UI) for runs lasting 10+ minutes.
- **SC-007**: After a transient connection drop of up to 60 seconds mid-run, the dashboard automatically recovers and displays the run's true current state within 10 seconds of connectivity returning.
- **SC-008**: In 100% of runs that end (complete, fail, or are cancelled), the dashboard reaches the correct terminal display within 30 seconds — including when the live connection was lost or degraded to polling.

## Assumptions

- The existing live telemetry channel already conveys progress, stage, year, and performance metrics; this feature extends what is conveyed, how it is presented, and how reliably it is delivered (User Story 4) — but does not change how scenarios are executed.
- A regular request/response status endpoint exists (or can be extended) to serve the polling fallback and full-state snapshots; the run's current state is queryable on demand, not only via the live stream.
- Event counts by type are derived from the run's generated events as each year completes; the running pipeline reports them at year/stage boundaries, so no concurrent database reads against the simulation's write connection are needed.
- Milestone history for the active run is retained in memory for the duration of the run so reconnecting clients can replay it; it does not survive an API server restart mid-run, and long-term retention beyond the run is out of scope (the existing run logs/detail page covers post-run review).
- Single-run-at-a-time semantics are unchanged: the dashboard monitors the one active run in the workspace.
- The simulation history table and run detail pages are out of scope except where the idle state links to them.
