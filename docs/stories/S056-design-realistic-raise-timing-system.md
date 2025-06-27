# Story S056: Design Realistic Raise Timing System

**Story ID**: S056
**Story Name**: Design Realistic Raise Timing System
**Epic**: E012 - Compensation System Integrity Fix (Phase 3)
**Story Points**: 3
**Priority**: Must Have
**Sprint**: TBD
**Status**: Complete
**Assigned To**: Engineering Team
**Business Owner**: Analytics Team

## Problem Statement

Based on S055 audit findings, the current RAISE timing implementation uses an oversimplified 50/50 split between January 1st and July 1st that does not reflect realistic business practices. This design story will create the technical specification for implementing configurable, realistic raise timing patterns that align with industry standards.

### S055 Audit Key Findings
- **Current State**: 50/50 Jan/July deterministic split based on employee_id length
- **Business Impact**: Unrealistic timing patterns undermine simulation credibility
- **Architecture**: Solid event sourcing foundation ready for enhancement
- **Technical Debt**: Hard-coded logic with no configuration flexibility

## User Story

**As a** workforce analytics team member
**I want** a configurable, realistic raise timing system design
**So that** I can implement timing patterns that match actual corporate practices and improve simulation credibility

## Technical Objectives

### 1. Design Goals
- **Realistic Patterns**: Implement research-based monthly distribution (28% Jan, 18% Apr, 23% July)
- **Configurable Framework**: Enable flexible timing patterns via configuration
- **Backward Compatibility**: Maintain current results for regression testing
- **Performance Optimization**: Ensure <5% impact on simulation runtime
- **Event Sourcing Alignment**: Follow existing promotion event timing patterns

### 2. Design Constraints
- **Deterministic Behavior**: Same random seed must produce identical results
- **DuckDB Compatibility**: Maintain serialization patterns and connection management
- **dbt Integration**: Follow existing model patterns and macro conventions
- **Event Sequencing**: Preserve existing event priority and conflict resolution

## Design Requirements

### 1. Timing Distribution Framework

**Target Monthly Distribution** (from S055 business requirements):
```yaml
monthly_distribution:
  january: 28%     # Calendar year alignment, budget implementation
  february: 3%     # Minor adjustments
  march: 7%        # Q1 end adjustments, some fiscal years
  april: 18%       # Merit increase cycles, Q2 budget implementation
  may: 4%          # Minor adjustments
  june: 5%         # Mid-year adjustments
  july: 23%        # Fiscal year starts, educational institutions
  august: 3%       # Minor adjustments
  september: 4%    # Q3 end, some fiscal years
  october: 8%      # Federal fiscal year, some corporate cycles
  november: 2%     # Minor adjustments
  december: 2%     # Year-end adjustments
```

### 2. Algorithm Design Requirements

**Hash-Based Distribution**:
- Follow existing promotion event pattern (`int_promotion_events.sql:70`)
- Two-stage process: month selection → day selection within month
- Maintain deterministic behavior across simulation runs
- Support cumulative percentage lookup for month selection

**Timing Methodology Options**:
- `legacy`: Current 50/50 Jan/July split (backward compatibility)
- `realistic`: New monthly distribution pattern
- `custom`: Future support for industry-specific patterns

### 3. Configuration Architecture

**Configuration Layers**:
1. **Global Methodology**: `simulation_config.yaml` - timing approach selection
2. **Distribution Parameters**: Seed files - monthly percentage allocation
3. **Validation Rules**: Tolerance settings for distribution accuracy
4. **Future Extensions**: Industry profiles, department overrides

## Design Specification

### 1. Core Algorithm Design

