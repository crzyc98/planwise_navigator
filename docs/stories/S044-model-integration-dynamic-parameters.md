# S044: Model Integration with Dynamic Parameters

**Epic:** E012 - Analyst-Driven Compensation Tuning System
**Story Points:** 8 (Large)
**Status:** Planned
**Assignee:** TBD
**Start Date:** TBD
**Target Date:** TBD

## Business Value

Compensation calculations automatically use analyst-configured parameters, enabling real-time scenario modeling without code deployment.

**User Story:**
As an analyst, I want compensation calculations to automatically use my configured parameters so that I can see immediate impact of parameter changes on workforce costs and growth metrics.

## Technical Approach

Modify 4 core compensation models to read from `comp_levers` instead of hardcoded rates. Maintain event sourcing integrity in `fct_yearly_events` by adding parameter tracking fields. Extend existing event types while preserving unique constraints and data quality validations.

## Implementation Details

### Existing Models/Tables to Modify

**Core Compensation Models:**
- `int_merit_events.sql` → Replace hardcoded merit rates with parameter lookup
- `int_hazard_merit.sql` → Dynamic merit calculation based on scenario
- `fct_compensation_growth.sql` → Scenario-aware growth calculations
- `fct_yearly_events.sql` → Add parameter tracking fields

**Supporting Models:**
- `dim_hazard_table.sql` → Integrate with parameter resolution system
- `int_hazard_termination.sql` → Prepare for future parameter integration
- `int_hazard_promotion.sql` → Prepare for future parameter integration

### New Schema Elements

**Enhanced Event Tracking:**
```sql
-- Extend fct_yearly_events
ALTER TABLE fct_yearly_events ADD COLUMN parameter_scenario_id VARCHAR(50);
ALTER TABLE fct_yearly_events ADD COLUMN parameter_source VARCHAR(20); -- 'hardcoded', 'scenario', 'override'
ALTER TABLE fct_yearly_events ADD COLUMN parameter_values JSON; -- Snapshot of parameters used
```

**New Intermediate Models:**
```sql
-- int_effective_parameters.sql
-- Resolves final parameters per employee/event combination
CREATE TABLE int_effective_parameters AS (
  SELECT
    scenario_id,
    fiscal_year,
    employee_id,
    job_level,
    event_type,
    parameter_name,
    parameter_value,
    parameter_source,
    effective_date
  FROM parameter_resolution_logic
);
```

### dbt Integration Points

**Macros to Extend:**
- `resolve_parameter(scenario_id, job_level, event_type, param_name)` - Main parameter resolution
- `get_merit_rate(employee_id, scenario_id)` - Employee-specific merit rate lookup
- `validate_parameter_usage(model_name, parameters_used)` - Parameter usage audit

**Models to Create:**
- `int_effective_parameters.sql` - Parameter resolution per employee
- `int_parameter_audit.sql` - Parameter usage tracking
- `fct_parameter_lineage.sql` - Parameter change impact analysis

**Model Modifications:**

**int_merit_events.sql Changes:**
```sql
-- BEFORE (hardcoded)
{% set merit_base = 0.04 %}
{% set cola_rate = 0.025 %}

-- AFTER (parameter-driven)
{% set scenario_id = var('scenario_id', 'default') %}

WITH merit_parameters AS (
  SELECT * FROM {{ ref('int_effective_parameters') }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND event_type = 'RAISE'
    AND parameter_name IN ('merit_base', 'cola_rate')
),

merit_events AS (
  SELECT
    e.employee_id,
    e.fiscal_year,
    p_merit.parameter_value AS merit_rate,
    p_cola.parameter_value AS cola_rate,
    '{{ scenario_id }}' AS parameter_scenario_id,
    'scenario' AS parameter_source
  FROM employees e
  LEFT JOIN merit_parameters p_merit
    ON p_merit.parameter_name = 'merit_base'
  LEFT JOIN merit_parameters p_cola
    ON p_cola.parameter_name = 'cola_rate'
)
```

### Data Flow Changes

```
Enhanced Flow:
Scenario Selection → Parameter Resolution → Dynamic Model Execution → Event Generation

Specific Flow:
var('scenario_id') → int_effective_parameters → int_merit_events → fct_yearly_events
                                           → int_hazard_merit → fct_compensation_growth
```

### Event Sourcing Enhancement

