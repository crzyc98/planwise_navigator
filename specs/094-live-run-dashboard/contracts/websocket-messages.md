# Contract: API → Frontend WebSocket Messages

**Endpoint**: `WS /ws/simulation/{run_id}` (existing route, message protocol extended)
**Producer**: `planalign_api/websocket/handlers.py` + `TelemetryService`
**Consumer**: `planalign_studio/services/websocket.ts` (`useRunTelemetry`)

All messages are JSON objects discriminated by `type`. Clients MUST ignore unknown `type` values.

## Connection sequence

1. Client connects (initial, after refresh, or on reconnect).
2. Server immediately sends `snapshot` with the full `RunTelemetrySnapshot` (FR-009/FR-013). If the run is unknown (e.g., API restarted), server sends `snapshot` with `status` from the run registry and empty stats; client falls back to REST polling.
3. Server then streams `update` / `milestone` messages as they occur.
4. Server sends `heartbeat` after 30s of silence (existing behavior, unchanged).
5. On terminal state, server sends a final `update` (status terminal) and a `milestone` (kind=terminal); connection stays open until client closes.

## Messages

### snapshot
```json
{"type":"snapshot","data":{ /* RunTelemetrySnapshot — see data-model.md */ }}
```
Sent exactly once per (re)connect, always before any `update`.

### update
Incremental live state; replaces same-named fields client-side. Throttled server-side to ≥1s between sends.
```json
{"type":"update","data":{
  "run_id":"...","status":"running","progress":42,
  "current_stage":"EVENT_GENERATION","current_year":2026,"total_years":3,"start_year":2025,
  "performance_metrics":{"memory_mb":512.0,"memory_pressure":"low","elapsed_seconds":30.5,
                          "events_generated":1500,"events_per_second":50.0},
  "event_counts":{"by_type":{"HIRE":142},"by_year":{"2025":{"HIRE":142}},"total":1204,"as_of_year":2025},
  "last_update_at":"..."}}
```

### milestone
```json
{"type":"milestone","data":{"sequence":17,"timestamp":"...","kind":"year_completed",
  "severity":"info","year":2025,"stage":null,
  "message":"Year 2025 complete — 142 hires, 98 terminations (48.2s)",
  "detail":{"event_counts":{"HIRE":142,"TERMINATION":98},"duration_seconds":48.2}}}
```
Client appends by `sequence`; duplicates (already present in snapshot) MUST be discarded by sequence number.

### heartbeat
```json
{"type":"heartbeat"}
```
Counts as liveness for staleness detection; carries no data.

## Removed from protocol

- `recent_events` (per-employee rows) is no longer consumed by the run screen; the field may remain in payloads during transition but the UI MUST NOT render it (spec FR-003).

## Client obligations

- Reconnect with exponential backoff (2s·2^n, max 5 attempts), counter held outside React state (FR-012).
- Treat any message (incl. heartbeat) as liveness; mark display stale after 15s of silence (FR-008).
- After retry exhaustion, switch to REST polling (see rest-telemetry-snapshot.md) and retry WS every 30s (FR-014).
- On `snapshot`, fully replace local state (never merge into possibly-stale state).
