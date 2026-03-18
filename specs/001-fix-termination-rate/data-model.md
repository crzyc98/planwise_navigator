# Phase 1: Data Model Design

**Feature**: Fix termination rate suggestion bug
**Date**: 2026-03-18
**Status**: Design (for implementation team review)

## Entity Model

### Entity 1: Census Data

**Purpose**: Source workforce snapshot containing employee records used for rate calculation

**Schema**:
```sql
census_record {
  census_id: UUID (unique identifier)
  scenario_id: str (scenario context)
  plan_design_id: str (benefit plan)
  employee_id: str (employee identifier)
  snapshot_date: date (census snapshot date)

  -- Employment Info
  hire_date: date (employee start date)
  employment_status: enum ['ACTIVE', 'TERMINATED', 'ON_LEAVE', 'RETIRED']
  termination_date: date (optional, null if ACTIVE)
  termination_reason: str (optional, reason for separation)

  -- Demographics
  age: int (current age)
  tenure_months: decimal (months employed)
  department: str
  job_level: int

  -- Compensation
  annual_salary: decimal

  created_at: timestamp (audit)
  source_file: str (audit: which census file)
}
```

**Key Attributes**:
- `employment_status` = 'ACTIVE' → included in active employee count
- `employment_status` = 'TERMINATED' AND termination_date in period → included in termination count
- `employment_status` = 'ACTIVE' AND termination_date NOT NULL → data quality issue
- All dates use ISO 8601 format
- UUIDs for census_id enable audit traceability

**Validation Rules**:
- `hire_date` ≤ `snapshot_date`
- `termination_date` ≥ `hire_date` (if not null)
- `termination_date` ≤ `snapshot_date` (if not null)
- If `employment_status` = 'TERMINATED', then `termination_date` NOT NULL
- If `employment_status` = 'ACTIVE', then `termination_date` IS NULL

---

### Entity 2: Termination Rate Calculation

**Purpose**: Intermediate calculation state for deriving termination rate suggestion

**Schema**:
```python
# Pydantic v2 model
class TerminationRateCalculation(BaseModel):
    calculation_id: UUID
    scenario_id: str
    plan_design_id: str
    snapshot_date: date
    period_year: int (calendar year for calculation)

    # Calculation Components
    total_active_employees: int (denominator)
    # Definition: COUNT DISTINCT employee_id WHERE employment_status = 'ACTIVE'

    total_terminated_employees: int (numerator)
    # Definition: COUNT DISTINCT employee_id WHERE
    #   employment_status = 'TERMINATED'
    #   AND YEAR(termination_date) = period_year

    calculation_numerator: Decimal (termination count)
    calculation_denominator: Decimal (active employee count)

    # Result
    calculated_rate: Decimal | None (percentage, null if error)
    # Formula: (total_terminated_employees / total_active_employees) * 100

    # Error Handling
    calculation_status: enum ['SUCCESS', 'INSUFFICIENT_DATA', 'DIVISION_BY_ZERO']
    error_message: str | None
    # Examples:
    # - "Insufficient active employees (0 found). Cannot calculate rate."
    # - "No termination data available for period. Rate cannot be determined."

    calculated_at: timestamp (audit)
    model_config = ConfigDict(validate_default=True)
```

**Key Attributes**:
- `total_active_employees` must be > 0 for valid rate calculation
- `calculated_rate` is null if status = 'INSUFFICIENT_DATA' or 'DIVISION_BY_ZERO'
- Range: 0.0 ≤ `calculated_rate` ≤ 100.0 (excludes 100% for most scenarios)
- Used for audit and debugging (shows intermediate values)

**Validation Rules**:
- `total_active_employees` ≥ 0
- `total_terminated_employees` ≥ 0
- If `total_active_employees` = 0, set `calculation_status` = 'DIVISION_BY_ZERO'
- If `total_terminated_employees` > `total_active_employees`, set warning (rate > 100% is valid but unusual)
- All Decimals use 4 decimal places for precision

---

### Entity 3: Termination Rate Suggestion

**Purpose**: User-facing suggestion delivered via API endpoint