#### 1.1 Two-Stage Hash Distribution
```python
def get_realistic_raise_date(employee_id, simulation_year, distribution_config):
    """
    Generate realistic raise effective date using two-stage hashing

    Stage 1: Select month based on cumulative distribution
    Stage 2: Select day within month using uniform distribution
    """

    # Stage 1: Month Selection
    base_hash = hash(f"{employee_id}_{simulation_year}_month")
    month_selector = abs(base_hash) % 10000 / 10000.0  # 0.0 to 1.0

    # Cumulative lookup in distribution table
    cumulative_percent = 0.0
    selected_month = 1
    for month, percentage in distribution_config.items():
        cumulative_percent += percentage
        if month_selector <= cumulative_percent:
            selected_month = month
            break

    # Stage 2: Day Selection within Month
    day_hash = hash(f"{employee_id}_{simulation_year}_day_{selected_month}")
    days_in_month = get_days_in_month(selected_month, simulation_year)
    selected_day = (abs(day_hash) % days_in_month) + 1

    return date(simulation_year, selected_month, selected_day)
```

#### 1.2 SQL Implementation Strategy
```sql
-- dbt macro implementation approach
{% macro get_realistic_raise_date(employee_id_column, simulation_year) %}
  {% if var('raise_timing_methodology', 'legacy') == 'realistic' %}
    {{ realistic_timing_calculation(employee_id_column, simulation_year) }}
  {% else %}
    {{ legacy_timing_calculation(employee_id_column, simulation_year) }}
  {% endif %}
{% endmacro %}

{% macro realistic_timing_calculation(employee_id_column, simulation_year) %}
  -- Two-stage hash calculation
  WITH month_selection AS (
    SELECT
      {{ employee_id_column }} as emp_id,
      ABS(HASH({{ employee_id_column }} || '_' || {{ simulation_year }} || '_month')) % 10000 / 10000.0 as month_selector
  ),
  cumulative_distribution AS (
    SELECT
      month,
      percentage,
      SUM(percentage) OVER (ORDER BY month) as cumulative_percent
    FROM {{ ref('config_raise_timing_distribution') }}
  ),
  selected_months AS (
    SELECT
      ms.emp_id,
      MIN(cd.month) as selected_month
    FROM month_selection ms
    JOIN cumulative_distribution cd
      ON ms.month_selector <= cd.cumulative_percent
    GROUP BY ms.emp_id
  ),
  day_selection AS (
    SELECT
      sm.emp_id,
      sm.selected_month,
      (ABS(HASH(sm.emp_id || '_' || {{ simulation_year }} || '_day_' || sm.selected_month)) %
       EXTRACT(DAY FROM (DATE_TRUNC('month', CAST({{ simulation_year }} || '-' || sm.selected_month || '-01' AS DATE)) + INTERVAL 1 MONTH - INTERVAL 1 DAY))) + 1 as selected_day
    FROM selected_months sm
  )
  SELECT
    CAST({{ simulation_year }} || '-' ||
         LPAD(ds.selected_month::VARCHAR, 2, '0') || '-' ||
         LPAD(ds.selected_day::VARCHAR, 2, '0') AS DATE)
  FROM day_selection ds
  WHERE ds.emp_id = {{ employee_id_column }}
{% endmacro %}
```

### 2. Configuration Schema Design

#### 2.1 Timing Distribution Configuration
**File**: `dbt/seeds/config_raise_timing_distribution.csv`
```csv
month,percentage,business_justification,industry_profile
1,0.28,"Calendar year alignment, budget implementation","general_corporate"
2,0.03,"Minor adjustments","general_corporate"
3,0.07,"Q1 end adjustments, some fiscal years","general_corporate"
4,0.18,"Merit increase cycles, Q2 budget implementation","general_corporate"
5,0.04,"Minor adjustments","general_corporate"
6,0.05,"Mid-year adjustments","general_corporate"
7,0.23,"Fiscal year starts, educational institutions","general_corporate"
8,0.03,"Minor adjustments","general_corporate"
9,0.04,"Q3 end, some fiscal years","general_corporate"
10,0.08,"Federal fiscal year, some corporate cycles","general_corporate"
11,0.02,"Minor adjustments","general_corporate"
12,0.02,"Year-end adjustments","general_corporate"
```

