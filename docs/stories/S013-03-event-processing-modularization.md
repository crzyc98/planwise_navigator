# Story S013-03: Event Processing Modularization

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: High
**Estimate**: 5 story points
**Status**: Not Started

## User Story

**As a** PlanWise Navigator developer
**I want** event processing logic extracted into dedicated operations
**So that** complex event model execution and debugging is isolated and reusable

## Background

The current pipeline has significant duplication in event processing:
- Lines 295-386 in `run_year_simulation`
- Lines 932-1026 in `run_multi_year_simulation`

Both contain identical logic for:
- Event model sequence execution (termination → promotion → merit → hiring → new_hire_termination)
- Detailed hiring calculation debug logging (🔍 HIRING CALCULATION DEBUG)
- Formula calculations and logging for hiring decisions

This duplication makes maintenance difficult and violates DRY principles.

## Acceptance Criteria

### Functional Requirements
1. **Event Models Operation**
   - [ ] Create `run_dbt_event_models_for_year` operation
   - [ ] Execute event models in correct Epic 11.5 sequence
   - [ ] Include comprehensive hiring calculation debug logging
   - [ ] Use the new `execute_dbt_command` utility (from S013-01)
   - [ ] Handle all configuration parameters (year, random_seed, growth rates)

2. **Hiring Debug Logic Preservation**
   - [ ] Maintain exact "🔍 HIRING CALCULATION DEBUG:" logging format
   - [ ] Include all formula calculations and intermediate values
   - [ ] Preserve mathematical precision and rounding behavior
   - [ ] Log all 8 debug metrics (workforce, rates, calculations, formula)

3. **Event Sequence Integrity**
   - [ ] Execute models in exact order: int_termination_events → int_promotion_events → int_merit_events → int_hiring_events → int_new_hire_termination_events
   - [ ] Pass all required variables to each model
   - [ ] Handle errors consistently with current implementation
   - [ ] Maintain exact variable formatting for dbt --vars

### Technical Requirements
1. **Operation Signatures**
```python
@op(required_resource_keys={"dbt"})
def run_dbt_event_models_for_year(
    context: OpExecutionContext,
    year: int,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute event models for a single simulation year with debug logging."""

@op(required_resource_keys={"dbt"})
def run_dbt_snapshot_for_year(
    context: OpExecutionContext,
    year: int
) -> None:
    """Execute dbt snapshot for year-end workforce state."""
```

2. **Configuration Handling**
   - [ ] Accept full config dictionary with all simulation parameters
   - [ ] Extract required values: random_seed, target_growth_rate, termination rates
   - [ ] Build proper dbt variables dictionary for each model
   - [ ] Handle full_refresh flag appropriately

3. **Debug Calculation Logic**
   - [ ] Calculate workforce count (baseline vs previous year logic)
   - [ ] Apply exact formula from int_hiring_events.sql
   - [ ] Use proper rounding: `math.ceil()` for terminations and hires, `round()` for new hire terminations
   - [ ] Log all intermediate calculations with identical format

## Implementation Details

### Current Duplicated Code Pattern
**Lines 946-1014 (run_multi_year_simulation) duplicate lines 310-376 (run_year_simulation)**:

```python
# Add detailed logging for hiring calculation before running int_hiring_events
if model == "int_hiring_events":
    context.log.info("🔍 HIRING CALCULATION DEBUG:")
    conn = duckdb.connect(str(DB_PATH))
    try:
        # Calculate workforce count
        if year == start_year:  # Different logic in each function!
            workforce_count = conn.execute(
                "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
            ).fetchone()[0]
        else:
            workforce_count = conn.execute(
                "SELECT COUNT(*) FROM int_workforce_previous_year WHERE employment_status = 'active'"
            ).fetchone()[0]

        # ... identical formula calculations ...
        # ... identical logging statements ...
```

