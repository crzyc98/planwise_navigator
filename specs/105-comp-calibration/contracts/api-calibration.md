# API Contract: Calibration

New router `planalign_api/routers/calibration.py`, included from `planalign_api/main.py`. Backs the Studio calibration panel (FR-012/FR-013). All payloads are Pydantic v2 models.

## POST `/api/calibration/run`

Trigger a calibration run for a year range under a parameter set.

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

### Response 200

```json
{
  "run_id": "cal_2026-06-30T12-00-00",
  "results": [
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
  ]
}
```

### Error responses

| Status | Condition | Body |
|--------|-----------|------|
| 422 | Invalid range / params out of range | FastAPI validation detail |
| 409 | Prerequisite DC tables missing | `{ "detail": "Target database lacks DC tables; run a full simulation first." }` |
| 500 | Build/runtime failure | `{ "detail": "<message + correlation id>" }` |

## GET `/api/calibration/status/{run_id}` *(optional, if runs are async)*

Returns `{ "run_id", "state": "running|done|failed", "results": [...] }`. For v1 a synchronous `POST` is acceptable since a comp-only run is ~2–4 min; a streaming/websocket variant can reuse the existing telemetry channel later.

## Studio panel contract (`CalibrationPanel.tsx`)

- Four sliders: **target growth**, **COLA**, **merit**, **new-hire mix**.
- On change (debounced) → `POST /api/calibration/run` → render per-year **avg-comp** line chart and **growth-vs-target** chart.
- Displayed values MUST equal the CLI output for identical params (FR-013/SC-006).