#### 2.2 Methodology Configuration
**File**: `config/simulation_config.yaml` (addition)
```yaml
raise_timing:
  methodology: "realistic"  # Options: "legacy", "realistic", "custom"
  distribution_profile: "general_corporate"  # Future: "technology", "finance", "government"
  validation_tolerance: 0.02  # ±2% tolerance for monthly distribution
  deterministic_behavior: true  # Ensure reproducible results
```

#### 2.3 Validation Configuration
**File**: `dbt/seeds/config_timing_validation_rules.csv`
```csv
rule_name,rule_type,target_value,tolerance,enforcement_level
monthly_distribution_sum,sum_validation,1.0,0.001,error
monthly_variance_tolerance,variance_validation,0.02,0.01,warning
minimum_month_percentage,minimum_validation,0.01,0.005,warning
maximum_month_percentage,maximum_validation,0.35,0.05,warning
```

### 3. Migration Strategy Design

#### 3.1 Phased Implementation Approach
```yaml
migration_phases:
  phase_1_design: "S056 - Design and specification"
  phase_2_implementation: "S057 - Code implementation with dual mode"
  phase_3_validation: "S058 - Testing and validation"
  phase_4_rollout: "S059 - Default switch to realistic timing"
```

#### 3.2 Backward Compatibility Framework
```sql
-- Configuration-controlled implementation
{% set timing_method = var('raise_timing_methodology', 'legacy') %}

{% if timing_method == 'legacy' %}
  -- Maintain exact current behavior for regression testing
  {{ legacy_50_50_split_logic() }}
{% elif timing_method == 'realistic' %}
  -- New realistic distribution
  {{ realistic_distribution_logic() }}
{% elif timing_method == 'custom' %}
  -- Future: custom distribution patterns
  {{ custom_distribution_logic() }}
{% endif %}
```

### 4. Performance Impact Analysis

#### 4.1 Computational Complexity
- **Current Logic**: O(1) - Simple modulo calculation
- **New Logic**: O(log n) - Hash calculation + cumulative lookup
- **Impact Estimate**: <2% runtime increase for timing calculation

#### 4.2 Memory Usage Analysis
- **Additional Seed Tables**: ~1KB for distribution configuration
- **Hash Calculations**: Minimal memory overhead
- **DuckDB Impact**: No change to serialization patterns

#### 4.3 Database Impact
- **Additional Queries**: One join to timing distribution table
- **Index Requirements**: None (small seed table)
- **Connection Management**: No changes to existing patterns

## Validation Strategy Design

### 1. Distribution Accuracy Validation
```sql
-- Monthly distribution validation test
WITH actual_distribution AS (
  SELECT
    EXTRACT(month FROM effective_date) as month,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as actual_percentage
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'RAISE'
    AND simulation_year = {{ var('simulation_year') }}
  GROUP BY month
),
expected_distribution AS (
  SELECT month, percentage * 100 as expected_percentage
  FROM {{ ref('config_raise_timing_distribution') }}
  WHERE industry_profile = {{ var('distribution_profile', 'general_corporate') }}
)
SELECT
  a.month,
  a.actual_percentage,
  e.expected_percentage,
  ABS(a.actual_percentage - e.expected_percentage) as variance,
  CASE
    WHEN ABS(a.actual_percentage - e.expected_percentage) > {{ var('timing_tolerance', 2.0) }}
    THEN 'FAIL'
    ELSE 'PASS'
  END as test_result
FROM actual_distribution a
JOIN expected_distribution e ON a.month = e.month
```