**Schema**:
```python
# Pydantic v2 model (FastAPI response)
class TerminationRateSuggestion(BaseModel):
    scenario_id: str
    plan_design_id: str
    snapshot_date: date

    # Suggestion (user-facing)
    suggested_rate: Decimal | None (0-100, null if error)
    # Range: 0.0 ≤ suggested_rate ≤ 99.9 (excludes 100% for normal cases)

    # Confidence & Details
    confidence: enum ['HIGH', 'MEDIUM', 'LOW'] (based on employee count and data quality)
    # HIGH: > 100 active employees
    # MEDIUM: 10-100 active employees
    # LOW: < 10 active employees

    sample_size: int (total active employees used in calculation)
    # For user context: "Based on {sample_size} active employees"

    # Transparency
    error_message: str | None
    # Only populated if calculation failed
    # Examples: "Unable to calculate rate: no active employees found"

    suggested_at: timestamp (when suggestion was generated)
```

**Key Attributes**:
- `suggested_rate` = null when calculation fails (not 100%)
- `confidence` indicates reliability of suggestion
- `sample_size` provides transparency to users
- Error messages are user-friendly (not technical)
- Non-200 HTTP status if error_message is populated

**Validation Rules**:
- 0.0 ≤ `suggested_rate` < 100.0 (reject 100%)
- If `suggested_rate` is null, `error_message` MUST be present
- If `error_message` is present, `suggested_rate` MUST be null
- `sample_size` ≥ 0
- `confidence` must be one of the defined enum values

---

### Entity 4: Test Census Scenario

**Purpose**: Known test data for validating fix

**Schema**:
```python
class TestCensusScenario(BaseModel):
    scenario_name: str (e.g., "10_employees_1_termination")
    total_active_employees: int
    total_terminated_employees: int (in year)
    expected_rate: Decimal (expected suggestion, e.g., 10.0)

    # Data for creating test records
    employee_records: List[EmployeeRecord]
```

**Test Scenarios**:
1. **Baseline**: 100 active, 5 terminated → expect 5.0%
2. **No Terminations**: 100 active, 0 terminated → expect 0.0%
3. **Zero Active**: 0 active, 0 terminated → expect error message
4. **One Employee**: 1 active, 0 terminated → expect 0.0%
5. **High Turnover**: 100 active, 50 terminated → expect 50.0%
6. **Small Population**: 5 active, 1 terminated → expect 20.0%

---

## State Transitions

Termination rate suggestion follows this path:

```
Census Data Input
    ↓
Load & Filter by Period
    ↓
Count Active Employees (denominator)
    ↓
Count Terminated Employees (numerator)
    ↓
Validate Denominators
    ├→ If denominator = 0: error_message + DIVISION_BY_ZERO status
    └→ If denominator > 0: Calculate rate = (numerator/denominator) * 100
    ↓
Determine Confidence Level
    ↓
Format & Return Termination Rate Suggestion
    ├→ Success: Return calculated_rate + confidence
    └→ Error: Return error_message + null rate
```

---

## Validation & Testing

**Constraints Enforced**:
- Census: All date ranges valid, status/termination_date consistency
- Calculation: Denominator > 0, result in [0, 100), error handling for edge cases
- Suggestion: Null rate iff error_message present, confidence reflects data quality

**Test Coverage**:
- Happy path: Various termination rates (0%, 5%, 50%)
- Edge cases: Zero denominator, single employee, no terminations
- Error handling: Informative messages vs. 100% defaults
- Data quality: Missing fields, invalid dates, status mismatches

**Example Test Case**:

```python
def test_termination_rate_basic(populated_db):
    """Test: 10 active employees, 2 terminated → expect 20%"""
    # Given: Census with 10 active, 2 terminated in year
    # When: Suggestion endpoint called
    # Then: Response.suggested_rate = 20.0, confidence = 'MEDIUM'

    response = client.get(
        "/api/scenarios/{id}/termination-rate-suggestion",
        params={"year": 2025}
    )
    assert response.status_code == 200
    assert response.json()['suggested_rate'] == 20.0
    assert response.json()['confidence'] == 'MEDIUM'
    assert response.json()['sample_size'] == 10
    assert response.json()['error_message'] is None
```

---

## Normalization & Relationships

**Census Data** → (many-to-one) → Scenario
- One scenario can have many census records
- Indexed by (scenario_id, snapshot_date) for efficient lookup

**Termination Rate Calculation** → (one-to-one) → Suggestion
- Calculation is internal; one suggestion returned to user
- Audit trail preserved by keeping calculation intermediate values

**No circular dependencies**: Census → Calculation → Suggestion (linear flow)
