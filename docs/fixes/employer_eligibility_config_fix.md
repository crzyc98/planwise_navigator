# Employer Eligibility Configuration Fix

**Status**: ✅ COMPLETED
**Date**: 2025-08-19
**Issue**: Configuration mismatch between dbt model expectations and YAML structure
**Files**: `config/simulation_config.yaml`, `dbt/models/intermediate/int_employer_eligibility.sql`, `run_multi_year.py`

## Problem Statement

The `int_employer_eligibility.sql` dbt model expects flat `core_*` variables (e.g., `core_minimum_tenure_years`) but the configuration file has them nested under `employer_core_contribution.eligibility`. This causes two issues:

1. **Direct dbt runs fail** because variables aren't found at the expected flat level
2. **SQL model has incorrect default** for `core_allow_terminated_new_hires` (should be `false`, not `true`)

## Root Cause Analysis

### Expected by SQL Model (lines 26-30)
```sql
{% set core_minimum_tenure_years = var('core_minimum_tenure_years', 1) | int %}
{% set core_require_active_eoy = var('core_require_active_eoy', true) %}
{% set core_minimum_hours = var('core_minimum_hours', 1000) | int %}
{% set core_allow_new_hires = var('core_allow_new_hires', true) %}
{% set core_allow_terminated_new_hires = var('core_allow_terminated_new_hires', true) %} <!-- BUG: should be false -->
```

### Current Config Structure
```yaml
employer_core_contribution:
  eligibility:
    minimum_tenure_years: 0
    require_active_at_year_end: true
    minimum_hours_annual: 1000
    allow_new_hires: true
    allow_terminated_new_hires: false
```

### Orchestrator Mapping (works correctly)
The `run_multi_year.py` orchestrator correctly maps nested → flat (lines 198-209):
```python
core_elig = core.get('eligibility', {})
if 'minimum_tenure_years' in core_elig:
    dbt_vars['core_minimum_tenure_years'] = int(core_elig['minimum_tenure_years'])
# ... etc
```

## Solution: Nested-Only Approach ✅

Update the dbt model to read directly from the nested configuration structure, eliminating duplication.

### Implementation Steps ✅

#### 1. Update SQL Model to Read Nested Structure
**File**: `dbt/models/intermediate/int_employer_eligibility.sql`
**Changes**: Lines 25-36

```sql
-- BEFORE (flat variables):
{% set core_minimum_tenure_years = var('core_minimum_tenure_years', 1) | int %}
{% set core_require_active_eoy = var('core_require_active_eoy', true) %}
# ... etc

-- AFTER (nested structure):
{% set employer_core_config = var('employer_core_contribution', {}) %}
{% set core_eligibility = employer_core_config.get('eligibility', {}) %}

{% set core_minimum_tenure_years = core_eligibility.get('minimum_tenure_years', 1) | int %}
{% set core_require_active_eoy = core_eligibility.get('require_active_at_year_end', true) %}
{% set core_minimum_hours = core_eligibility.get('minimum_hours_annual', 1000) | int %}
{% set core_allow_new_hires = core_eligibility.get('allow_new_hires', true) %}
{% set core_allow_terminated_new_hires = core_eligibility.get('allow_terminated_new_hires', false) %}
```

#### 2. Update Orchestrator to Pass Nested Structure
**File**: `run_multi_year.py`
**Changes**: Lines 191-194

```python
# BEFORE (individual field mapping):
dbt_vars['core_minimum_tenure_years'] = int(core_elig['minimum_tenure_years'])
dbt_vars['core_require_active_eoy'] = bool(core_elig['require_active_at_year_end'])
# ... etc

# AFTER (pass entire nested structure):
core = cfg.get('employer_core_contribution', {})
if core:
    dbt_vars['employer_core_contribution'] = core
```

#### 3. Remove Duplicate Flat Variables
**File**: `config/simulation_config.yaml`
**Action**: Removed duplicate `core_*` variables, kept only nested structure

## Testing Plan

### Test 1: Direct dbt Run
```bash
cd dbt
dbt run --models int_employer_eligibility --vars "simulation_year: 2025"
```
**Expected**: Should work without needing explicit variable passing

### Test 2: Orchestrated Run
```bash
python run_multi_year.py  # Single year test
```
**Expected**: Should use nested config values mapped by orchestrator

### Test 3: Variable Verification
```bash
cd dbt
dbt compile --models int_employer_eligibility --vars "simulation_year: 2025"
```
**Expected**: Compiled SQL should show `false` for terminated new hires logic

## Validation Criteria ✅

✅ **Direct dbt runs work** with nested structure or defaults
✅ **Orchestrated runs work** using nested config structure
✅ **Default values are correct** in SQL model
✅ **Configuration is clean** - single source of truth
✅ **No breaking changes** to existing functionality
✅ **Eliminates duplication** - no more dual structures

## Benefits ✅

1. **Single Source of Truth**: Only one place to configure employer eligibility settings
2. **Clean Organization**: Related settings grouped logically under `employer_core_contribution`
3. **No Duplication**: Eliminated redundant flat variables that could get out of sync
4. **Maintainable**: Changes only need to be made in one location
5. **Flexible**: Works with both orchestrated runs and direct dbt commands
6. **Robust**: Proper default values if config is missing

## Alternative Approaches Considered

### Option B: Nested-Only with SQL Changes
- **Pros**: Single source of configuration
- **Cons**: Requires complex Jinja logic, breaks direct dbt compatibility

### Option C: dbt_project.yml Variables
- **Pros**: Most dbt-idiomatic
- **Cons**: Separates config across multiple files, harder to maintain

### Decision: Option A (Dual Structure)
Chosen for maximum compatibility and developer experience while maintaining clear organization.

## Implementation Checklist ✅

- [x] Update SQL model to read nested structure (lines 25-36)
- [x] Update orchestrator to pass nested structure (lines 191-194)
- [x] Remove duplicate flat variables from config
- [x] Test direct dbt run with nested structure
- [x] Test direct dbt run with defaults (no config passed)
- [x] Test orchestrated run with nested config
- [x] Verify all tests pass
- [x] Update documentation
- [x] Ready for commit

## Maintenance Notes ✅

When updating employer eligibility configuration:
1. Update **only** the nested structure under `employer_core_contribution.eligibility`
2. No need to maintain duplicate variables - single source of truth
3. SQL model will automatically pick up changes via nested variable reading
4. Both orchestrator and direct dbt runs will work seamlessly

## Usage Examples

### For Direct dbt Development
```bash
# Uses defaults from SQL model
dbt run --models int_employer_eligibility --vars "simulation_year: 2025"

# Or pass custom config
dbt run --models int_employer_eligibility --vars '{
  "simulation_year": 2025,
  "employer_core_contribution": {
    "eligibility": {
      "minimum_tenure_years": 2,
      "allow_new_hires": false
    }
  }
}'
```

### For Production Orchestration
```bash
# Uses config from simulation_config.yaml automatically
python run_multi_year.py
```
