# S056 Backward Compatibility Design

**Document Type**: Technical Design
**Story ID**: S056
**Component**: Backward Compatibility Framework
**Created**: June 26, 2025
**Status**: DESIGN PHASE

---

## 1. Compatibility Requirements

### 1.1 Zero Breaking Changes Mandate
- **Existing Simulations**: Must work unchanged with no configuration modifications
- **Regression Testing**: Same random seed produces identical timing results in legacy mode
- **Performance**: Legacy mode maintains current performance characteristics
- **API Stability**: No changes to existing dbt model interfaces

### 1.2 Compatibility Scope
- **Configuration Files**: Existing simulation_config.yaml works without changes
- **dbt Variables**: Current variable usage patterns unchanged
- **Database Schema**: No changes to event tables or column definitions
- **Event Sequencing**: Existing priority and conflict resolution preserved

---

## 2. Technical Implementation Design

### 2.1 Dual-Mode Macro System
```sql
-- Primary interface macro (replaces hard-coded logic)
{% macro get_realistic_raise_date(employee_id_column, simulation_year) %}
  {% if var('raise_timing_methodology', 'legacy') == 'realistic' %}
    {{ realistic_timing_calculation(employee_id_column, simulation_year) }}
  {% else %}
    {{ legacy_timing_calculation(employee_id_column, simulation_year) }}
  {% endif %}
{% endmacro %}
```

**Key Design Features**:
- **Default Behavior**: `var('raise_timing_methodology', 'legacy')` ensures backward compatibility
- **Explicit Opt-In**: Realistic timing requires conscious configuration change
- **Isolated Logic**: Legacy and realistic calculations completely separate

### 2.2 Legacy Mode Implementation
```sql
-- dbt/macros/legacy_timing_calculation.sql
{% macro legacy_timing_calculation(employee_id_column, simulation_year) %}
  -- Exact replication of current int_merit_events.sql logic (lines 81-84)
  CASE
    WHEN (LENGTH({{ employee_id_column }}) % 2) = 0
    THEN CAST({{ simulation_year }} || '-01-01' AS DATE)
    ELSE CAST({{ simulation_year }} || '-07-01' AS DATE)
  END
{% endmacro %}
```

**Compatibility Guarantees**:
- **Identical Logic**: Exact byte-for-byte match with current implementation
- **Same Performance**: O(1) calculation, no additional overhead
- **Deterministic**: Same employee_id produces same date in every run

### 2.3 Configuration Backward Compatibility

#### 2.3.1 No Configuration Changes Required
```yaml
# Existing simulation_config.yaml continues to work unchanged
compensation:
  cola_rate: 0.01
  merit_budget: 0.035
  # ... all existing parameters
```

#### 2.3.2 dbt Variables Backward Compatibility
```yaml
# dbt_project.yml default values ensure compatibility
vars:
  # Existing variables unchanged
  simulation_year: 2025
  random_seed: 42

  # New variables with safe defaults
  raise_timing_methodology: "legacy"  # CRITICAL: defaults to current behavior
  raise_timing_profile: "general_corporate"
  timing_tolerance: 2.0
```

---

## 3. Integration Compatibility

### 3.1 int_merit_events.sql Integration
```sql
-- BEFORE (current logic, lines 81-84):
CASE
    WHEN (LENGTH(e.employee_id) % 2) = 0 THEN CAST({{ simulation_year }} || '-01-01' AS DATE)
    ELSE CAST({{ simulation_year }} || '-07-01' AS DATE)
END AS effective_date,

-- AFTER (backward compatible):
{{ get_realistic_raise_date('e.employee_id', simulation_year) }} AS effective_date,
```

**Compatibility Impact**:
- **Legacy Mode**: Produces identical results to BEFORE implementation
- **Realistic Mode**: Requires explicit opt-in via configuration
- **Default Behavior**: No changes unless specifically configured

### 3.2 Event Processing Compatibility
- **Event Type**: Continues to use 'RAISE' (no schema changes needed)
- **Event Sequencing**: Priority 3 (after termination, promotion) unchanged
- **Prorated Calculations**: Existing logic in fct_workforce_snapshot.sql works with both modes
- **Data Flow**: int_merit_events → fct_yearly_events → fct_workforce_snapshot unchanged

