# Story S065: Implement dbt Contracts for Core Models

## Story Overview

**Story ID**: S065
**Epic**: E014 - Layered Defense Strategy
**Story Points**: 10
**Priority**: Must Have
**Sprint**: 9
**Status**: Not Started

## User Story

**As a** data architect
**I want** to define and enforce dbt contracts for core data models
**So that** schema changes are explicitly managed and breaking changes are prevented

## Background

dbt contracts provide compile-time enforcement of model schemas, ensuring that:
- Column names, types, and constraints are explicitly declared
- Schema changes require intentional updates to contract definitions
- Breaking changes are caught before they reach production
- API-like stability for critical data models

This is particularly important for PlanWise Navigator's event sourcing architecture, where schema stability is crucial for data integrity.

## Acceptance Criteria

1. **Contract Schema Definition**
   - Contract schema defined for 3+ core models (stg_census_data, fct_workforce_snapshot, fct_yearly_events)
   - All column names, data types, and constraints explicitly declared
   - Contract definitions stored in dedicated schema files

2. **Contract Enforcement**
   - dbt contracts enforced with `contract: enforced: true` configuration
   - CI pipeline fails gracefully when contract violations detected
   - Clear error messages guide developers to resolution

3. **Schema Change Process**
   - Schema change process documented for contracted models
   - Approval workflow defined for contract modifications
   - Backward compatibility assessment required for changes

4. **Integration and Testing**
   - Backward compatibility maintained for existing downstream consumers
   - Contract validation integrated into CI script (S063)
   - Performance impact assessed and optimized

5. **Documentation and Training**
   - Contract system documented in developer guide
   - Examples provided for adding new contracts
   - Team trained on contract workflow

## Technical Implementation

### Core Models for Contracts

#### 1. stg_census_data (Foundation)
```yaml
# models/contracts/stg_census_data_contract.yml
version: 2

models:
  - name: stg_census_data
    description: "LOCKED CONTRACT: Primary census data foundation"
    config:
      contract:
        enforced: true
    columns:
      - name: employee_id
        description: "Primary key - NEVER change"
        data_type: varchar
        constraints:
          - type: not_null
          - type: unique
      - name: employee_ssn
        description: "SSN for compliance"
        data_type: varchar
        constraints:
          - type: not_null
      - name: employee_annualized_compensation
        description: "Annualized compensation"
        data_type: decimal
        constraints:
          - type: not_null
```

#### 2. fct_workforce_snapshot (Critical Output)
```yaml
# models/contracts/fct_workforce_snapshot_contract.yml
version: 2

models:
  - name: fct_workforce_snapshot
    description: "LOCKED CONTRACT: Core simulation output"
    config:
      contract:
        enforced: true
    columns:
      - name: employee_id
        data_type: varchar
        constraints:
          - type: not_null
      - name: simulation_year
        data_type: integer
        constraints:
          - type: not_null
      - name: employment_status
        data_type: varchar
        constraints:
          - type: not_null
      - name: current_compensation
        data_type: decimal
        constraints:
          - type: not_null
```

#### 3. fct_yearly_events (Event Sourcing)
```yaml
# models/contracts/fct_yearly_events_contract.yml
version: 2

models:
  - name: fct_yearly_events
    description: "LOCKED CONTRACT: Immutable event log"
    config:
      contract:
        enforced: true
    columns:
      - name: employee_id
        data_type: varchar
        constraints:
          - type: not_null
      - name: event_type
        data_type: varchar
        constraints:
          - type: not_null
      - name: simulation_year
        data_type: integer
        constraints:
          - type: not_null
      - name: effective_date
        data_type: date
        constraints:
          - type: not_null
```

### Contract Directory Structure
```
dbt/
├── models/
│   ├── contracts/
│   │   ├── schema.yml                    # Contract definitions
│   │   ├── stg_census_data_contract.yml  # Individual contracts
│   │   └── fct_*_contract.yml
│   ├── staging/
│   ├── intermediate/
│   └── marts/
```

### CI Integration
```bash
# In run_ci_tests.sh
echo "🔒 Validating dbt contracts..."
dbt compile --select config.contract:true
```

## Schema Change Workflow

### 1. Impact Assessment
- Identify all downstream dependencies
- Assess breaking vs. non-breaking changes
- Document rationale for schema change

### 2. Contract Update Process
```yaml
# Non-breaking change (adding optional column)
- name: new_optional_column
  data_type: varchar
  constraints: []  # No not_null constraint

# Breaking change (requires approval)
- name: existing_column
  data_type: integer  # Changed from varchar - BREAKING
```

### 3. Approval Requirements
- **Non-breaking**: Standard code review
- **Breaking**: Architecture review + business approval
- **Critical models**: Additional testing requirements

## Testing Strategy

### Contract Validation Tests
```python
def test_contract_enforcement():
    """Verify contracts prevent schema violations"""
    # Test that schema changes fail compilation
    # Test that contract violations produce clear errors

def test_backward_compatibility():
    """Ensure contracts don't break existing queries"""
    # Test existing downstream models still work
    # Validate API compatibility maintained
```

### Performance Testing
- Measure compilation time impact
- Validate no runtime performance degradation
- Test with large datasets

## Definition of Done

- [ ] 3+ core models have enforced contracts
- [ ] Contract violations fail CI with clear error messages
- [ ] Schema change process documented and tested
- [ ] Backward compatibility validated for all contracted models
- [ ] Team trained on contract system
- [ ] Performance impact assessed (target: <10% compilation time increase)

## Dependencies

- **dbt Version**: Contracts require dbt 1.5+ (current: 1.8.8 ✅)
- **Story S063**: CI script integration
- **Story S064**: Critical model identification

## Risks and Mitigation

### Risk: Compilation Performance
- **Issue**: Contracts may slow dbt compilation
- **Mitigation**: Benchmark performance, implement only on critical models initially

### Risk: Developer Friction
- **Issue**: Contracts require more upfront schema definition
- **Mitigation**: Provide templates, clear documentation, gradual adoption

### Risk: DuckDB Compatibility
- **Issue**: DuckDB adapter may have contract limitations
- **Mitigation**: Test thoroughly with dbt-duckdb 1.8.1, fallback plan available

### Risk: Over-Contracting
- **Issue**: Too many contracts reduce development agility
- **Mitigation**: Start with 3 core models, expand based on value demonstrated

## Success Metrics

- **Schema Stability**: Zero unintentional breaking changes to contracted models
- **Error Detection**: Contract violations caught in CI, not production
- **Developer Adoption**: Positive feedback on contract system
- **Documentation Quality**: Contract definitions serve as up-to-date API docs

## Future Enhancements

- **Automated Contract Generation**: Generate initial contracts from existing models
- **Version Management**: Support for contract versioning and migration
- **Cross-Model Contracts**: Enforce relationships between models
- **Performance Optimization**: Optimize contract validation for large projects

## Example Error Handling

```bash
# Expected error output for contract violation
❌ Contract violation in fct_workforce_snapshot:
   Column 'employee_id' expected type 'varchar' but got 'integer'

💡 To fix:
   1. Update model to match contract, OR
   2. Update contract in models/contracts/schema.yml
   3. If breaking change, follow schema change approval process
```

---

*This story provides compile-time schema enforcement for critical data models, preventing the "fix one thing, break another" problem at the source.*
