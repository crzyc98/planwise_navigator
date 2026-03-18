# Contract: Termination Rate Suggestion API

**Feature**: Fix termination rate suggestion bug
**API Base**: `/api/scenarios/{scenario_id}`
**Date**: 2026-03-18

## Endpoint: GET Termination Rate Suggestion

### Request

```http
GET /api/scenarios/{scenario_id}/termination-rate-suggestion

Query Parameters:
  - year: int (required) - Calendar year for rate calculation (e.g., 2025)
  - plan_design_id: str (optional) - Filter to specific benefit plan; if omitted, use scenario default
```

**Example Request**:
```bash
curl "http://localhost:8000/api/scenarios/baseline_2025/termination-rate-suggestion?year=2025&plan_design_id=standard_401k"
```

---

### Success Response: 200 OK

```json
{
  "suggested_rate": 12.5,
  "confidence": "HIGH",
  "sample_size": 200,
  "snapshot_date": "2025-12-31",
  "suggested_at": "2026-03-18T15:30:45.123Z",
  "error_message": null
}
```

**Fields**:
- `suggested_rate` (number, range: 0.0 - 99.9)
  - Percentage of active employees who terminated in the year
  - Null only if error_message is present
  - Format: Decimal with up to 2 decimal places (e.g., 12.50)

- `confidence` (enum: "HIGH" | "MEDIUM" | "LOW")
  - HIGH: > 100 active employees in snapshot
  - MEDIUM: 10-100 active employees
  - LOW: < 10 active employees

- `sample_size` (integer, >= 0)
  - Total active employees used in calculation
  - Provides transparency: "Based on {sample_size} employees"

- `snapshot_date` (ISO 8601 date)
  - Census snapshot date used for calculation
  - Format: YYYY-MM-DD

- `suggested_at` (ISO 8601 timestamp)
  - Timestamp when suggestion was generated
  - Format: RFC 3339 (e.g., 2026-03-18T15:30:45.123Z)

- `error_message` (string | null)
  - Only present if calculation failed
  - User-friendly message (not technical details)
  - Always null on success (200)

---

### Error Response: 400 Bad Request

```json
{
  "suggested_rate": null,
  "confidence": null,
  "sample_size": 0,
  "snapshot_date": null,
  "suggested_at": "2026-03-18T15:30:46.789Z",
  "error_message": "Census data not found for scenario 'unknown_scenario' in year 2025"
}
```

**Status**: 400
**Trigger**: Invalid scenario_id, missing census data, or invalid year parameter
**error_message examples**:
- "Scenario not found: baseline_2025"
- "Census data not available for year 2025"
- "Invalid year parameter: year must be a positive integer"

---

### Error Response: 503 Service Unavailable

```json
{
  "suggested_rate": null,
  "confidence": null,
  "sample_size": 0,
  "snapshot_date": null,
  "suggested_at": "2026-03-18T15:30:47.456Z",
  "error_message": "Unable to calculate termination rate: insufficient active employees (0 found). Cannot compute rate with empty dataset."
}
```

**Status**: 503 (or 400 depending on root cause)
**Trigger**: Census has zero active employees, calculation cannot proceed
**error_message examples**:
- "Unable to calculate termination rate: no active employees found"
- "Insufficient data: census has no employee records for year 2025"

---

## Response Contract Rules

**Success (200)**:
1. HTTP 200 status code
2. `suggested_rate` is a number (never 100.0, never hardcoded)
3. `suggested_rate` range: 0.0 ≤ rate < 100.0
4. `error_message` is always null on 200
5. `sample_size` > 0 (at least one active employee used)
6. `confidence` is one of the defined enum values

**Error (4xx/5xx)**:
1. HTTP status 400 or 503 (never 200)
2. `suggested_rate` is null
3. `error_message` is a user-friendly string (not null)
4. Never return 100.0 as a fallback or default
5. `sample_size` reflects actual employees (not a placeholder)

---

## Calculation Logic

**Formula**:
```
suggested_rate = (count_terminated_employees / count_active_employees) * 100
```

**Definitions**:
- `count_active_employees`: Employees with status='ACTIVE' in census snapshot
- `count_terminated_employees`: Employees with status='TERMINATED' AND termination_date in calendar year

**Validation**:
- If `count_active_employees` = 0, return error (503) with message
- If `count_terminated_employees` > `count_active_employees`, return rate > 50% (valid, indicates high turnover)

---

## Implementation Notes

**Do**:
- ✅ Calculate rate from actual census data (never hardcode 100%)
- ✅ Use correct denominator (active employees at snapshot, not just counts)
- ✅ Return informative error messages (not 100% defaults)
- ✅ Include sample_size for transparency
- ✅ Set confidence based on employee count
- ✅ Validate denominators before calculation

**Don't**:
- ❌ Return 100.0 as a suggestion (indicates bug)
- ❌ Use same rate for all scenarios
- ❌ Hardcode fallback values
- ❌ Return generic HTTP 500 errors without context
- ❌ Perform division-by-zero without catching (will crash)

---

## Testing

**Test Cases**:

| Scenario | Active | Terminated | Expected Rate | Status |
|----------|--------|-----------|---------------|--------|
| Baseline | 100 | 5 | 5.0% | 200 ✅ |
| No turnover | 100 | 0 | 0.0% | 200 ✅ |
| Small pop | 5 | 1 | 20.0% | 200 ✅ |
| Zero active | 0 | 0 | error msg | 503 ✅ |
| High turnover | 100 | 50 | 50.0% | 200 ✅ |

**Coverage**:
- Happy path: Various termination rates
- Edge cases: Zero active, single employee, no data
- Error cases: Missing census, invalid scenario
- Never 100% suggestion for valid data

---

## Versioning

- **Version**: 1.0.0
- **Breaking Changes**: None (first version)
- **Deprecated Fields**: None
- **Sunset Plan**: N/A
