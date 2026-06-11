# Research: Live Simulation Run Dashboard

**Feature**: 094-live-run-dashboard | **Date**: 2026-06-10

All Technical Context unknowns resolved. Decisions below are grounded in direct inspection of the current code (`planalign_api/services/simulation/service.py`, `output_parser.py`, `telemetry_service.py`, `websocket/handlers.py`, `planalign_studio/services/websocket.ts`, `components/SimulationControl.tsx`).

## R1. Source of truth for live progress/counts: structured stdout protocol

**Decision**: Orchestrator pipeline hooks emit single-line JSON records to stdout with a sentinel prefix (`PLANALIGN_TELEMETRY|{...}`) at stage and year boundaries. The API's existing stdout streaming loop parses sentinel lines as JSON; the current regex heuristics remain only as a fallback for non-sentinel lines.

**Rationale**: Today the API *guesses* stage/year/event-counts by regexing arbitrary log text (`STAGE_PATTERNS`, `(\d+)\s*events?`) — this is the root cause of janky/incorrect telemetry (e.g., any line containing "complet" flips the stage to REPORTING; the "events" regex matches unrelated lines). The subprocess boundary already exists and stdout is already streamed line-by-line, so a machine-readable line protocol is the minimal-change path to deterministic telemetry. It also lands in `simulation.log` automatically, aiding audit (Constitution IV).

**Alternatives considered**:
- *API polls the scenario DuckDB during the run* — rejected: DuckDB single-writer locks; explicitly excluded by spec clarification.
- *Orchestrator pushes HTTP callbacks to the API* — rejected: couples orchestrator to the Studio API, breaks CLI-only usage, adds failure modes.
- *Shared file (JSON status file) written by orchestrator, watched by API* — workable but adds fs-watching complexity; stdout streaming already exists and is ordered.

## R2. Exact per-event-type counts at year boundaries

**Decision**: After each year's `EVENT_GENERATION` stage completes, the telemetry emitter runs one aggregate query (`SELECT event_type, COUNT(*) ... WHERE simulation_year = ?`) using the orchestrator's *own in-process database connection*, and includes the counts in the year-boundary telemetry record.

**Rationale**: The orchestrator already holds the write connection, so an in-process read causes no lock conflict. One aggregate per year is negligible. Counts derived from `fct_yearly_events` are exact by construction, satisfying FR-011 (final UI counts match persisted results).

**Alternatives considered**:
- *Count events as generated in Python* — rejected: SQL-mode generation happens inside dbt models; Python never sees individual events.
- *Parse counts from dbt output* — rejected: that is the fragile status quo.

## R3. Backend telemetry state: extend `TelemetryService` with per-run state

**Decision**: Extend the existing `TelemetryService` singleton with a `RunTelemetryState` per run: latest snapshot, milestone list (capped ~200), per-year event counts, perf-sample ring buffer (capped ~600), and terminal status. On WebSocket subscribe, send one `snapshot` message containing the full state, then incremental `update`/`milestone` messages. Terminal state is retained in memory until a new run starts for the same scenario (not cleared at completion).

**Rationale**: `TelemetryService` already implements queue-based pub/sub with last-message replay on subscribe — the snapshot pattern is a natural extension and directly satisfies FR-009/FR-013 (refresh/reconnect restore). Keeping terminal state (instead of today's `clear_telemetry`) closes the "stuck on running" hole (FR-015). In-memory only, per spec clarification.

**Alternatives considered**:
- *Persist milestones to the run directory* — rejected by clarification (in-memory, active run only).
- *New separate service class* — rejected: state and pub/sub belong together; splitting would duplicate listener bookkeeping.

## R4. Polling fallback + refresh restore: REST snapshot endpoint

**Decision**: Add `GET /api/scenarios/{scenario_id}/run/telemetry` returning the same `RunTelemetrySnapshot` JSON the WS `snapshot` message carries (plus run status). Frontend uses it (a) on mount before/while WS connects, (b) as a 5s polling loop when WS reconnect attempts are exhausted, (c) as the terminal-state safety net. Also fix the existing `get_run_status` endpoint, which currently fabricates values when no active run is tracked.

**Rationale**: One canonical snapshot shape serves WS resync, page-refresh restore, and degraded polling (FR-009, FR-013, FR-014, FR-015) — single contract, no drift. REST works through proxies that block WS upgrades (corporate-firewall constraint).

**Alternatives considered**:
- *SSE fallback* — rejected: another long-lived connection type with the same proxy risks; polling is simpler and sufficient at 5s cadence.
- *Reuse `/run/status` as-is* — rejected: it lacks stats/milestones and returns placeholder data.

## R5. Frontend hook rewrite: refs for retry state, explicit connection state machine

**Decision**: Rewrite `useSimulationSocket` as `useRunTelemetry(runId, scenarioId)` with: retry counter and timers held in `useRef` (the current bug: `onclose` reads `status.reconnectAttempts` from a stale closure, so backoff never escalates and the retry cap misfires); explicit states `connecting → live → stale → reconnecting → polling → terminal`; staleness timer flags `stale` if no message (heartbeats count) for 15s; after 5 failed reconnects switch to polling and keep a low-frequency WS retry (every 30s) to upgrade back to live.

**Rationale**: Fixes the reported "doesn't work well" defects at the root: stale-closure retry logic, silent data loss on reconnect (server snapshot now resyncs), and indefinite "running" display (polling + terminal retention guarantee convergence). The state machine maps 1:1 onto the `ConnectionStatusBadge` UI states.

**Alternatives considered**:
- *Adopt a WS client library (e.g., reconnecting-websocket)* — rejected: small dependency surface preferred (corporate environment); the logic is ~100 lines once state lives in refs.
- *Patch the existing hook minimally* — rejected by clarification (full reliability overhaul chosen).

## R6. Trend chart: Recharts `LineChart` with bounded client buffer

**Decision**: Use Recharts (already in `package.json`, used by the DC contribution analytics from feature 066) for a dual-axis line chart (events/sec, memory MB). Client keeps at most 600 samples; beyond that, downsample by dropping every other point (keeps render O(constant)).

**Rationale**: No new dependency; consistent look with existing analytics; 600 points at one sample per ~2s covers a 20-minute run before downsampling, satisfying SC-006.

**Alternatives considered**: hand-rolled SVG sparkline — more code for less capability; canvas charting lib — new dependency, blocked-CDN risk if misconfigured.

## R7. Milestone derivation

**Decision**: Milestones are created server-side in `TelemetryService` from structured records: `run_started`, `stage_started`/`stage_completed` (per year), `year_completed` (with counts + duration), `warning`, `error`, and terminal (`completed`/`failed`/`cancelled`). Warning/error milestones come from the existing per-line severity classifier (already feeding `simulation.log`), deduplicated and rate-limited (max ~20 warning milestones per run) to keep the feed readable.

**Rationale**: Server-side derivation means every client (including ones that connect late) sees identical history via the snapshot — required by FR-009. Stage grain matches the 6-stage workflow already displayed in the UI's stage chips.

**Alternatives considered**: client-side derivation from raw updates — rejected: history would differ per client and vanish on refresh.