### New Modular Implementation
```python
@op(required_resource_keys={"dbt"})
def run_dbt_event_models_for_year(
    context: OpExecutionContext,
    year: int,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute event models for a single simulation year with debug logging."""

    event_models = [
        "int_termination_events",
        "int_promotion_events",
        "int_merit_events",
        "int_hiring_events",
        "int_new_hire_termination_events"
    ]

    results = {}

    for model in event_models:
        vars_dict = {
            "simulation_year": year,
            "random_seed": config["random_seed"],
            "target_growth_rate": config["target_growth_rate"],
            "new_hire_termination_rate": config["new_hire_termination_rate"],
            "total_termination_rate": config["total_termination_rate"]
        }

        # Special handling for hiring events debug logging
        if model == "int_hiring_events":
            debug_info = _log_hiring_calculation_debug(context, year, config)
            results["hiring_debug"] = debug_info

        execute_dbt_command(
            context,
            ["run", "--select", model],
            vars_dict,
            config.get("full_refresh", False),
            f"{model} for year {year}"
        )

        results[model] = {"status": "completed", "year": year}

    return results

def _log_hiring_calculation_debug(
    context: OpExecutionContext,
    year: int,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Log detailed hiring calculation debug information."""
    context.log.info("🔍 HIRING CALCULATION DEBUG:")

    conn = duckdb.connect(str(DB_PATH))
    try:
        # Unified workforce count logic
        if year == 2025:  # Use baseline for first year
            workforce_count = conn.execute(
                "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
            ).fetchone()[0]
        else:
            workforce_count = conn.execute(
                "SELECT COUNT(*) FROM int_workforce_previous_year WHERE employment_status = 'active'"
            ).fetchone()[0]

        # Extract formula inputs
        target_growth_rate = config["target_growth_rate"]
        total_termination_rate = config["total_termination_rate"]
        new_hire_termination_rate = config["new_hire_termination_rate"]

        # Apply exact formula from int_hiring_events.sql
        import math
        experienced_terms = math.ceil(workforce_count * total_termination_rate)
        growth_amount = workforce_count * target_growth_rate
        total_hires_needed = math.ceil(
            (experienced_terms + growth_amount) / (1 - new_hire_termination_rate)
        )
        expected_new_hire_terms = round(total_hires_needed * new_hire_termination_rate)

        # Log all debug information (maintain exact format)
        context.log.info(f"  📊 Starting workforce: {workforce_count} active employees")
        context.log.info(f"  📊 Target growth rate: {target_growth_rate:.1%}")
        context.log.info(f"  📊 Total termination rate: {total_termination_rate:.1%}")
        context.log.info(f"  📊 New hire termination rate: {new_hire_termination_rate:.1%}")
        context.log.info(f"  📊 Expected experienced terminations: {experienced_terms}")
        context.log.info(f"  📊 Growth amount needed: {growth_amount:.1f}")
        context.log.info(f"  🎯 TOTAL HIRES CALLING FOR: {total_hires_needed}")
        context.log.info(f"  📊 Expected new hire terminations: {expected_new_hire_terms}")
        context.log.info(f"  📊 Net hiring impact: {total_hires_needed - expected_new_hire_terms}")
        context.log.info(f"  📊 Formula: CEIL(({experienced_terms} + {growth_amount:.1f}) / (1 - {new_hire_termination_rate})) = {total_hires_needed}")

        return {
            "workforce_count": workforce_count,
            "experienced_terms": experienced_terms,
            "growth_amount": growth_amount,
            "total_hires_needed": total_hires_needed,
            "expected_new_hire_terms": expected_new_hire_terms
        }

    except Exception as e:
        context.log.warning(f"Error calculating hiring debug info: {e}")
        return {"error": str(e)}
    finally:
        conn.close()

@op(required_resource_keys={"dbt"})
def run_dbt_snapshot_for_year(context: OpExecutionContext, year: int) -> None:
    """Execute dbt snapshot for year-end workforce state."""
    execute_dbt_command(
        context,
        ["snapshot", "--select", "scd_workforce_state"],
        {"simulation_year": year},
        False,  # Snapshots typically don't use full_refresh
        f"workforce state snapshot for year {year}"
    )
```

## Testing Requirements

### Unit Tests
1. **Event Model Sequence**
   - [ ] Test all 5 event models execute in correct order
   - [ ] Test variable passing to each model
   - [ ] Test error handling for individual model failures
   - [ ] Test full_refresh flag handling

2. **Debug Calculation Logic**
   - [ ] Test hiring calculation with known inputs/outputs
   - [ ] Test baseline vs previous year workforce logic
   - [ ] Test mathematical precision and rounding
   - [ ] Test debug logging format and content

3. **Integration Points**
   - [ ] Test operation integration with run_year_simulation
   - [ ] Test operation integration with run_multi_year_simulation
   - [ ] Test configuration parameter handling

### Behavior Validation
1. **Logging Comparison**
   - [ ] Compare debug output before/after refactoring
   - [ ] Verify all 10 debug log lines are identical
   - [ ] Confirm emoji and formatting preservation
   - [ ] Validate mathematical calculation accuracy

2. **Simulation Results**
   - [ ] Run same simulation before/after refactoring
   - [ ] Compare event counts and workforce metrics
   - [ ] Verify hiring calculations produce identical results
   - [ ] Validate year-over-year progression

## Definition of Done

- [ ] `run_dbt_event_models_for_year` operation implemented and tested
- [ ] `run_dbt_snapshot_for_year` operation implemented and tested
- [ ] Hiring debug calculation logic extracted and verified
- [ ] Duplicated code removed from both single/multi-year operations
- [ ] Unit tests written and passing (>95% coverage)
- [ ] Integration tests confirm identical behavior
- [ ] Debug logging output validated character-for-character
- [ ] Code review completed and approved

## Dependencies

- **Upstream**: S013-01 (dbt Command Utility) - required for execute_dbt_command
- **Downstream**: S013-05 (Single-Year Refactoring), S013-06 (Multi-Year Transformation)

## Risk Mitigation

1. **Calculation Accuracy**:
   - Comprehensive testing with known inputs/outputs
   - Comparison testing before/after refactoring
   - Mathematical validation of rounding and precision

2. **Logging Compatibility**:
   - Character-by-character comparison of debug output
   - Validation that monitoring/alerting continues to work
   - Preservation of exact emoji and formatting

3. **Event Sequence Integrity**:
   - Explicit testing of Epic 11.5 sequence requirements
   - Validation that model dependencies are maintained
   - Error handling consistency with current implementation

---

**Implementation Notes**: This is the most complex story due to the critical hiring calculation logic. Extensive testing and validation required to ensure mathematical accuracy and logging preservation.
