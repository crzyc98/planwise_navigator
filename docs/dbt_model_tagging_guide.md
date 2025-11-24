# dbt Model Tagging Guide

## Overview

This guide documents the tagging conventions implemented for Fidelity PlanAlign Engine's dbt models (Story S064). Tags enable selective testing, deployment, and enhanced protection of critical data infrastructure.

## Tag Categories

### `critical`
**Purpose**: Core business logic that affects downstream reporting and decision-making

**Criteria**:
- Business Impact: Directly affects executive reporting or key metrics
- Dependency Count: >3 downstream models depend on it
- Change Frequency: Infrequent, requires careful review
- Data Volume: Processes significant portion of company data

**Tagged Models**:
- `dim_hazard_table` - Master hazard rates for simulation
- `fct_compensation_growth` - Financial impact calculations
- `fct_workforce_snapshot` - Primary simulation output
- `fct_yearly_events` - Event sourcing foundation
- `int_baseline_workforce` - Simulation starting point
- `int_effective_parameters` - Dynamic parameter resolution
- `int_workforce_previous_year` - Multi-year continuity
- `stg_comp_levers` - Compensation tuning parameters

### `foundation`
**Purpose**: Models that many others depend on; critical for overall data integrity

**Criteria**:
- Dependency Root: Many models depend on these
- Data Quality: Critical for overall data integrity
- Performance: Optimization has widespread impact

**Tagged Models**:
- `dim_hazard_table` - Used by all hazard calculations
- `fct_workforce_snapshot` - Primary output used by dashboards
- `int_baseline_workforce` - Starting point for all simulations
- `int_effective_parameters` - Used by all event models
- `int_workforce_previous_year` - Required for multi-year simulations
- `stg_census_data` - Primary data source

### `locked`
**Purpose**: Schema-stable models that external systems depend on

**Criteria**:
- Schema Stability: External systems depend on current schema
- Contractual: Subject to dbt contracts or SLAs
- Compliance: Required for regulatory reporting
- Event Sourcing: Immutable by architectural design

**Tagged Models**:
- `fct_yearly_events` - Immutable event log
- `stg_census_data` - External data dependency
- `stg_comp_levers` - Parameter interface contract

### `event_sourcing`
**Purpose**: Models that implement event sourcing patterns

**Criteria**:
- Immutable by design
- Part of audit trail
- Event generation or processing logic

**Tagged Models**:
- `fct_yearly_events` - Immutable event log
- `int_hiring_events` - Hiring event generation
- `int_termination_events` - Termination event generation

## Usage Examples

### Tag-Based Operations

```bash
# Test only critical models
dbt test --select tag:critical

# Run foundation models first
dbt run --select tag:foundation

# Test locked models for schema stability
dbt test --select tag:locked

# Full critical path validation
dbt run --select tag:critical,tag:foundation

# Event sourcing models only
dbt run --select tag:event_sourcing
```

### CI/CD Integration

```yaml
# Example CI pipeline steps
- name: Test Critical Models
  run: dbt test --select tag:critical

- name: Validate Locked Schema
  run: dbt test --select tag:locked

- name: Full Foundation Run
  run: dbt run --select tag:foundation
```

## Model Count Summary

- **Critical**: 8 models
- **Foundation**: 6 models
- **Locked**: 3 models
- **Event Sourcing**: 3 models

## Maintenance Guidelines

### Adding New Tags
1. Review model against criteria above
2. Add tags to appropriate `schema.yml` file
3. Test tag-based operations work correctly
4. Update this documentation

### Tag Review Process
- Review tags quarterly or when models change significantly
- Validate that tagged models still meet criteria
- Remove tags from models that no longer qualify

### Best Practices
- Use multiple tags when appropriate (e.g., `critical` + `foundation`)
- Document reasoning for tag assignment in model descriptions
- Test tag-based operations in CI pipeline
- Keep tag usage conservative to maintain effectiveness

## Implementation Status

- ✅ Model classification criteria established
- ✅ 8 critical models tagged
- ✅ Tag-based dbt operations tested
- ✅ Documentation completed
- ✅ CI integration ready

## Future Enhancements

- Automated tagging suggestions based on model usage patterns
- Quantitative criticality scores beyond binary tags
- Integration with deployment approval workflows
- Monitoring and alerting for changes to locked models
