# API Contract: Calibration

New router `planalign_api/routers/calibration.py`, included from `planalign_api/main.py`. Backs the Studio calibration panel (FR-012/FR-013). All payloads are Pydantic v2 models.

## POST `/api/calibration/run`

Enqueue a calibration run for an exact workspace baseline or merged scenario target (issue #380: the build takes minutes, so it runs as a background job — POST returns `202` with a `run_id` immediately and clients poll `GET /api/calibration/runs/{run_id}`). Workspace requests resolve and copy a completed, provenance-matched scenario database into a disposable isolated database. They never accept a client database path or read `dbt/simulation.duckdb`.

### Request body

```json
{
  "start_year": 2025,
  "end_year": 2029,
  "workspace_id": "workspace-id",
  "scenario_id": "scenario-id",
  "params": {
    "target_growth_pct": 0.035,
    "cola_rate": 0.025,
    "merit_budget": 0.03,
    "new_hire_age_distribution": [{ "age": 25, "weight": 1.0 }]
  }
}
```

- `scenario_id` selects the exact merged scenario config; omit it to target the workspace baseline.
- Omitted years default from that target config. An explicit override updates both the materialized config/dbt vars and Python schedule.
- The source completed run must match workspace ID, census/config fingerprints, random seed, and inclusive horizon. Missing or stale inputs fail at POST with `409`.
- `config_path` and `database_path` are rejected for workspace requests. Legacy/CLI-style requests must name an explicit isolated database.
- `params` reuses `CalibrationParameterSet` (see data-model.md); omitted fields fall back to config defaults.

### Response 202

```json
{ "run_id": "cal_3f2a9c1b04de", "status": "queued" }
```

### Error responses (at POST)

| Status | Condition | Body |
|--------|-----------|------|
| 422 | Invalid range / params out of range | FastAPI validation detail |
| 404 | Unknown `workspace_id` | `{ "detail": "Workspace <id> not found" }` |
| 409 | Missing census or no matching completed run | Actionable prerequisite detail |

Build-time failures surface on the job record (below), not the POST.

## GET `/api/calibration/runs/{run_id}`

Poll a calibration job. `404` for unknown/pruned run ids (the registry keeps the last 20 finished jobs, in memory).

```json
{
  "run_id": "cal_3f2a9c1b04de",
  "kind": "run",
  "status": "queued | running | completed | failed",
  "created_at": "2026-07-05T12:00:00",
  "completed_at": null,
  "context": {
    "workspace_id": "workspace-id",
    "scenario_id": "scenario-id",
    "source_scenario_id": "scenario-id",
    "source_run_id": "run-uuid",
    "config_fingerprint": "sha256",
    "census_fingerprint": "sha256",
    "random_seed": 42,
    "start_year": 2025,
    "end_year": 2029
  },
  "results": [
    {
    {
      "simulation_year": 2025,
      "avg_compensation": 98400.0,
      "yoy_growth_pct": null,
      "target_growth_pct": 0.035,
      "growth_delta_pct": null,
      "headcount": 10000,
      "new_hire_avg_comp": 86300.0,
      "existing_avg_comp": 98400.0,
      "new_hire_gap": -12100.0
    }
  ],
  "outcome": null,
  "error": null,
  "error_status": null
}
```

- `results` is set on completion for `kind: "run"`; `outcome` (the `AutoCalibrationResult`) for `kind: "optimize"` (`POST /api/calibration/optimize` follows the same enqueue/poll contract).
- Optimization uses `objective: "max_annual_error"`. It converges only when every post-baseline year is within `tolerance_pct`; the outcome includes each year's delta, `max_abs_error_pct`, and the exact inclusive horizon.
- On `status: "failed"`, `error` carries the message and `error_status` the HTTP-equivalent code the old sync endpoints returned: `409` for the prerequisite-DC-tables guard, `500` for unexpected build/runtime failures. The Studio API client rethrows these as `ApiError`, so panel error handling is unchanged.

## POST `/api/calibration/apply`

Accepts the completed job's `context`, `best_params`, and whole-number `target_comp_growth_pct`. The API rechecks the current target config, census fingerprint, seed, and horizon before writing. A stale context returns `409`. The exact optimizer ranges and lever values are merged into the workspace base config and scenario overrides; the response reports each scenario success/failure and never reports global success when any scenario failed.

## Studio panel contract (`CalibrationPanel.tsx`)

- The analyst selects workspace baseline or one scenario. All visible held-fixed inputs and the exact horizon hydrate from that target.
- Auto-calibration → `POST /api/calibration/optimize` → render per-year **avg-comp** and **growth-vs-target** results.
- Apply persists `outcome.best_params`, including exact evaluated salary ranges; display rounding never feeds persistence.
- Displayed values MUST equal the CLI output for identical params (FR-013/SC-006).
