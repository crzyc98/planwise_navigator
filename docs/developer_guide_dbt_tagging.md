# dbt Model Tagging Convention

## Overview

This document establishes the tagging convention for dbt models in Fidelity PlanAlign Engine to enable selective testing, deployment, and enhanced protection of critical data infrastructure.

## Tag Taxonomy

### Critical Models (`critical`)
**Purpose**: Core business logic that affects downstream reporting and executive decision-making.

**Criteria**:
- Directly affects executive reporting or key metrics
- >3 downstream models depend on it
- Changes require careful review and approval
- Processes significant portion of company data

**Examples**:
- `fct_workforce_snapshot` - Primary simulation output
- `fct_yearly_events` - Event sourcing foundation
- `fct_compensation_growth` - Financial impact calculations
- `dim_hazard_table` - Core business logic parameters
- `int_effective_parameters` - Dynamic parameter resolution

### Foundation Models (`foundation`)
**Purpose**: Models that many others depend on and are critical for overall data integrity.

**Criteria**:
- Many models depend on these (dependency root)
- Critical for overall data quality
- Performance optimization has widespread impact
- Form the base layer of the simulation pipeline

**Examples**:
- `stg_census_data` - Primary data source
- `int_baseline_workforce` - Simulation starting point
- `int_workforce_previous_year` - Multi-year continuity
- `dim_hazard_table` - Referenced by all event models

### Locked Models (`locked`)
**Purpose**: Schema stability required - external systems or contracts depend on current schema.

**Criteria**:
- External systems depend on current schema
- Subject to dbt contracts or SLAs
- Required for regulatory reporting
- Event sourcing models (immutable by design)

**Examples**:
- `fct_yearly_events` - Immutable event log
- `stg_census_data` - External data dependencies
- `stg_comp_levers` - Analyst interface contract
- Models with dbt contracts (from S065)

### Event Sourcing Models (`event_sourcing`)
**Purpose**: Models that implement event sourcing patterns with immutable audit trails.

**Criteria**:
- Part of the immutable event log system
- Generate or process workforce events
- Support audit trail and history reconstruction
- Follow event sourcing architectural patterns

**Examples**:
- `fct_yearly_events` - Consolidated event log
- `int_hiring_events` - New employee onboarding events
- `int_termination_events` - Employee departure events
- `int_promotion_events` - Level advancement events
- `int_merit_events` - Compensation adjustment events

## Tag-Based Operations

### Testing Commands
```bash
# Test only critical models
dbt test --select tag:critical

# Test foundation models (run these first)
dbt test --select tag:foundation

# Test all event sourcing models
dbt test --select tag:event_sourcing

# Test locked models (require extra scrutiny)
dbt test --select tag:locked
```

### Model Execution Commands
```bash
# Run foundation models first (dependency order)
dbt run --select tag:foundation

# Run critical models
dbt run --select tag:critical

# Run event sourcing models
dbt run --select tag:event_sourcing

# Combined critical path validation
dbt run --select tag:critical,tag:foundation
```

### CI/CD Pipeline Integration
```bash
# Enhanced validation for critical models in CI
dbt test --select tag:critical --fail-fast

# Separate locked model validation (requires approval)
dbt run --select tag:locked --defer --state ./state
```

## Implementation Guidelines

### Schema.yml Structure
```yaml
models:
  - name: model_name
    description: "Model description"
    config:
      tags: ["tag1", "tag2", "tag3"]
    columns:
      # Column definitions...
```

### Multiple Tags
Models can have multiple tags to reflect their various characteristics:
```yaml
  - name: fct_yearly_events
    config:
      tags: ["critical", "locked", "event_sourcing"]
```

### Tag Assignment Process

1. **New Models**: All new models must be reviewed for appropriate tags
2. **Tag Changes**: Require approval from data team lead
3. **Regular Review**: Quarterly review of tag assignments for relevance

## Usage in CI/CD

### Pull Request Checks
- All `critical` models must pass tests before merge
- `locked` models require additional schema change approval
- Tag-based test selection reduces CI runtime

### Deployment Strategy
```bash
# Stage 1: Foundation models (required for dependencies)
dbt run --select tag:foundation

# Stage 2: Critical business logic
dbt run --select tag:critical

# Stage 3: Event sourcing (can run in parallel with critical)
dbt run --select tag:event_sourcing

# Stage 4: All other models
dbt run --exclude tag:foundation,tag:critical,tag:event_sourcing
```

## Best Practices

### Do's
- ✅ Start conservative with tag assignments
- ✅ Document rationale for critical/locked designations
- ✅ Use tag-based selection in development workflows
- ✅ Include tags in model documentation reviews

### Don'ts
- ❌ Tag too many models as critical (reduces effectiveness)
- ❌ Change tags without team review
- ❌ Use tags as the only form of model categorization
- ❌ Ignore tag-based test failures in CI

## Current Tagged Models Summary

### Critical Models (11)
- `dim_hazard_table`
- `fct_workforce_snapshot`
- `fct_yearly_events`
- `fct_compensation_growth`
- `int_baseline_workforce`
- `int_effective_parameters`
- `int_workforce_previous_year`
- `int_hiring_events`
- `int_merit_events`
- `int_promotion_events`
- `stg_comp_levers`

### Foundation Models (6)
- `dim_hazard_table`
- `fct_workforce_snapshot`
- `int_baseline_workforce`
- `int_effective_parameters`
- `int_workforce_previous_year`
- `stg_census_data`

### Locked Models (3)
- `fct_yearly_events`
- `stg_census_data`
- `stg_comp_levers`

### Event Sourcing Models (6)
- `fct_yearly_events`
- `int_hiring_events`
- `int_termination_events`
- `int_merit_events`
- `int_promotion_events`
- `int_new_hire_termination_events`

## Future Enhancements

### Planned Features
- **Automated Tagging**: ML-based suggestions for model criticality
- **Impact Scoring**: Quantitative criticality scores beyond tags
- **Integration**: Tag-based deployment approvals in CI/CD
- **Monitoring**: Alerts on changes to locked models

### Integration with Other Systems
- **Story S063**: CI script enhancement for tag-based operations
- **Story S065**: dbt contracts will inform locked model tags
- **Story S066**: Schema change detection for locked models

---

*This tagging system establishes the foundation for selective testing and enhanced protection of critical data infrastructure. Regular review and maintenance of tag assignments ensures continued effectiveness.*