### 3.3 Testing Compatibility
```sql
-- Existing tests continue to pass in legacy mode
-- Example: Current raise timing validation
SELECT COUNT(*) as jan_raises
FROM fct_yearly_events
WHERE event_type = 'RAISE'
  AND EXTRACT(month FROM effective_date) = 1
-- Legacy mode: ~50% of total raises (even-length employee_ids)
-- Realistic mode: ~28% of total raises (configured distribution)
```

---

## 4. Migration Safety Framework

### 4.1 Zero-Risk Default Configuration
```yaml
# Safe defaults in all configuration layers:

# 1. dbt_project.yml
vars:
  raise_timing_methodology: "legacy"  # Default to current behavior

# 2. simulation_config.yaml (optional addition)
raise_timing:
  methodology: "legacy"  # Explicit backward compatibility

# 3. Macro fallback
{% if var('raise_timing_methodology', 'legacy') == 'realistic' %}
  # Default to 'legacy' if variable not defined
```

### 4.2 Gradual Opt-In Strategy
```yaml
# Phase 1: Default to legacy (S056/S057)
raise_timing:
  methodology: "legacy"

# Phase 2: Testing and validation (S058)
raise_timing:
  methodology: "realistic"  # Opt-in for testing

# Phase 3: Default switch (Future S059)
# Change default to "realistic" only after full validation
```

### 4.3 Rollback Strategy
**Immediate Rollback** (Configuration change):
```yaml
# Simple configuration change reverts to legacy behavior
raise_timing:
  methodology: "legacy"
```

**Code Rollback** (Git revert):
- Legacy macro remains in codebase permanently
- Git revert to previous commit available
- No risk of losing backward compatibility

---

## 5. Validation Framework

### 5.1 Backward Compatibility Testing
```sql
-- Test: Legacy mode produces identical results
WITH current_simulation AS (
  -- Run with current hard-coded logic
  SELECT employee_id, effective_date as current_date
  FROM int_merit_events_current
),
legacy_mode_simulation AS (
  -- Run with new macro in legacy mode
  SELECT employee_id, effective_date as legacy_date
  FROM int_merit_events_with_macro
  WHERE {{ var('raise_timing_methodology') }} = 'legacy'
)
SELECT COUNT(*) as date_mismatches
FROM current_simulation c
JOIN legacy_mode_simulation l ON c.employee_id = l.employee_id
WHERE c.current_date != l.legacy_date
-- Expected result: 0 mismatches
```

### 5.2 Deterministic Behavior Validation
```sql
-- Test: Same seed produces same results across runs
WITH run_1 AS (
  SELECT employee_id, effective_date as date_1
  FROM fct_yearly_events
  WHERE event_type = 'RAISE' AND random_seed = 42
),
run_2 AS (
  SELECT employee_id, effective_date as date_2
  FROM fct_yearly_events
  WHERE event_type = 'RAISE' AND random_seed = 42
)
SELECT COUNT(*) as reproducibility_failures
FROM run_1 r1
JOIN run_2 r2 ON r1.employee_id = r2.employee_id
WHERE r1.date_1 != r2.date_2
-- Expected result: 0 failures
```

### 5.3 Performance Compatibility Validation
```sql
-- Performance test: Legacy mode timing
EXPLAIN ANALYZE
SELECT {{ get_realistic_raise_date('employee_id', 2025) }} as raise_date
FROM employees
WHERE {{ var('raise_timing_methodology') }} = 'legacy'
-- Expected: Same performance as current hard-coded logic
```

---

## 6. Error Handling and Validation

### 6.1 Configuration Validation
```sql
-- Validate methodology parameter
{% if var('raise_timing_methodology') not in ['legacy', 'realistic', 'custom'] %}
  {{ log("ERROR: Invalid raise_timing_methodology. Must be 'legacy', 'realistic', or 'custom'", info=false) }}
  {{ exceptions.raise_compiler_error("Invalid raise_timing_methodology configuration") }}
{% endif %}
```

