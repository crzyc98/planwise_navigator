# API Contract: Simulation Error Response

**Feature**: Census Path Validation
**Endpoint**: `POST /api/workspaces/{workspace_id}/simulations/{scenario_id}/runs`
**Method**: Execute Simulation

---

## Error Response Changes

### No New Endpoints

This feature **does not add new API endpoints**. It changes the error behavior of the existing simulation execution endpoint.

**Endpoint**: `POST /api/workspaces/{workspace_id}/simulations/{scenario_id}/runs`

---

## Existing Error Response Format (No Changes)

The endpoint already returns error responses with this format:

```json
{
  "run_id": "run-abc123",
  "status": "FAILED",
  "error_message": "[Error message string]",
  "error_code": "CONFIGURATION_ERROR",
  "completed_at": "2026-03-18T14:23:45.123456Z"
}
```

---

## Census Validation Errors

When census path validation fails, the error response will follow the same format as above with one of two error messages:

### Error 1: Missing Census Path

**Scenario**: `census_parquet_path` is absent or empty in scenario config

**Response Status**: 500 Internal Server Error (raised as exception during simulation startup)

**Response Body**:
```json
{
  "run_id": "run-def456",
  "status": "FAILED",
  "error_message": "census_parquet_path is required but was not found in the scenario config. Ensure a census file has been uploaded to the scenario folder before running.",
  "error_code": "CONFIGURATION_ERROR",
  "completed_at": "2026-03-18T14:30:12.123456Z"
}
```

**Frontend Display**: Error message shown in red in Simulation Status panel

**User Action**: Upload census file via scenario file manager and retry

---

### Error 2: Census File Not Found

**Scenario**: `census_parquet_path` is configured but file doesn't exist on disk

**Response Status**: 500 Internal Server Error (raised as exception during simulation startup)

**Response Body**:
```json
{
  "run_id": "run-ghi789",
  "status": "FAILED",
  "error_message": "Census file not found at '/workspaces/my-workspace/scenarios/my-scenario/data/census.parquet'. Upload a valid census parquet file to the scenario folder and retry.",
  "error_code": "CONFIGURATION_ERROR",
  "completed_at": "2026-03-18T14:35:22.123456Z"
}
```

**Frontend Display**: Error message shown in red, path included for debugging

**User Action**: Verify file exists at path, upload if missing, retry

---

## Client Error Handling

### Frontend Consumer (planalign_studio)

**Current Behavior**: Frontend already handles `error_message` field and displays it in UI.

**Change**: Message will now be clearer and more actionable (includes resolution steps).

**No frontend changes needed** — existing error display mechanism works as-is.

### CLI Consumer (if any)

If CLI commands call the simulation API:

**Current Behavior**: CLI receives error and displays it.

**Change**: Error message will be same as above (pre-validation, so CLI won't need changes).

---

## Error Logging Contract

**Logs Produced** (for observability and audit):

Logs will include execution context and correlation ID:

```
2026-03-18 14:23:45.123 ERROR [planalign_api] execute_simulation failed
Exception: ConfigurationError
Message: census_parquet_path is required but was not found in the scenario config.
Ensure a census file has been uploaded to the scenario folder before running.

Execution Context:
  scenario_id: my-scenario-123
  workspace_id: workspace-456
  correlation_id: a1b2c3d4
  timestamp: 2026-03-18T14:23:45.123456Z
  error_type: MISSING_PATH
```

**Log Fields**:
- `correlation_id` - Unique identifier for tracing across systems
- `scenario_id` - Identifies which scenario failed
- `workspace_id` - Identifies which workspace
- `error_type` - One of: MISSING_PATH, FILE_NOT_FOUND
- `timestamp` - When the error occurred (ISO 8601)

**Audit Trail**: All census path validation failures recorded with correlation ID for compliance reporting.

---

## WebSocket Telemetry (if applicable)

**No Changes**: Census path validation occurs before simulation starts, before telemetry streaming begins.

WebSocket subscribers will not receive telemetry for failed simulations (no events generated before validation fails).

---

## Backward Compatibility

**Breaking Change**: YES

**Impact**: Simulations without valid census paths will now fail instead of silently using default.

**User Action Required**: Upload census file to scenario before running simulation.

**Migration Path**:
1. User receives error in UI with clear message
2. User uploads census file via Studio
3. User retries simulation

**No API versioning needed** — error handling is internal; response format unchanged.

---

## Validation Contracts (Internal)

These internal validation points must be met:

### Input Contract

**Method**: `_validate_census(config: Dict[str, Any])`

**Input**: Configuration dictionary with structure:
```json
{
  "setup": {
    "census_parquet_path": "/path/to/census.parquet"
  },
  "simulation": {
    "start_year": 2025,
    "end_year": 2027
  }
}
```

**Valid Inputs**:
- Path is non-empty string
- Path points to existing file
- Path is absolute (per Assumption 1 in research.md)

**Invalid Inputs**:
- `census_parquet_path` missing
- `census_parquet_path` is empty string
- `census_parquet_path` is whitespace-only
- `census_parquet_path` points to non-existent file

### Output Contract

**Success Case**: Method returns None (no exception)

**Failure Case**: Raises `ConfigurationError` with message and context:
```python
from planalign_orchestrator.exceptions import ConfigurationError, ExecutionContext

raise ConfigurationError(
    message="census_parquet_path is required but was not found in the scenario config...",
    context=ExecutionContext(
        scenario_id="my-scenario",
        metadata={"missing_field": "setup.census_parquet_path"}
    )
)
```

**Exception Invariants**:
- Exception type is `ConfigurationError` (not ValueError, not generic Exception)
- Exception has `context` with `scenario_id` and `correlation_id`
- Exception message matches FR-002 or FR-004 exactly
- Exception severity is ERROR (user must intervene)

---

## Related Endpoints (No Changes)

These endpoints are not affected by this feature:

- `GET /api/workspaces/{workspace_id}/simulations/{scenario_id}/runs` — Still works
- `GET /api/workspaces/{workspace_id}/simulations/{scenario_id}/runs/{run_id}` — Still works
- `DELETE /api/workspaces/{workspace_id}/simulations/{scenario_id}/runs/{run_id}` — Still works
- File upload endpoints — No changes

---

## Monitoring & Alerting

### Metrics to Track

- Count of simulations failing due to missing census path
- Count of simulations failing due to file not found
- Time to resolution (from error to successful retry)

### Alert Thresholds

- If >10% of simulation attempts fail due to census path errors → Alert team
- If census file is consistently deleted post-upload → Investigate storage layer

### Dashboards

Update monitoring dashboard to show:
- Simulation failure rate by error type
- Correlation ID for tracing errors across systems
- Resolution time (from error to success)
