# Developer Quickstart: Fix Termination Rate Suggestion Bug

**Feature**: 001-fix-termination-rate
**Created**: 2026-03-18
**Goal**: Fix termination rate suggestions that always return 100% regardless of input

---

## Quick Navigation

1. **What's broken**: Termination rate suggestions always show 100%
2. **What to fix**: The calculation logic in the termination rate suggestion service
3. **How to test**: Use pytest fixtures with test census data
4. **How to validate**: Compare results against expected rates

---

## Setup

### Clone & Activate Environment

```bash
cd /workspace
git checkout 001-fix-termination-rate
source .venv/bin/activate
```

### Verify Test Infrastructure

```bash
# Run fast tests to ensure environment is ready
pytest -m fast --collect-only

# Should show 87 tests in ~4.7 seconds when executed
pytest -m fast
```

### Access Implementation Files

**Primary Files to Review/Modify**:
```bash
# API endpoint (likely location)
planalign_api/routers/scenarios.py        # GET /api/scenarios/{id}/termination-rate-suggestion

# Service layer (likely location)
planalign_api/services/suggestion_service.py   # or similar

# Orchestrator (if calculation is in engine)
planalign_orchestrator/generators/termination.py  # or similar

# Test file (create or modify)
tests/test_termination_rate_suggestion.py
```

---

## Understanding the Bug

### Current Behavior

```python
# Example of what's currently happening (WRONG):
def suggest_termination_rate(scenario_id, year):
    rate = 100.0  # ← BUG: Always returns 100%
    return {"suggested_rate": rate}
```

### Expected Behavior

```python
# What it should do (CORRECT):
def suggest_termination_rate(scenario_id, year):
    # Get census data
    active_count = count_active_employees(scenario_id, year)
    terminated_count = count_terminated_employees(scenario_id, year)

    # Calculate rate
    if active_count == 0:
        return {"suggested_rate": None, "error_message": "No active employees found"}

    rate = (terminated_count / active_count) * 100
    return {
        "suggested_rate": rate,
        "confidence": get_confidence(active_count),
        "sample_size": active_count
    }
```

### Likely Root Causes

**Check these first**:
1. **Division by zero**: `total_active / total_active` → catches exception, returns 100%?
2. **Missing denominator**: Only counts terminations, no denominator → defaults to 100%?
3. **Wrong filter**: Filter returns empty active employee list → fallback to 100%?
4. **Hardcoded default**: `except: return 100.0` in the code?

---

## Step-by-Step Fix Process

### 1. Find the Bug Location

```bash
# Search for termination rate suggestion code
grep -r "termination.*rate" planalign_api/ planalign_orchestrator/
grep -r "100\.0\|100%" planalign_api/services/

# Look for suggestion endpoint
grep -r "suggestion" planalign_api/routers/
```

**What to look for**:
- Function name containing "termination" + "rate" or "suggestion"
- Variables: `termination_count`, `active_count`, `denominator`
- Try/except blocks that might have `return 100`
- Hardcoded percentages

### 2. Understand Current Data Flow

```bash
# Trace data from census to suggestion response
# 1. Identify where census data is loaded
# 2. Find where active/terminated counts are computed
# 3. Locate where the division happens (or doesn't)
```

**Check in dbt models**:
```bash
cd dbt
dbt run --select tag:CENSUS_STAGING --threads 1
dbt test --select tag:CENSUS_STAGING --threads 1
```

### 3. Write Failing Tests First (TDD)

Create `tests/test_termination_rate_suggestion.py`:

```python
import pytest
from tests.fixtures.database import populated_db
from tests.fixtures.config import minimal_config
from planalign_api.services.suggestion_service import suggest_termination_rate

def test_termination_rate_basic(populated_db, minimal_config):
    """Test: 100 active, 5 terminated → expect 5.0%"""
    # Arrange: Census with known data
    scenario_id = "test_scenario"
    year = 2025

    # Act: Get suggestion
    result = suggest_termination_rate(scenario_id, year)

    # Assert: Correct rate (not 100%)
    assert result["suggested_rate"] == 5.0, f"Expected 5.0%, got {result['suggested_rate']}%"
    assert result["error_message"] is None
    assert result["sample_size"] == 100

def test_termination_rate_no_terminations(populated_db):
    """Test: 100 active, 0 terminated → expect 0.0%"""
    result = suggest_termination_rate("test_scenario", 2025)
    assert result["suggested_rate"] == 0.0

def test_termination_rate_zero_active(populated_db):
    """Test: 0 active employees → expect error message"""
    result = suggest_termination_rate("empty_scenario", 2025)
    assert result["suggested_rate"] is None
    assert "no active employees" in result["error_message"].lower()
    assert result["sample_size"] == 0
```

**Run tests** (they should fail initially):
```bash
pytest tests/test_termination_rate_suggestion.py -v
# Expected: All tests fail with assertion errors
```

### 4. Fix the Code

