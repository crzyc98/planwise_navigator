# S043: Parameter Tables Foundation

**Epic:** E012 - Analyst-Driven Compensation Tuning System
**Story Points:** 5 (Medium)
**Status:** Planned
**Assignee:** TBD
**Start Date:** TBD
**Target Date:** TBD

## Business Value

Analysts can adjust compensation parameters without code changes, replacing hardcoded values in CSV seeds with dynamic, scenario-aware parameter tables.

**User Story:**
As an analyst, I want to adjust compensation parameters for different scenarios so that I can model various budget outcomes without requiring developer assistance.

## Technical Approach

Extend existing 11 CSV seeds structure in `dbt/seeds/` to create new parameter tables that integrate with existing 5-level job structure. Leverage current variable system (`simulation_year`, `target_growth_rate`, etc.) and build on existing macro system for parameter resolution.

## Implementation Details

### Existing Models/Tables to Modify

**Seeds to Extend:**
- `config_raises_hazard.csv` → Replace with dynamic `comp_levers` table
- `config_cola_by_year.csv` → Extend with scenario support
- `config_job_levels.csv` → Add parameter override capabilities

**Models to Update:**
- `dim_hazard_table.sql` → Update to read from new parameter sources
- `int_merit_events.sql` → Prepare for parameter lookup integration

### New Schema Elements

**New Seeds:**
```csv
# dbt/seeds/comp_levers.csv
scenario_id,fiscal_year,job_level,event_type,parameter_name,parameter_value,is_locked,created_at,created_by

# dbt/seeds/comp_targets.csv
scenario_id,fiscal_year,metric_name,target_value,tolerance_pct,priority,description

# dbt/seeds/scenario_meta.csv
scenario_id,scenario_name,description,created_by,status,base_scenario_id,created_at,updated_at
```

**Schema Definitions:**
```yaml
# dbt/models/staging/schema.yml
models:
  - name: stg_comp_levers
    description: "Staging model for compensation parameter levers"
    columns:
      - name: scenario_id
        tests:
          - not_null
          - length:
              min: 1
              max: 50
      - name: parameter_value
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
              inclusive: true
```

### dbt Integration Points

**Macros to Create:**
- `resolve_parameter.sql` - Main parameter resolution logic
- `get_scenario_parameters.sql` - Scenario-specific parameter lookup
- `validate_parameter_ranges.sql` - Parameter validation logic

**Models to Create:**
- `stg_comp_levers.sql` - Staging model for parameter processing
- `stg_comp_targets.sql` - Staging model for target processing
- `int_effective_parameters.sql` - Resolved parameters per scenario

**Variables to Add:**
```yaml
# dbt_project.yml
vars:
  scenario_id: "default"
  parameter_validation_enabled: true
```

### Data Flow Changes

```
New Flow:
Raw Seeds → Staging Models → Parameter Resolution → Intermediate Models

Specific Models:
seeds/comp_levers.csv → stg_comp_levers → int_effective_parameters
seeds/comp_targets.csv → stg_comp_targets → int_target_tracking
seeds/scenario_meta.csv → stg_scenario_meta → dim_scenario_registry
```

## Acceptance Criteria

### Functional Requirements
- [ ] `comp_levers` table supports all 5 job levels (Staff=1 → VP=5)
- [ ] Parameter resolution respects existing merit ranges (3.5% → 5.5%)
- [ ] Scenario isolation prevents cross-contamination of parameters
- [ ] Backward compatibility maintained with existing hardcoded parameters
- [ ] Default scenario created that matches current hardcoded values

### Technical Requirements
- [ ] dbt test coverage for parameter validation (ranges, constraints)
- [ ] Integration with existing `var('simulation_year')` system
- [ ] Performance impact <5% on existing model execution time
- [ ] Schema documentation includes parameter descriptions and valid ranges

### Data Quality Requirements
- [ ] Parameter values validated within reasonable ranges
- [ ] Scenario metadata includes audit trail (created_by, created_at)
- [ ] Foreign key relationships enforced between parameter tables
- [ ] Duplicate parameter detection and prevention

## Dependencies

**Prerequisite Stories:** None (foundation story)

**Dependent Stories:**
- S044 (Model Integration) - Requires parameter tables to be available

**External Dependencies:**
- Existing dbt project structure
- Current CSV seed processing pipeline
- Established variable system

## Testing Strategy

### Unit Tests (dbt tests)
```yaml
# Parameter range validation
- dbt_utils.accepted_range:
    column_name: parameter_value
    min_value: 0
    max_value: 1

# Scenario integrity
- unique_combination_of_columns:
    combination_of_columns:
      - scenario_id
      - job_level
      - parameter_name
```

### Integration Tests
- Parameter resolution accuracy across scenarios
- Backward compatibility with existing hardcoded values
- Performance benchmarking for parameter lookup

### Regression Tests
- Existing model outputs unchanged with default scenario
- Variable system integration maintained
- Seed processing pipeline unaffected

## Implementation Steps

1. **Create seed files** with initial parameter data
2. **Build staging models** for parameter processing
3. **Create parameter resolution macro** for dynamic lookup
4. **Add schema validations** and data quality tests
5. **Create default scenario** matching current hardcoded values
6. **Performance testing** and optimization
7. **Documentation updates** and examples

## Rollback Plan

If issues arise:
1. **Immediate:** Revert to existing hardcoded parameters via feature flag
2. **Model-level:** Conditional logic to use old vs new parameter sources
3. **Seed-level:** Maintain backward compatibility with existing CSV structure

## Success Metrics

**Functional Success:**
- All parameter lookups return expected values
- Scenario isolation prevents data leakage
- Default scenario produces identical results to current system

**Performance Success:**
- Parameter resolution adds <100ms to model execution
- Memory usage increase <10% for parameter tables
- dbt compilation time increase <5%

**Quality Success:**
- 100% test coverage for parameter validation
- Zero data quality issues in production
- Complete audit trail for all parameter changes

---

**Story Dependencies:** None
**Blocked By:** None
**Blocking:** S044, S045, S046
**Related Stories:** All stories in E012 epic
