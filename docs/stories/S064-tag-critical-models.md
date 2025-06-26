# Story S064: Tag Critical dbt Models

## Story Overview

**Story ID**: S064
**Epic**: E014 - Layered Defense Strategy
**Story Points**: 3
**Priority**: Must Have
**Sprint**: 8
**Status**: Not Started

## User Story

**As a** data engineer
**I want** to tag critical and locked dbt models in schema.yml
**So that** their importance is clear and they can be targeted for more rigorous testing or deployment safeguards

## Background

Currently, all dbt models are treated equally in our testing and deployment processes. However, some models are more critical to business operations and require enhanced protection:

- **Critical Models**: Core business logic that affects downstream reporting
- **Locked Models**: Schemas that must not change without careful review
- **Foundation Models**: Models that many others depend on

Without clear identification, developers may unknowingly make breaking changes to critical infrastructure.

## Acceptance Criteria

1. **Model Classification System**
   - Definition of "critical" and "locked" models established and documented
   - Clear criteria for what makes a model critical vs. standard
   - Process defined for promoting models to critical status

2. **Tagging Implementation**
   - At least 5 critical dbt models identified and tagged with appropriate tags
   - Tags include: `critical`, `locked`, `foundation`, `event_sourcing`
   - Models tagged in their respective schema.yml files

3. **Tag-Based Operations**
   - Tag-based test selection works: `dbt test --select tag:critical`
   - Tag-based model runs work: `dbt run --select tag:locked`
   - Tags visible in dbt docs and manifest

4. **Documentation and Guidelines**
   - Tagging convention documented in developer guide
   - Examples provided for each tag type
   - Process for requesting tag changes documented

5. **CI Integration**
   - Tagged models receive enhanced validation in CI pipeline
   - Critical models tested in every CI run
   - Locked models require additional approval for schema changes

## Technical Implementation

### Model Tags to Implement

#### Core Business Models (tag: critical)
- `fct_workforce_snapshot` - Primary simulation output
- `fct_yearly_events` - Event sourcing foundation
- `fct_compensation_growth` - Financial impact calculations
- `dim_hazard_table` - Core business logic parameters

#### Data Foundation (tag: foundation)
- `stg_census_data` - Primary data source
- `int_baseline_workforce` - Simulation starting point
- `int_workforce_previous_year` - Multi-year continuity

#### Schema Locked (tag: locked)
- Models with dbt contracts (from S065)
- Event sourcing models (immutable by design)
- External API/export dependencies

#### Event Sourcing (tag: event_sourcing)
- `fct_yearly_events` - Immutable event log
- `int_*_events` models - Event generation logic

### Schema.yml Structure
```yaml
models:
  - name: fct_workforce_snapshot
    description: "Year-end workforce snapshot"
    config:
      tags: ["critical", "foundation"]

  - name: fct_yearly_events
    description: "Immutable event log"
    config:
      tags: ["critical", "locked", "event_sourcing"]

  - name: stg_census_data
    description: "Primary data foundation"
    config:
      tags: ["foundation", "locked"]
```

### Tag-Based CI Commands
```bash
# Test only critical models
dbt test --select tag:critical

# Run foundation models first
dbt run --select tag:foundation

# Full critical path validation
dbt run --select tag:critical tag:foundation
```

## Classification Criteria

### Critical Models
- **Business Impact**: Directly affects executive reporting or key metrics
- **Dependency Count**: >3 downstream models depend on it
- **Change Frequency**: Infrequent, requires careful review
- **Data Volume**: Processes significant portion of company data

### Locked Models
- **Schema Stability**: External systems depend on current schema
- **Contractual**: Subject to dbt contracts or SLAs
- **Compliance**: Required for regulatory reporting
- **Event Sourcing**: Immutable by architectural design

### Foundation Models
- **Dependency Root**: Many models depend on these
- **Data Quality**: Critical for overall data integrity
- **Performance**: Optimization has widespread impact

## Testing Strategy

### Validation Tests
- Verify all tagged models compile successfully
- Test tag-based selection works across different dbt commands
- Validate tags appear correctly in dbt documentation

### Impact Analysis
- Document downstream dependencies for each critical model
- Test that tag changes don't break existing workflows
- Validate performance impact of tag-based operations

## Definition of Done

- [ ] Model classification criteria documented
- [ ] At least 5 models tagged with appropriate tags
- [ ] Tag-based dbt operations tested and working
- [ ] Documentation updated with tagging conventions
- [ ] CI script updated to use tagged models
- [ ] Team trained on new tagging system

## Dependencies

- **Story S063**: CI script needs tag-based operations
- **Story S065**: dbt contracts will inform locked model tags
- **Current dbt version**: Tags supported in dbt 1.8.8

## Risks and Mitigation

### Risk: Over-Tagging
- **Issue**: Tagging too many models as critical reduces effectiveness
- **Mitigation**: Start conservative, expand based on usage patterns

### Risk: Tag Drift
- **Issue**: Tags become outdated as models evolve
- **Mitigation**: Include tag review in model change approval process

### Risk: Performance Impact
- **Issue**: Tag-based operations might be slower than expected
- **Mitigation**: Benchmark tag operations, optimize if needed

## Success Metrics

- **Clear Identification**: Developers can easily identify critical models
- **Targeted Testing**: CI runs use tag-based selection for efficiency
- **Change Awareness**: Reduced accidental changes to critical models
- **Documentation Usage**: Tags visible and useful in dbt docs

## Future Enhancements

- **Automated Tagging**: ML-based suggestions for model criticality
- **Impact Scoring**: Quantitative criticality scores beyond tags
- **Integration**: Tag-based deployment approvals in CI/CD
- **Monitoring**: Alert on changes to locked models

---

*This story establishes the foundation for selective testing and enhanced protection of critical data infrastructure.*
