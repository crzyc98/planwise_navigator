# API Contract: Employee Timeline

**Feature**: 114-employee-event-timeline | **Base prefix**: `/api/workspaces` (registered in `planalign_api/main.py`)

Both endpoints are read-only GETs, subject to the same shared-token auth and workspace/scenario validation as all existing scenario-scoped routes. Workspace and scenario IDs are path-traversal-validated by `DatabasePathResolver`. A missing workspace/scenario → `404`; a scenario whose database cannot be resolved → `404` with a "no results database" detail (distinct from employee-not-found, per the empty-scenario edge case).

---

## 1. Employee discovery (autocomplete + attribute filter)

```
GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/employees
```

### Query parameters

| Param | Type | Default | Constraints | Purpose |
|-------|------|---------|-------------|---------|
| `q` | string | — | trimmed; case-insensitive prefix | Autocomplete mode (US1/FR-001a) |
| `status` | string | — | matches `employment_status` | Filter (US4/FR-013) |
| `level` | int | — | ≥ 1 | Filter |
| `year` | int | latest year in DB | — | Which snapshot year filters evaluate against |
| `enrolled` | bool | — | — | Filter on `is_enrolled_flag` |
| `has_escalations` | bool | — | — | Filter on `has_deferral_escalations` |
| `page` | int | 1 | ≥ 1 | FR-014 pagination |
| `page_size` | int | 50 | 1–200 | |

`q` and attribute filters may combine; all predicates AND together. All values are SQL-bound parameters — never interpolated.

### Response `200` — `EmployeeSearchResponse`

```json
{
  "results": [
    {
      "employee_id": "EMP_2025_001",
      "employment_status": "terminated",
      "level_id": 3,
      "current_compensation": 125000.0,
      "simulation_year": 2026
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 50
}
```

- Empty match → `200` with `results: []`, `total: 0` (FR-014 "states plainly"; UI renders the no-match message).
- Results ordered by `employee_id` ascending (deterministic paging).

### Errors

| Code | Condition |
|------|-----------|
| 404 | Workspace or scenario not found; scenario database not resolvable |
| 422 | Parameter validation (FastAPI/Pydantic) |

---

## 2. Employee timeline (merged events + per-year state)

```
GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/employees/{employee_id}/timeline
```

`employee_id` is normalized server-side: surrounding whitespace stripped, matched case-insensitively (FR-001).

### Query parameters

| Param | Type | Default | Constraints | Purpose |
|-------|------|---------|-------------|---------|
| `start_year` | int | employee's first available year | — | Page start (oldest-first, FR-006) |
| `years` | int | 3 | 1–20 | How many years per page |

### Response `200` — `EmployeeTimelineResponse`

```json
{
  "workspace_id": "ws1",
  "scenario_id": "baseline",
  "employee_id": "EMP_2025_001",
  "employee": {
    "employee_id": "EMP_2025_001",
    "employee_ssn": "***-**-6789",
    "employee_birth_date": "1988-04-12",
    "employee_hire_date": "2025-01-15"
  },
  "available_years": [2025, 2026, 2027],
  "start_year": 2025,
  "years_requested": 3,
  "years": [
    {
      "simulation_year": 2025,
      "events": [
        {
          "event_id": "a1b2...",
          "source": "yearly",
          "event_type": "hire",
          "simulation_year": 2025,
          "effective_date": "2025-01-15",
          "event_details": "New hire at level 3",
          "compensation_amount": 125000.0,
          "previous_compensation": null,
          "deferral_rate": null,
          "prev_deferral_rate": null,
          "level_id": 3
        },
        {
          "event_id": "c3d4...",
          "source": "employer_match",
          "event_type": "employer_match",
          "simulation_year": 2025,
          "effective_date": "2025-12-31",
          "event_details": null,
          "compensation_amount": 3750.0,
          "previous_compensation": null,
          "deferral_rate": 0.06,
          "prev_deferral_rate": null,
          "level_id": null
        }
      ],
      "state": {
        "simulation_year": 2025,
        "employment_status": "active",
        "current_compensation": 125000.0,
        "current_deferral_rate": 0.06,
        "is_enrolled": true,
        "employer_match_amount": 3750.0,
        "employer_core_amount": 1250.0,
        "...": "remaining YearState fields per data-model.md"
      }
    }
  ]
}
```

### Contract guarantees

- **Completeness (FR-002/FR-003, SC-002)**: every row in `fct_yearly_events` and `fct_employer_match_events` for this employee/scenario within the requested years appears exactly once. No event-type allowlist.
- **Ordering (FR-005)**: events sorted by `(simulation_year, effective_date, COALESCE(event_sequence, 999), event_id)`; identical across calls.
- **Pagination (FR-006)**: `available_years` always lists every year with events or a snapshot row (ascending) so the client can page/prefetch; `years` contains only `[start_year, start_year + years)` intersected with available years.
- **Snapshot-only years (FR-008)**: a year with a snapshot row but no events appears with `events: []` and populated `state`.
- **Event-only years**: a year with events but no snapshot row appears with `state: null`.
- **Not found (FR-009)**: employee has no events **and** no snapshot rows → `200` with `employee: null`, `available_years: []`, `years: []`. (Deliberately `200`, not `404`: the scenario resolved fine; "no records" is a domain answer the comparison view renders in one column.)
- **Read-only (FR-012)**: no non-GET methods exist on these paths.

### Errors

| Code | Condition |
|------|-----------|
| 404 | Workspace or scenario not found; scenario database not resolvable |
| 422 | Parameter validation |

---

## 3. Comparison (US5) — client-composed, no endpoint

The comparison view issues endpoint 2 twice (same `workspace_id` + `employee_id`, different `scenario_id`) and composes columns client-side per data-model.md. Deep-link contract (FR-011/FR-017), using Studio's HashRouter:

```
/#/timeline/{workspaceId}/{scenarioId}/{employeeId}              # single
/#/timeline/{workspaceId}/{scenarioId}/{employeeId}?compare={scenarioId2}   # comparison
```

The compare picker must not offer the current scenario (`scenarioId2 ≠ scenarioId`).
