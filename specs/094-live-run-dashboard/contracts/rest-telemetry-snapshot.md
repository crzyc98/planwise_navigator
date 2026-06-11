# Contract: REST Run Telemetry Snapshot (polling fallback / refresh restore)

**Endpoint**: `GET /api/scenarios/{scenario_id}/run/telemetry`
**Router**: `planalign_api/routers/simulations.py`
**Auth/scope**: same as existing scenario endpoints (workspace-scoped, localhost app)

## Purpose

Single canonical snapshot used for: page-refresh restore before/while WS connects (FR-009), degraded polling when WS is unavailable (FR-014), and terminal-state safety net (FR-015). Response body `data` is byte-compatible with the WS `snapshot` message `data`.

## Response — 200

```json
{
  "run": {
    "run_id": "uuid",
    "status": "running",          // pending | running | completed | failed | cancelled | not_run
    "error_message": null
  },
  "telemetry": { /* RunTelemetrySnapshot | null */ }
}
```

- `telemetry` is `null` when no in-memory state exists (no run since API start). Clients then rely on `run.status` alone — e.g., after an API restart mid-run, milestone history is absent by design (clarification 2026-06-10) but status/terminal detection still works.
- For `not_run` scenarios: `run.run_id` is null, `telemetry` is null.

## Errors

- `404` — scenario not found.
- No `409`/`423`: the endpoint never touches the scenario DuckDB (in-memory state only), so it is always safe to call during a run.

## Performance

- Pure in-memory read; target <50ms. Polling cadence: client polls every 5s in degraded mode (well under the constitution's 2s dashboard query budget).

## Related fix (same router)

`GET /api/scenarios/{scenario_id}/run/status` currently fabricates `progress=100/completed` from scenario status when the run is not in the in-memory registry. It MUST be corrected to report the run registry's real values, with the scenario's persisted status as fallback, and never report a terminal scenario as `running`.
