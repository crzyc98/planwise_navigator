# S055 Implementation Roadmap for S056/S057

**Document Type**: Technical Implementation Roadmap
**Source Story**: S055 - Audit Current Raise Timing Implementation
**Target Stories**: S056 (Design), S057 (Implementation)
**Created**: June 26, 2025
**Status**: READY FOR S056 IMPLEMENTATION

---

## 1. Implementation Overview

### 1.1 Current State (S055 Audit Results)
```
✅ AUDIT COMPLETE - Key Findings:
- Current: 50/50 Jan/July split (NOT 100% Jan as claimed)
- Timing logic: LENGTH(employee_id) % 2 deterministic split
- Architecture: Solid event sourcing foundation ready for enhancement
- Issues: Hard-coded logic, schema inconsistency, unrealistic patterns
```

### 1.2 Target State (S056/S057 Deliverables)
```
🎯 IMPLEMENTATION GOALS:
- S056: Design configurable realistic timing system
- S057: Implement month-based distribution with business patterns
- Result: 28% Jan, 18% Apr, 23% July, distributed realistic timing
```

---

## 2. S056 Story - Design Phase

### 2.1 Story Scope Definition
**Title**: Design Realistic Raise Timing System
**Estimated Points**: 3
**Dependencies**: S055 Audit (COMPLETE)

### 2.2 S056 Deliverables

#### 2.2.1 Technical Design Specification
**File**: `docs/S056-realistic-timing-design-spec.md`

**Required Sections**:
- Configuration schema for timing distribution
- Hash-based month/day allocation algorithm
- Migration strategy from current 50/50 logic
- Backward compatibility approach
- Performance impact analysis

#### 2.2.2 Configuration Structure Design
**New File**: `dbt/seeds/config_raise_timing_distribution.csv`

**Proposed Structure**:
```csv
month,percentage,business_justification
1,0.28,"Calendar year alignment, budget implementation"
2,0.03,"Minor adjustments"
3,0.07,"Q1 end adjustments, some fiscal years"
4,0.18,"Merit increase cycles, Q2 budget implementation"
5,0.04,"Minor adjustments"
6,0.05,"Mid-year adjustments"
7,0.23,"Fiscal year starts, educational institutions"
8,0.03,"Minor adjustments"
9,0.04,"Q3 end, some fiscal years"
10,0.08,"Federal fiscal year, some corporate cycles"
11,0.02,"Minor adjustments"
12,0.02,"Year-end adjustments"
```

#### 2.2.3 Algorithm Design
**Hash-Based Distribution Within Months**:
```python
# Pseudocode for S057 implementation
def get_raise_effective_date(employee_id, simulation_year, distribution_config):
    # Step 1: Select month based on distribution percentages
    hash_value = hash(employee_id + str(simulation_year))
    month = select_month_by_percentage(hash_value, distribution_config)

    # Step 2: Select day within month (uniform distribution)
    day_hash = hash(employee_id + str(simulation_year) + str(month))
    day = (day_hash % days_in_month(month, simulation_year)) + 1

    return date(simulation_year, month, day)
```

#### 2.2.4 Migration Strategy
**Approach**: Configuration-controlled rollout
- Add `timing_methodology` parameter to simulation_config.yaml
- Options: "legacy" (current 50/50), "realistic" (new distribution)
- Default: "legacy" for backward compatibility
- S057: Implement both, S058: Switch default to "realistic"

### 2.3 S056 Acceptance Criteria
- [ ] Complete technical design specification documented
- [ ] Configuration schema defined and validated
- [ ] Algorithm design peer-reviewed and approved
- [ ] Performance impact estimated (target: <5% overhead)
- [ ] Migration strategy approved by Analytics Team
- [ ] Backward compatibility approach verified

---

## 3. S057 Story - Implementation Phase

### 3.1 Story Scope Definition
**Title**: Implement Realistic Raise Date Generation Logic
**Estimated Points**: 5
**Dependencies**: S056 Design (COMPLETE)

