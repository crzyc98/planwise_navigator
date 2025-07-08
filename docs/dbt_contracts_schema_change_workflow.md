# dbt Contracts Schema Change Workflow

## Overview

This document establishes the workflow for managing schema changes to dbt models with enforced contracts. These procedures ensure that breaking changes are caught early and that schema evolution is managed safely.

## Contracted Models

The following models have enforced contracts and require special handling for schema changes:

### 🔒 **Foundation Model**
- **`stg_census_data`** - Primary data foundation
  - **Impact**: Affects ALL downstream models
  - **Approval**: Architecture team required

### 🔒 **Critical Output Models**
- **`fct_workforce_snapshot`** - Core simulation output
  - **Impact**: Affects business reporting and dashboards
  - **Approval**: Data team + business stakeholders required

- **`fct_yearly_events`** - Immutable event log
  - **Impact**: Affects entire event sourcing architecture
  - **Approval**: Architecture team + compliance required

## Change Types and Approval Matrix

| Change Type | Definition | Approval Required | Process |
|-------------|------------|-------------------|---------|
| **Non-Breaking** | Add optional column, relax constraint | Standard code review | Fast track |
| **Breaking** | Change data type, remove column, add NOT NULL | Architecture + Business | Full approval |
| **Critical** | Changes to primary keys, event columns | Architecture + Compliance | Extended review |

## Schema Change Process

### 1. Pre-Change Assessment

Before making any schema changes:

```bash
# 1. Identify downstream dependencies
dbt list --select stg_census_data+  # Find all downstream models

# 2. Check current contract
cat dbt/models/staging/schema.yml | grep -A 50 "name: stg_census_data"

# 3. Assess breaking vs non-breaking change
# Breaking: Changes existing column types, removes columns, adds NOT NULL
# Non-breaking: Adds optional columns, relaxes constraints
```

### 2. Change Categories

#### ✅ **Non-Breaking Changes** (Fast Track)
- Adding optional columns (no NOT NULL constraint)
- Adding new data tests
- Relaxing existing constraints
- Updating descriptions

**Example - Adding optional column:**
```yaml
# ✅ SAFE: Adding optional column
- name: employee_department
  description: "Employee department code (optional)"
  data_type: varchar
  # No constraints - this is safe
```

#### ⚠️ **Breaking Changes** (Approval Required)
- Changing data types
- Removing columns
- Adding NOT NULL constraints
- Renaming columns

**Example - Breaking change:**
```yaml
# ❌ BREAKING: Changing data type
- name: employee_id
  description: "Employee identifier"
  data_type: integer  # Changed from varchar - BREAKING!
  constraints:
    - type: not_null
    - type: unique
```

#### 🚨 **Critical Changes** (Extended Review)
- Changes to primary keys
- Changes to event sourcing columns
- Schema changes affecting compliance

### 3. Implementation Workflow

#### For Non-Breaking Changes:

1. **Update schema.yml** with new column definition
2. **Update model SQL** to include new column
3. **Test locally:**
   ```bash
   dbt compile --select stg_census_data
   dbt run --select stg_census_data --full-refresh
   ```
4. **Submit standard PR** with clear description
5. **Merge** after code review

#### For Breaking Changes:

1. **Create change proposal** documenting:
   - Reason for change
   - Impact assessment
   - Migration strategy
   - Rollback plan

2. **Get approval** from required stakeholders

3. **Implement with migration strategy:**
   ```yaml
   # Option A: Additive approach (recommended)
   # 1. Add new column alongside old
   - name: employee_id_new
     data_type: integer
     constraints:
       - type: not_null

   # 2. In later release, remove old column
   # - name: employee_id (remove this)
   ```

4. **Test thoroughly:**
   ```bash
   # Test contract validation
   dbt compile --select tag:contract

   # Test downstream impacts
   dbt run --select stg_census_data+

   # Run full test suite
   ./scripts/run_ci_tests.sh
   ```

5. **Deploy with monitoring** and rollback plan ready

### 4. Contract Violation Handling

When contract violations occur, you'll see errors like:

```bash
❌ Contract violation in stg_census_data:
   Column 'employee_id' expected type 'varchar' but got 'integer'

💡 To fix:
   1. Update model SQL to match contract, OR
   2. Update contract in schema.yml (requires approval)
   3. If breaking change, follow approval process
```