### 6.2 Fallback Logic
```sql
-- Robust fallback to legacy mode
{% macro get_realistic_raise_date(employee_id_column, simulation_year) %}
  {% set methodology = var('raise_timing_methodology', 'legacy') %}
  {% if methodology == 'realistic' %}
    {{ realistic_timing_calculation(employee_id_column, simulation_year) }}
  {% elif methodology == 'custom' %}
    {{ custom_timing_calculation(employee_id_column, simulation_year) }}
  {% else %}
    -- Default to legacy for any unrecognized value
    {{ legacy_timing_calculation(employee_id_column, simulation_year) }}
  {% endif %}
{% endmacro %}
```

### 6.3 Runtime Validation
```sql
-- Validate results match expected patterns
{% macro validate_timing_results() %}
  WITH timing_validation AS (
    SELECT
      COUNT(*) as total_raises,
      COUNT(CASE WHEN EXTRACT(month FROM effective_date) = 1 THEN 1 END) as jan_raises,
      COUNT(CASE WHEN EXTRACT(month FROM effective_date) = 7 THEN 1 END) as jul_raises
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'RAISE'
  )
  SELECT
    total_raises,
    jan_raises,
    jul_raises,
    CASE
      WHEN {{ var('raise_timing_methodology') }} = 'legacy'
        AND (jan_raises + jul_raises) != total_raises
      THEN 'LEGACY_VALIDATION_FAILED'
      ELSE 'VALIDATION_PASSED'
    END as validation_status
  FROM timing_validation
{% endmacro %}
```

---

## 7. Documentation and Communication

### 7.1 Breaking Change Documentation
```markdown
# BREAKING CHANGES: NONE

## S056/S057 Raise Timing Enhancement

**Backward Compatibility**: FULL
- Existing simulations work unchanged
- No configuration modifications required
- Legacy timing mode as permanent fallback

## Migration Path
1. **No Action Required**: Current behavior preserved by default
2. **Opt-In Testing**: Enable realistic timing via configuration
3. **Gradual Rollout**: Switch default in future release (S059)
```

### 7.2 Configuration Documentation
```yaml
# Optional: Enable realistic raise timing
raise_timing:
  methodology: "realistic"      # Options: "legacy" (default), "realistic", "custom"
  distribution_profile: "general_corporate"  # Industry pattern selection
  validation_tolerance: 0.02    # ±2% tolerance for distribution accuracy
```

### 7.3 Troubleshooting Guide
```markdown
## Issue: Timing patterns changed unexpectedly
**Solution**: Verify `raise_timing_methodology` is set to "legacy"

## Issue: Performance degradation
**Solution**: Legacy mode maintains original performance. Check methodology configuration.

## Issue: Test failures after upgrade
**Solution**: Legacy mode should pass all existing tests. Check configuration defaults.
```

---

## 8. Success Criteria

### 8.1 Technical Compatibility
- [ ] Legacy mode produces identical results to current implementation
- [ ] Same random seed generates identical timing in legacy mode
- [ ] No performance degradation in legacy mode
- [ ] All existing dbt tests pass unchanged

### 8.2 Configuration Compatibility
- [ ] Existing simulation_config.yaml works without modification
- [ ] dbt variables maintain current behavior by default
- [ ] No breaking changes to existing simulation workflows

### 8.3 Operational Compatibility
- [ ] Zero configuration changes required for existing users
- [ ] Gradual opt-in capability for realistic timing
- [ ] Simple rollback strategy via configuration change
- [ ] Complete audit trail of timing methodology choices

---

## 9. Risk Assessment

### 9.1 Low Risk Areas
- **Configuration**: Safe defaults prevent breaking changes
- **Performance**: Legacy mode unchanged, realistic mode optional
- **Testing**: Comprehensive validation of backward compatibility

### 9.2 Risk Mitigation
- **Default to Legacy**: No behavior changes unless explicitly opted in
- **Permanent Fallback**: Legacy mode always available for rollback
- **Incremental Rollout**: Realistic timing only after validation

---

**Compatibility Owner**: Engineering Team
**Review Status**: DESIGN PHASE
**Implementation Risk**: LOW (configuration-controlled, backward compatible)