### 3.2 S057 Implementation Tasks

#### 3.2.1 Core Logic Modification
**File**: `dbt/models/intermediate/events/int_merit_events.sql`

**Changes Required**:
```sql
-- REPLACE lines 81-84 current logic:
CASE
    WHEN (LENGTH(e.employee_id) % 2) = 0 THEN CAST({{ simulation_year }} || '-01-01' AS DATE)
    ELSE CAST({{ simulation_year }} || '-07-01' AS DATE)
END AS effective_date,

-- WITH new realistic timing logic:
{{ get_realistic_raise_date('e.employee_id', simulation_year) }} AS effective_date,
```

#### 3.2.2 New dbt Macro Implementation
**File**: `dbt/macros/get_realistic_raise_date.sql`

**Implementation**:
```sql
{%- macro get_realistic_raise_date(employee_id_column, simulation_year) -%}
  {%- if var('timing_methodology', 'legacy') == 'realistic' -%}
    -- Realistic timing distribution implementation
    {{ realistic_month_day_calculation(employee_id_column, simulation_year) }}
  {%- else -%}
    -- Legacy 50/50 split for backward compatibility
    CASE
        WHEN (LENGTH({{ employee_id_column }}) % 2) = 0
        THEN CAST({{ simulation_year }} || '-01-01' AS DATE)
        ELSE CAST({{ simulation_year }} || '-07-01' AS DATE)
    END
  {%- endif -%}
{%- endmacro -%}
```

#### 3.2.3 Seed Files Implementation
**New Files**:
1. `dbt/seeds/config_raise_timing_distribution.csv` (from S056 design)
2. `dbt/seeds/config_timing_methodology.csv` (methodology selection)

#### 3.2.4 Configuration Integration
**File**: `config/simulation_config.yaml`

**Add Section**:
```yaml
raise_timing:
  methodology: "realistic"  # Options: "legacy", "realistic"
  distribution_profile: "general_corporate"  # Future: "technology", "finance", "government"
  validation_tolerance: 0.02  # ±2% tolerance for monthly distribution validation
```

#### 3.2.5 Schema Fix
**File**: `dbt/models/marts/schema.yml`

**Change Line 66**:
```yaml
# FROM:
accepted_values:
  values: ['termination', 'promotion', 'hire', 'merit_increase']

# TO:
accepted_values:
  values: ['termination', 'promotion', 'hire', 'RAISE']
```

#### 3.2.6 Testing Implementation
**New Tests**:
1. **Monthly Distribution Validation**:
```sql
-- Test: monthly_distribution_within_tolerance
SELECT
    month,
    actual_percentage,
    expected_percentage,
    ABS(actual_percentage - expected_percentage) as variance
FROM (
    SELECT
        EXTRACT(month FROM effective_date) as month,
        COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as actual_percentage
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'RAISE'
    GROUP BY month
) actual
JOIN {{ ref('config_raise_timing_distribution') }} expected
    ON actual.month = expected.month
WHERE ABS(actual_percentage - expected_percentage) > {{ var('timing_tolerance', 2.0) }}
```

2. **Deterministic Behavior Test**:
```sql
-- Test: same_seed_same_results
-- Verify identical timing with same random seed across multiple runs
```

### 3.3 S057 File Modifications Summary

#### 3.3.1 Modified Files
```
dbt/models/intermediate/events/int_merit_events.sql  # Core timing logic
dbt/models/marts/schema.yml                          # Fix event type validation
config/simulation_config.yaml                       # Add timing methodology
```

#### 3.3.2 New Files
```
dbt/macros/get_realistic_raise_date.sql                    # Timing logic macro
dbt/macros/realistic_month_day_calculation.sql             # Distribution algorithm
dbt/seeds/config_raise_timing_distribution.csv             # Monthly percentages
dbt/tests/test_raise_timing_distribution.sql               # Validation tests
docs/S057-implementation-guide.md                          # Implementation documentation
```