**Resolution steps:**
1. **Identify** if this is intentional or accidental
2. **If accidental**: Fix model SQL to match contract
3. **If intentional**: Follow breaking change approval process

### 5. Emergency Schema Changes

For urgent production fixes:

1. **Create hotfix branch** from main
2. **Make minimal required changes**
3. **Get emergency approval** from data team lead
4. **Deploy with enhanced monitoring**
5. **Follow up** with proper documentation and review

### 6. Contract Maintenance

#### Quarterly Contract Review
- Review all contract tags and classifications
- Assess if models should be promoted/demoted from contract status
- Update approval matrices based on system evolution

#### Annual Schema Audit
- Full dependency analysis for all contracted models
- Performance impact assessment of contracts
- Contract optimization opportunities

## Tools and Commands

### Contract Validation Commands
```bash
# List all contracted models
dbt list --select tag:contract

# Compile only contracted models
dbt compile --select tag:contract

# Test contracted models
dbt test --select tag:contract

# Check CI with contracts
./scripts/run_ci_tests.sh
```

### Dependency Analysis
```bash
# Find all models that depend on stg_census_data
dbt list --select stg_census_data+

# Find what stg_census_data depends on
dbt list --select +stg_census_data

# Full lineage view
dbt docs generate && dbt docs serve
```

### Contract Debugging
```bash
# Debug contract compilation issues
dbt compile --select stg_census_data --debug

# Check manifest for contract details
cat target/manifest.json | jq '.nodes | to_entries[] | select(.value.contract.enforced == true)'
```

## Approval Workflows

### Standard Approval (Non-Breaking Changes)
1. **Code Review**: 1 approval from data team member
2. **Testing**: CI tests must pass
3. **Merge**: Automatic deploy to staging for validation

### Extended Approval (Breaking Changes)
1. **Impact Assessment**: Document all downstream effects
2. **Architecture Review**: 1 approval from architecture team
3. **Business Review**: 1 approval from business stakeholders
4. **Testing**: Full regression test suite
5. **Staged Deploy**: Manual deploy with monitoring

### Critical Approval (Event Sourcing/Compliance)
1. **Compliance Review**: Approval from compliance team
2. **Architecture Review**: Senior architect approval
3. **Business Review**: Business owner approval
4. **Security Review**: If data sensitivity changes
5. **Extended Testing**: Performance and security testing
6. **Monitored Deploy**: Deploy with full observability

## Migration Strategies

### Additive Migration (Preferred)
```sql
-- Phase 1: Add new column
SELECT
  employee_id,
  employee_id::integer AS employee_id_new,  -- Add new typed column
  employee_ssn,
  ...
FROM source_table

-- Phase 2: Update downstream to use new column
-- Phase 3: Remove old column in later release
```

### Versioned Migration
```sql
-- Use versioned models for major breaking changes
-- stg_census_data_v2.sql with new schema
-- Gradually migrate downstream models
-- Deprecate v1 after full migration
```

## Error Recovery

### Contract Compilation Failures
1. **Check contract definition** in schema.yml
2. **Verify model SQL** produces expected columns/types
3. **Review recent changes** that might have introduced mismatch
4. **Test in isolation** before full compilation

### Downstream Breakage
1. **Identify affected models** using dependency analysis
2. **Assess impact scope** (critical vs non-critical systems)
3. **Implement fix** using appropriate change process
4. **Validate fix** with full downstream testing

## Best Practices

### ✅ Do's
- Always assess impact before schema changes
- Use additive migration strategies when possible
- Test contract changes in isolation first
- Document rationale for all breaking changes
- Keep contracts focused on critical models only

### ❌ Don'ts
- Never bypass contract approval process
- Don't make breaking changes without migration strategy
- Avoid changing primary keys or event columns
- Don't remove contract enforcement without team discussion
- Never merge without testing downstream impacts

## Integration with Existing Processes

### Story S064 (Model Tagging)
- Contract models are automatically tagged with `contract` tag
- Use existing tag-based operations for selective testing
- Leverage tag-based CI validation

### Story S063 (CI Scripts)
- Contract validation integrated into `run_ci_tests.sh`
- Automated contract compilation testing
- Enhanced error reporting for contract violations

---

*This workflow ensures that schema changes to critical models are managed safely while maintaining development velocity and system reliability.*