**Pseudocode for fix**:
```python
def suggest_termination_rate(scenario_id, year):
    # Load census data
    census = load_census_data(scenario_id, year)

    # Calculate denominators
    active_count = count_active_employees(census)
    terminated_count = count_terminated_employees(census, year)

    # Handle edge cases
    if active_count == 0:
        return {
            "suggested_rate": None,
            "error_message": "Unable to calculate rate: no active employees found",
            "confidence": None,
            "sample_size": 0
        }

    # Calculate rate (not 100%)
    rate = Decimal(terminated_count) / Decimal(active_count) * 100

    # Determine confidence
    confidence = "HIGH" if active_count > 100 else "MEDIUM" if active_count > 10 else "LOW"

    return {
        "suggested_rate": rate,
        "confidence": confidence,
        "sample_size": active_count,
        "error_message": None
    }
```

### 5. Run Tests & Validate

```bash
# Run specific test
pytest tests/test_termination_rate_suggestion.py -v

# Run all fast tests to ensure no regressions
pytest -m fast

# Run integration tests
pytest -m integration
```

### 6. Verify Against Success Criteria

Check against requirements in `spec.md`:

- [ ] **SC-001**: Suggestions return 0-99% (not 100%)
- [ ] **SC-002**: Rates vary across different census files
- [ ] **SC-003**: Edge cases return error messages
- [ ] **SC-004**: All test files return realistic rates
- [ ] **SC-005**: Same census always produces same rate

---

## Key Files & Patterns

### Using Fixtures (E075)

```python
# Import fixtures
from tests.fixtures.database import populated_db, in_memory_db
from tests.fixtures.config import minimal_config
from tests.fixtures.workforce_data import sample_employees

def test_with_fixture(populated_db):
    """populated_db is a pre-populated DuckDB instance"""
    # Database is ready for queries
    # Fixtures handle setup/teardown automatically
```

### DuckDB Queries

```python
from planalign_orchestrator.config import get_database_path
import duckdb

def count_active_employees(scenario_id, year):
    conn = duckdb.connect(str(get_database_path()))
    result = conn.execute("""
        SELECT COUNT(DISTINCT employee_id)
        FROM census_data
        WHERE scenario_id = ? AND employment_status = 'ACTIVE'
    """, [scenario_id]).fetchall()
    conn.close()
    return result[0][0]
```

### Type-Safe Models (Pydantic v2)

```python
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional

class TerminationRateSuggestion(BaseModel):
    suggested_rate: Optional[Decimal] = Field(None, ge=0, lt=100)
    confidence: str
    sample_size: int = Field(ge=0)
    error_message: Optional[str] = None

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v)
        }
```

---

## Debugging Tips

### Check Current Logic

```bash
# Add print statements in test
def test_debug(populated_db):
    active = count_active_employees("test", 2025)
    terminated = count_terminated_employees("test", 2025)
    print(f"Active: {active}, Terminated: {terminated}")
    print(f"Rate: {(terminated / active * 100) if active > 0 else 'N/A'}")
```

### Trace Division Issue

```python
# If you suspect division-by-zero:
try:
    rate = terminated / active * 100
except ZeroDivisionError:
    print("Found it! Division by zero is not handled")
    return 100  # ← This is the bug
```

### Query Census Data Directly

```bash
# In terminal
duckdb dbt/simulation.duckdb

# Then in DuckDB CLI:
SELECT COUNT(*) as total_records FROM census_data;
SELECT employment_status, COUNT(*) as count FROM census_data GROUP BY employment_status;
SELECT * FROM census_data LIMIT 5;  # View sample records
```

---

## Common Pitfalls

1. **Forgetting to close database connections**
   ```python
   # Wrong
   conn = duckdb.connect(str(path))
   result = conn.execute(...).fetchall()
   # ← Connection never closed, locks database

   # Right
   conn = duckdb.connect(str(path))
   try:
       result = conn.execute(...).fetchall()
   finally:
       conn.close()
   ```

2. **Using wrong denominator**
   ```python
   # Wrong: Uses all employees (including terminated)
   rate = terminated / total_all * 100

   # Right: Uses only active employees
   rate = terminated / active_only * 100
   ```

3. **Hardcoding 100% as fallback**
   ```python
   # Wrong
   except:
       return {"suggested_rate": 100.0}

   # Right
   except Exception as e:
       return {"suggested_rate": None, "error_message": str(e)}
   ```

4. **Not testing edge cases**
   ```python
   # Add these tests:
   # - Zero active employees
   # - Single employee
   # - No terminations
   # - Missing data
   ```

---

## Success Checklist

- [ ] Found bug location
- [ ] Wrote failing tests
- [ ] Fixed calculation logic
- [ ] All tests pass (pytest -m fast)
- [ ] Rates vary across scenarios (not all 100%)
- [ ] Edge cases handled (informative errors)
- [ ] Integration tests pass
- [ ] Success criteria verified (spec.md SC-001 through SC-005)
- [ ] Code reviewed for type-safety (Pydantic models)
- [ ] Database connections properly managed

---

## Next Steps After Fix

1. **Code review**: Have someone review the fix
2. **Create PR**: Push to GitHub branch `001-fix-termination-rate`
3. **Run CI tests**: Ensure all tests pass in CI pipeline
4. **Merge & deploy**: Follow standard release process

---

## References

- **Spec**: `specs/001-fix-termination-rate/spec.md`
- **API Contract**: `specs/001-fix-termination-rate/contracts/termination-rate-api.md`
- **Data Model**: `specs/001-fix-termination-rate/data-model.md`
- **Testing Guide**: `tests/TEST_INFRASTRUCTURE.md`
- **CLAUDE.md**: Code generation playbook (database patterns, dbt development)