#### 3.3.3 Test Files
```
tests/test_monthly_distribution_within_tolerance.sql       # Distribution validation
tests/test_deterministic_timing_behavior.sql               # Reproducibility test
tests/test_backward_compatibility_legacy_mode.sql          # Migration validation
```

### 3.4 S057 Acceptance Criteria
- [ ] Realistic timing distribution implemented (28% Jan, 18% Apr, 23% July)
- [ ] Legacy mode maintains identical results with same random seed
- [ ] Monthly distribution within ±2% tolerance of target percentages
- [ ] All existing data tests continue to pass
- [ ] Performance impact <5% of simulation runtime
- [ ] Schema validation tests pass with 'RAISE' event type
- [ ] Comprehensive test coverage for new timing logic

---

## 4. Testing Strategy

### 4.1 Unit Testing
- **dbt macro tests**: Validate timing calculation logic
- **Seed file validation**: Ensure percentages sum to 100%
- **Configuration validation**: Test all timing methodology options

### 4.2 Integration Testing
- **End-to-end simulation**: Full year simulation with new timing
- **Prorated compensation**: Verify calculations work with realistic timing
- **Event sequencing**: Ensure priority and conflict resolution unchanged

### 4.3 Validation Testing
- **Distribution accuracy**: Monthly percentages within tolerance
- **Deterministic behavior**: Same seed produces identical results
- **Backward compatibility**: Legacy mode produces identical baseline results

### 4.4 Performance Testing
- **Runtime comparison**: New vs. old timing logic performance
- **Memory usage**: DuckDB serialization with new logic
- **Scale testing**: 10K+ employee simulation performance

---

## 5. Risk Mitigation

### 5.1 Technical Risks
**Risk**: Complex hash-based distribution algorithm
**Mitigation**: Implement simple cumulative percentage lookup first, optimize later

**Risk**: DuckDB serialization issues with new logic
**Mitigation**: Follow existing promotion event pattern, extensive testing

**Risk**: Performance degradation
**Mitigation**: Benchmark against current logic, optimize hash calculations

### 5.2 Business Risks
**Risk**: Stakeholder rejection of new timing patterns
**Mitigation**: Maintain legacy mode, provide business justification documentation

**Risk**: Audit concerns about changing established patterns
**Mitigation**: Comprehensive audit trail, business research documentation

### 5.3 Deployment Risks
**Risk**: Breaking changes to existing simulations
**Mitigation**: Default to legacy mode, gradual rollout strategy

**Risk**: Data test failures with new patterns
**Mitigation**: Update tests in parallel, comprehensive validation suite

---

## 6. Definition of Done

### 6.1 S056 Complete When:
- [ ] Technical design specification peer-reviewed and approved
- [ ] Configuration schema designed and documented
- [ ] Algorithm design validated by engineering team
- [ ] Migration strategy approved by Analytics Team
- [ ] Performance estimates within acceptable range
- [ ] S057 implementation ready to begin

### 6.2 S057 Complete When:
- [ ] Realistic timing distribution fully implemented
- [ ] All existing functionality maintains backward compatibility
- [ ] Monthly timing distribution validates within tolerance
- [ ] Performance impact <5% of simulation runtime
- [ ] Comprehensive test suite passes
- [ ] Documentation complete for business and technical teams
- [ ] Analytics Team sign-off on realistic timing patterns

---

## 7. Success Metrics

### 7.1 Technical Success
- **Accuracy**: Monthly distribution within ±2% of target
- **Performance**: <5% runtime impact
- **Reliability**: 100% reproducibility with same random seed
- **Quality**: All data tests pass, no regression

### 7.2 Business Success
- **Credibility**: Analytics team approval of realistic patterns
- **Auditability**: Timing patterns defensible in compliance reviews
- **Flexibility**: Configuration supports future business requirements
- **Adoption**: Smooth migration from legacy to realistic timing

---

**Roadmap Owner**: Engineering Team
**Technical Review**: PENDING S056 initiation
**Business Sponsor**: Analytics Team
**Implementation Status**: READY TO BEGIN S056 DESIGN PHASE