**Parameter Tracking in Events:**
- Every event records which parameters were used
- Parameter values snapshot preserved for audit
- Scenario traceability maintained throughout pipeline

**Event Types Maintained:**
- `HIRE` - New employee events
- `TERMINATION` - Employee departure events
- `PROMOTION` - Job level advancement events
- `RAISE` - Merit and COLA increase events (enhanced with parameter tracking)

## Acceptance Criteria

### Functional Requirements
- [ ] All merit events use scenario-specific parameters from `comp_levers`
- [ ] Parameter resolution works for all 5 job levels (Staff → VP)
- [ ] Default scenario produces identical results to current hardcoded system
- [ ] Event sourcing maintains immutable audit trail with parameter tracking
- [ ] Multiple scenarios can be processed independently

### Technical Requirements
- [ ] Performance maintained for 10,000+ employee simulations
- [ ] Existing event types (`RAISE`, etc.) preserve structure and downstream compatibility
- [ ] Data quality tests pass with dynamic parameter ranges
- [ ] Incremental model performance unaffected (<5% execution time increase)

### Data Quality Requirements
- [ ] Parameter range validation enforced (e.g., merit rates 0-50%)
- [ ] Parameter source tracking for full lineage
- [ ] Event sequencing and conflict resolution maintained
- [ ] Backward compatibility validation passes

## Dependencies

**Prerequisite Stories:**
- S043 (Parameter Tables Foundation) - Requires `comp_levers` and parameter resolution system

**Dependent Stories:**
- S045 (Dagster Enhancement) - Requires parameter-driven models
- S046 (Analyst Interface) - Requires dynamic calculation system

**External Dependencies:**
- Existing event sourcing architecture
- Current dbt model performance baselines
- Established data quality validation framework

## Testing Strategy

### Unit Tests (dbt tests)
```yaml
# Parameter-driven calculation validation
- name: test_merit_calculation_accuracy
  description: "Verify merit calculations use correct parameter values"

# Event sourcing integrity
- name: test_parameter_tracking_completeness
  description: "Ensure all events track parameter usage"

# Performance regression
- name: test_model_execution_performance
  description: "Verify <5% performance impact"
```

### Integration Tests
- Cross-scenario result isolation and accuracy
- Parameter change impact propagation
- Event sourcing audit trail completeness
- Downstream model compatibility

### Regression Tests
- Default scenario matches current hardcoded results exactly
- Existing Dagster pipeline continues to function
- Streamlit dashboard data remains consistent

## Implementation Steps

1. **Create parameter resolution logic** in `int_effective_parameters.sql`
2. **Update merit event model** to use dynamic parameters
3. **Extend event tracking** with parameter metadata
4. **Modify hazard models** for parameter integration
5. **Update growth analysis models** for scenario awareness
6. **Add comprehensive testing** for parameter-driven calculations
7. **Performance optimization** and validation
8. **Documentation updates** with parameter usage examples

## Performance Considerations

**Optimization Strategies:**
- **Materialized Tables:** Cache parameter resolution results
- **Incremental Processing:** Only recalculate when parameters change
- **Index Optimization:** Index on scenario_id, job_level, parameter_name
- **Memory Management:** Limit parameter table size in memory

**Performance Targets:**
- Model execution time increase <5%
- Parameter lookup time <10ms per employee
- Memory usage increase <15% for parameter tables

## Rollback Plan

**Immediate Rollback:**
```sql
-- Feature flag in dbt_project.yml
vars:
  use_dynamic_parameters: false  # Reverts to hardcoded values
```

**Gradual Rollback:**
- Model-by-model reversion to hardcoded parameters
- Preserve event tracking for audit purposes
- Maintain parameter tables for future re-enablement

## Success Metrics

**Functional Success:**
- 100% accuracy for parameter-driven calculations
- Zero data quality regressions
- Complete parameter audit trail in all events

**Performance Success:**
- <5% increase in model execution time
- <10ms parameter lookup latency
- <15% memory usage increase

**Quality Success:**
- All existing dbt tests continue to pass
- New parameter validation tests achieve 100% coverage
- Event sourcing integrity maintained

---

**Story Dependencies:** S043 (Parameter Tables Foundation)
**Blocked By:** S043
**Blocking:** S045, S046, S047
**Related Stories:** All stories in E012 epic
