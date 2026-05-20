# API Contract: Match Census for Opt-Out Rate Configuration

**Branch**: `085-optout-match-census` | **Phase**: 1 Design

## New Endpoint

### POST `/api/workspaces/{workspace_id}/analyze-opt-out-rate`

Analyzes a census file to suggest a target opt-out rate based on the non-participant rate among recently hired employees (filtered by a configurable tenure lookback window).

**Router**: `planalign_api/routers/bands.py`
**Service**: `planalign_api/services/opt_out_service.OptOutAnalysisService`

---

#### Request

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `workspace_id` | `str` | Workspace identifier |

**Request Body** (`OptOutRateAnalysisRequest`):

```json
{
  "file_path": "uploads/census_2024.csv",
  "lookback_years": 3
}
```

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `file_path` | `string` | yes | — | Non-empty path to census file |
| `lookback_years` | `integer` | no | `3` | min: 1, max: 50 |

---

#### Responses

**200 OK** — Analysis completed successfully:

```json
{
  "suggested_rate": 0.082,
  "eligible_count": 147,
  "non_participant_count": 12,
  "total_eligible_in_census": 832,
  "excluded_null_tenure": 3,
  "lookback_years": 3,
  "hire_date_column_used": "hire_date",
  "analysis_type": "Non-participant rate for employees hired within last 3 years",
  "source_file": "uploads/census_2024.csv",
  "message": null
}
```

**200 OK** — No eligible employees in lookback window (suggested_rate is null):

```json
{
  "suggested_rate": null,
  "eligible_count": 0,
  "non_participant_count": 0,
  "total_eligible_in_census": 832,
  "excluded_null_tenure": 0,
  "lookback_years": 1,
  "hire_date_column_used": "employee_hire_date",
  "analysis_type": "Non-participant rate for employees hired within last 1 year",
  "source_file": "uploads/census_2024.csv",
  "message": "No eligible employees found within the 1-year lookback window. Try a longer lookback."
}
```

**400 Bad Request** — File not found or unsupported format:

```json
{ "detail": "File not found: uploads/census_2024.csv" }
```

**400 Bad Request** — No hire date column detected:

```json
{ "detail": "No hire date column found in census. Expected one of: hire_date, employee_hire_date, hiredate, start_date" }
```

**400 Bad Request** — No deferral rate column detected:

```json
{ "detail": "No deferral rate column found in census. Expected one of: employee_deferral_rate, deferral_rate" }
```

**500 Internal Server Error** — Unexpected failure:

```json
{ "detail": "Failed to analyze census for opt-out rate: <reason>" }
```

---

## Frontend API Service Contract

New function in `planalign_studio/services/api.ts`:

```typescript
export interface OptOutRateAnalysisRequest {
  file_path: string;
  lookback_years?: number;  // default 3
}

export interface OptOutRateAnalysisResult {
  suggested_rate: number | null;
  eligible_count: number;
  non_participant_count: number;
  total_eligible_in_census: number;
  excluded_null_tenure: number;
  lookback_years: number;
  hire_date_column_used: string;
  analysis_type: string;
  source_file: string;
  message: string | null;
}

export async function analyzeOptOutRate(
  workspaceId: string,
  request: OptOutRateAnalysisRequest,
): Promise<OptOutRateAnalysisResult>
```

---

## Unchanged Contracts

- `GET /api/workspaces/{workspace_id}/config` — no changes
- `PUT /api/workspaces/{workspace_id}/config` — no changes; `dc_plan.opt_out_rate_target` field is already part of the scenario config schema
- No new database columns; no dbt model changes
