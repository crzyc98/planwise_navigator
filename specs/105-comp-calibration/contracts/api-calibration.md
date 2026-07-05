# API Contract: Calibration

New router `planalign_api/routers/calibration.py`, included from `planalign_api/main.py`. Backs the Studio calibration panel (FR-012/FR-013). All payloads are Pydantic v2 models.

## POST `/api/calibration/run`

Enqueue a calibration run for a year range under a parameter set (issue #380: the build takes minutes, so it runs as a background job — POST returns `202` with a `run_id` immediately and clients poll `GET /api/calibration/runs/{run_id}`). Jobs targeting the same explicit `database_path` serialize on a per-DB lock; `database_path: null` runs use isolated timestamped DBs and never contend.

### Request body

```json
{
  "start_year": 2025,
  "end_year": 2029,
  "database_path": null,
  "params": {
    "target_growth_pct": 0.035,
    "cola_rate": 0.025,
    "merit_budget": 0.03,
    "new_hire_mix": { "1": 0.4, "2": 0.3, "3": 0.2, "4": 0.1 }
  }
}
```

- `database_path` null → isolated calibration DB (never shared dev DB).
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
- On `status: "failed"`, `error` carries the message and `error_status` the HTTP-equivalent code the old sync endpoints returned: `409` for the prerequisite-DC-tables guard, `500` for unexpected build/runtime failures. The Studio API client rethrows these as `ApiError`, so panel error handling is unchanged.

## Studio panel contract (`CalibrationPanel.tsx`)

- Four sliders: **target growth**, **COLA**, **merit**, **new-hire mix**.
- On change (debounced) → `POST /api/calibration/run` → render per-year **avg-comp** line chart and **growth-vs-target** chart.
- Displayed values MUST equal the CLI output for identical params (FR-013/SC-006).