### 2. Deterministic Behavior Validation
```sql
-- Reproducibility test with same random seed
WITH simulation_run_1 AS (
  SELECT employee_id, effective_date as date_run_1
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'RAISE' AND simulation_year = 2025
),
simulation_run_2 AS (
  -- Re-run with same seed, should get identical results
  SELECT employee_id, effective_date as date_run_2
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'RAISE' AND simulation_year = 2025
)
SELECT COUNT(*) as mismatched_dates
FROM simulation_run_1 r1
JOIN simulation_run_2 r2 ON r1.employee_id = r2.employee_id
WHERE r1.date_run_1 != r2.date_run_2
-- Expected: 0 mismatched dates
```

## Implementation Files Design

### 1. Core Implementation Files
```
dbt/macros/get_realistic_raise_date.sql          # Main timing macro
dbt/macros/realistic_timing_calculation.sql      # Distribution algorithm
dbt/macros/legacy_timing_calculation.sql         # Backward compatibility
dbt/seeds/config_raise_timing_distribution.csv   # Monthly percentages
dbt/seeds/config_timing_validation_rules.csv     # Validation parameters
```

### 2. Configuration Files
```
config/simulation_config.yaml                    # Methodology selection
dbt/dbt_project.yml                             # Variable definitions
```

### 3. Testing Files
```
tests/test_monthly_distribution_accuracy.sql     # Distribution validation
tests/test_deterministic_behavior.sql            # Reproducibility test
tests/test_backward_compatibility.sql            # Legacy mode validation
tests/test_configuration_validation.sql          # Config parameter tests
```

## Acceptance Criteria

### Technical Design Criteria
- [ ] Algorithm design supports realistic monthly distribution (28% Jan, 18% Apr, 23% July)
- [ ] Hash-based implementation follows promotion event pattern
- [ ] Configuration framework supports multiple timing methodologies
- [ ] Backward compatibility maintains identical results with same random seed
- [ ] Performance impact estimated at <5% of simulation runtime

### Documentation Criteria
- [ ] Complete technical specification with implementation details
- [ ] Configuration schema documented with examples
- [ ] Migration strategy defined with clear phases
- [ ] Validation approach specified with test cases
- [ ] Performance analysis completed with concrete estimates

### Stakeholder Review Criteria
- [ ] Engineering team peer review completed
- [ ] Analytics team approval of proposed timing patterns
- [ ] Business justification documented for all design decisions
- [ ] Implementation complexity assessed as feasible
- [ ] Risk mitigation strategies defined

## Risk Assessment

### Technical Risks
- **Medium**: Hash-based algorithm complexity could impact performance
- **Low**: DuckDB compatibility issues with new logic
- **Low**: Configuration validation complexity

### Business Risks
- **Low**: Stakeholder rejection of proposed timing patterns
- **Medium**: Need for industry-specific customization beyond scope
- **Low**: Audit concerns about changing established patterns

### Mitigation Strategies
- Maintain legacy mode as fallback option
- Implement comprehensive validation and testing suite
- Provide detailed business justification documentation
- Phase implementation with gradual rollout

## Dependencies

### Prerequisites
- S055 audit findings and business requirements (COMPLETE)
- Understanding of current event sourcing architecture
- Analytics team availability for pattern validation

### Blocks Next Stories
- **S057**: Implement realistic raise date generation logic (depends on this design)
- **S058**: Validate and test new timing system (needs S057 implementation)

## Definition of Done

- [ ] Complete technical design specification documented
- [ ] Algorithm design peer-reviewed and approved by engineering team
- [ ] Configuration schema defined and validated
- [ ] Migration strategy approved by Analytics Team
- [ ] Performance impact analysis completed with concrete estimates
- [ ] Validation strategy defined with comprehensive test cases
- [ ] Risk assessment and mitigation strategies documented
- [ ] Stakeholder sign-off received for proposed approach
- [ ] S057 implementation ready to begin

---

**Story Owner**: Engineering Team
**Technical Review**: In Progress
**Business Sponsor**: Analytics Team
**Design Status**: READY FOR IMPLEMENTATION DESIGN
