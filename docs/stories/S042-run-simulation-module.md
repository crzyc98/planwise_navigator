# Story S042: Create run_simulation Module

**Story ID**: S042
**Priority**: High
**Status**: Planning
**Epic**: Workforce Simulation Foundation
**Estimated Effort**: 8 points

## Problem Statement

We need a clean, reliable `run_simulation` module that orchestrates the dbt models in the correct order to produce multi-year workforce simulations. Currently, we have staging setup working, but no systematic way to run the full simulation pipeline.

## Analysis Summary

### Current dbt Architecture (78 models total):
- **Staging**: 14 models (seeds + census data) ✅ Working via `run_staging.py`
- **Intermediate**: 40+ models (hazards, events, workforce calculations)
- **Marts**: 11 models (fact tables, dashboards)

### Critical Dependencies Found:
1. **Parameter Resolution** must happen first (`int_effective_parameters`)
2. **Event Generation** has strict ordering requirements
3. **Multi-year** requires previous year's workforce state
4. **Validation** needs all events applied to workforce state

## Proposed Processing Order

### Phase 1: Foundation Setup
**Models to run:**
1. `int_effective_parameters` - Resolve scenario parameters
2. `int_baseline_workforce` - Starting workforce (year 1 only)
3. `int_workforce_previous_year_v2` - Previous year workforce (year 2+)

**Expected Output:** Clean workforce baseline with resolved parameters

### Phase 2: Hazard Calculations
**Models to run:**
1. `int_hazard_termination` - Turnover risk calculations
2. `int_hazard_promotion` - Advancement probabilities
3. `int_hazard_merit` - Raise eligibility calculations

**Expected Output:** Risk probabilities for each employee

### Phase 3: Event Generation (ORDER CRITICAL!)
**Models to run in sequence:**
1. `int_termination_events` - Who leaves (affects replacement hiring)
2. `int_hiring_events` - Replacement + growth hires
3. `int_promotion_events` - Career advancement
4. `int_merit_events` - Salary increases

**Expected Output:** Individual event records for each employee action

### Phase 4: Event Consolidation
**Models to run:**
1. `fct_yearly_events` - Unified event stream (all event types)
2. `fct_workforce_snapshot` - Apply events to workforce state

**Expected Output:**
- Complete event log for the simulation year
- Current workforce state after applying all events

### Phase 5: Validation & Quality Checks
**Models to run:**
1. `dq_employee_id_validation` - Data integrity checks
2. Custom validation for:
   - Growth rate achievement (3% target)
   - Status code distribution (4 expected types)
   - Event count reasonableness

**Expected Output:** Validation report, error flags if issues found

## Implementation Tasks

### Task 1: Create Basic Single-Year Function
- `run_simulation_year(year: int)` function
- Run phases 1-5 in order for single year
- Basic error handling and logging
- Return success/failure status

### Task 2: Add Multi-Year Orchestration
- `run_simulation(start_year: int, end_year: int)` function
- Loop through years, using previous year's output
- Handle year-to-year state transitions
- Progress reporting

### Task 3: Parameter Integration
- Accept scenario_id parameter
- Pass variables to dbt runs correctly
- Support custom growth rates, termination rates
- Validate parameter combinations

### Task 4: Validation Framework
- Implement growth rate validation
- Check for all 4 workforce status codes
- Validate event counts are reasonable
- Generate validation report

### Task 5: Error Recovery & Resume
- Detect partial runs
- Resume from specific year if needed
- Clear incomplete state
- Robust error messages

## Expected Interface

```python
from orchestrator_dbt import run_simulation

# Simple single year
result = run_simulation(year=2025)

# Multi-year range
result = run_simulation(start_year=2025, end_year=2029)

# With custom parameters
result = run_simulation(
    start_year=2025,
    end_year=2027,
    scenario_id="high_growth",
    growth_rate=0.05
)

# Result object contains:
# - success: bool
# - years_completed: List[int]
# - validation_results: Dict
# - execution_time: float
# - error_messages: List[str]
```

## Expected Output Tables

After successful simulation run:

### Core Tables:
- **`fct_yearly_events`**: ~200-500 events per year (hires, terms, promotions, raises)
- **`fct_workforce_snapshot`**: Current workforce state by year
- **All intermediate tables**: Available for debugging/analysis

### Validation Metrics:
- **Growth Rate**: Actual vs target (3% annually)
- **Status Distribution**:
  - `continuous_active`: Existing employees still active
  - `new_hire_active`: New hires who stayed
  - `experienced_termination`: Existing employees who left
  - `new_hire_termination`: New hires who left
- **Event Counts**: Reasonable numbers based on workforce size

## Acceptance Criteria

### Must Have:
1. ✅ Single year simulation completes successfully
2. ✅ Multi-year simulation (2025-2029) produces all expected tables
3. ✅ Growth rate validation passes (within ±0.5% of target)
4. ✅ All 4 workforce status codes present in results
5. ✅ Can resume from specific year if interrupted

### Should Have:
1. ✅ Custom parameter support (scenario_id, growth_rate)
2. ✅ Detailed validation reporting
3. ✅ Progress logging during execution
4. ✅ Clear error messages for failures

### Nice to Have:
1. Performance metrics and timing
2. Dry-run mode to validate parameters
3. Comparison with previous simulation runs

## Technical Notes

### dbt Variable Passing:
```bash
dbt run --select model_name --vars "simulation_year: 2025, scenario_id: default"
```

### Multi-Year State Management:
- Year N depends on Year N-1 workforce state
- Must run years sequentially, not in parallel
- Previous year workforce filtered to active employees only

### Error Scenarios to Handle:
1. Missing staging data (run staging first)
2. Invalid parameter combinations
3. dbt model failures
4. Database lock issues
5. Incomplete previous year state

### Performance Considerations:
- Each year processes ~5,000 employees
- Expected runtime: 2-5 minutes per year
- Memory usage: <2GB for 5-year simulation
- Database size: ~50MB per simulation year

## Dependencies

### Prerequisites:
- ✅ Staging tables populated (`orchestrator_dbt/run_staging.py`)
- ✅ Configuration seeds loaded
- ✅ DuckDB database accessible

### Technical Dependencies:
- dbt 1.9.8+ with DuckDB adapter
- All intermediate models working
- Parameter resolution macros
- Hazard calculation logic

## Success Metrics

### Quantitative:
- 5-year simulation completes in <15 minutes
- Growth rate within ±0.5% of 3% target
- All 4 workforce status codes represented
- Zero data quality failures

### Qualitative:
- Clear, actionable error messages
- Easy to use interface
- Reliable, repeatable results
- Good logging and progress visibility

---

**Implementation Approach**: Start with Task 1 (single year), validate it works perfectly, then build up to multi-year orchestration. Focus on getting the basic pipeline solid before adding advanced features.
