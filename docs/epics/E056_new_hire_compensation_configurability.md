# Epic E056: New Hire Compensation Configurability Enhancement

**Status**: 🟡 In Progress
**Priority**: High
**Estimated Effort**: 5-8 days
**GitHub Issue**: #27
**Feature Branch**: `feature/E056-new-hire-compensation-configurability`

## Executive Summary

Transform new hire compensation from a hardcoded midpoint calculation to a fully configurable system that enables analysts to quickly model different hiring strategies and their financial impact. This enhancement addresses the current limitation where new hires are always set at the 50th percentile of job level compensation ranges, providing no flexibility for conservative vs. aggressive hiring scenarios.

## Problem Statement

### Current System Limitations

The existing new hire compensation system has several critical constraints:

1. **Hardcoded Midpoint Calculation**: All new hires receive compensation at exactly 50% between min/max of their job level
2. **Limited Configurability**: Only a single 3% adjustment parameter in `comp_levers.csv`
3. **No Percentile Selection**: Cannot hire at 25th, 75th, or other percentiles
4. **Inflexible Market Adjustments**: No way to adjust for market conditions or hiring strategies
5. **Inconsistent Implementation**: Two separate models with potential logic drift

### Current Financial Impact Example

**Level 3 Manager Example:**
- Current Range: $121,000 - $160,000
- Current Midpoint: $140,500
- With 3% Adjustment: ~$145,000
- **Conservative Alternative (25th percentile)**: ~$131,000 (**$14k savings per hire**)
- **Aggressive Alternative (75th percentile)**: ~$151,000 (**$6k premium per hire**)

### Business Impact

- **No Strategic Flexibility**: Cannot model conservative vs. aggressive hiring strategies
- **Budget Planning Limitations**: Scenarios are limited to single compensation approach
- **Market Response**: Cannot quickly adjust to competitive market conditions
- **Cost Optimization**: Missing ~$11k-14k savings opportunity per hire with conservative strategy

## Solution Architecture

### 1. Configurable Compensation Strategy Framework

Create a comprehensive configuration system in `simulation_config.yaml`:

```yaml
# New hire compensation configuration
new_hire_compensation:
  # Global strategy selection
  strategy: "percentile_based"  # Options: percentile_based, custom_distribution, market_adjusted

  # Percentile-based hiring
  percentile_strategy:
    default_percentile: 0.50    # 50th percentile (current behavior)
    level_overrides:
      1: 0.40                   # Level 1: 40th percentile (conservative)
      2: 0.50                   # Level 2: 50th percentile
      3: 0.60                   # Level 3: 60th percentile (competitive)
      4: 0.75                   # Level 4: 75th percentile (aggressive)
      5: 0.80                   # Level 5: 80th percentile (executive)

    # Distribution around percentile (adds realism)
    variance_enabled: true
    variance_std_dev: 0.05      # 5% standard deviation around target percentile

  # Market adjustment multipliers
  market_adjustments:
    enabled: true
    base_adjustment: 1.00       # No adjustment by default
    level_adjustments:
      1: 1.02                   # 2% market premium for entry level
      2: 1.00                   # No adjustment for managers
      3: 0.98                   # 2% discount for senior managers
      4: 1.05                   # 5% premium for directors
      5: 1.10                   # 10% premium for VPs

    # Scenario-based adjustments (for quick modeling)
    scenarios:
      conservative: 0.92        # 8% reduction for budget constraints
      competitive: 1.05         # 5% increase for competitive markets
      aggressive: 1.15          # 15% increase for talent war scenarios

  # Custom distribution options (future enhancement)
  custom_distribution:
    enabled: false
    distribution_type: "beta"   # Options: normal, beta, uniform
    parameters:
      alpha: 2.0
      beta: 5.0
      min_percentile: 0.25
      max_percentile: 0.85
```

### 2. Enhanced Parameter Integration

Extend `comp_levers.csv` with new compensation parameters:

```csv
scenario_id,fiscal_year,job_level,event_type,parameter_name,parameter_value
default,2025,1,HIRE,compensation_percentile,0.40
default,2025,2,HIRE,compensation_percentile,0.50
default,2025,3,HIRE,compensation_percentile,0.60
default,2025,1,HIRE,market_adjustment_multiplier,1.02
default,2025,2,HIRE,market_adjustment_multiplier,1.00
default,2025,3,HIRE,market_adjustment_multiplier,0.98
```

### 3. Unified Compensation Logic

Replace hardcoded midpoint calculations with configurable percentile logic:

```sql
-- New configurable approach
new_hire_compensation AS (
  SELECT
    level_id,
    min_compensation +
    (max_compensation - min_compensation) *
    {{ get_parameter_value('level_id', 'HIRE', 'compensation_percentile', simulation_year, 0.50) }} *
    {{ get_parameter_value('level_id', 'HIRE', 'market_adjustment_multiplier', simulation_year, 1.00) }}
    AS target_compensation
  FROM {{ ref('stg_config_job_levels') }}
)
```

### 4. Streamlit UI Enhancement

Add real-time compensation modeling to the analyst dashboard:

- **Percentile Sliders**: Adjust compensation percentiles by level in real-time
- **Market Scenario Toggle**: Switch between conservative/competitive/aggressive modes
- **Impact Calculator**: Instant cost impact analysis per scenario
- **Side-by-side Comparison**: Compare multiple scenarios simultaneously

## Implementation Plan

### Phase 1: Configuration Foundation (2 days)
- [ ] Add `new_hire_compensation` section to `simulation_config.yaml`
- [ ] Create compensation parameter resolution macro
- [ ] Add new parameters to `comp_levers.csv` seed
- [ ] Update parameter loading logic

### Phase 2: Model Integration (2 days)
- [ ] Update `int_workforce_needs_by_level.sql` with configurable percentile logic
- [ ] Refactor `int_new_hire_compensation_staging.sql` for consistency
- [ ] Update `int_hiring_events.sql` to use unified compensation source
- [ ] Remove hardcoded midpoint calculations

### Phase 3: Validation & Testing (2 days)
- [ ] Create data quality validation for compensation ranges
- [ ] Add unit tests for percentile calculation logic
- [ ] Test scenarios: 25th, 50th, 75th percentile configurations
- [ ] Validate financial impact calculations

### Phase 4: UI Enhancement (2 days)
- [ ] Add compensation configurator to Streamlit dashboard
- [ ] Implement real-time scenario impact calculator
- [ ] Create side-by-side scenario comparison view
- [ ] Add parameter export functionality for analysts

## Detailed User Stories

### Story 1: Configurable Compensation Percentiles
**As an** analyst
**I want to** configure new hire compensation at different percentiles (25th, 50th, 75th)
**So that** I can model conservative vs. aggressive hiring strategies

**Acceptance Criteria:**
- [ ] Configuration in `simulation_config.yaml` allows percentile selection by job level
- [ ] 25th percentile results in ~10-15% lower compensation than current midpoint
- [ ] 75th percentile results in ~10-15% higher compensation than current midpoint
- [ ] Changes apply consistently across all hiring models

### Story 2: Market Adjustment Controls
**As an** analyst
**I want to** apply market adjustment multipliers to base compensation
**So that** I can quickly model responses to market conditions

**Acceptance Criteria:**
- [ ] Market adjustment multipliers configurable by job level
- [ ] Predefined scenarios: conservative (-8%), competitive (+5%), aggressive (+15%)
- [ ] Adjustments combine with percentile settings multiplicatively
- [ ] Changes trackable in audit trail

### Story 3: Real-time Impact Analysis
**As an** analyst
**I want to** see immediate financial impact of compensation changes
**So that** I can make informed budgeting decisions

**Acceptance Criteria:**
- [ ] Streamlit UI shows per-hire cost changes in real-time
- [ ] Total annual impact calculation for multi-year simulations
- [ ] Comparison view showing before/after scenarios
- [ ] Export capability for budget presentations

### Story 4: Unified Compensation Logic
**As a** developer
**I want to** eliminate duplicate compensation calculation logic
**So that** the system maintains consistency and is easier to maintain

**Acceptance Criteria:**
- [ ] Single source of truth for new hire compensation calculation
- [ ] `int_workforce_needs_by_level.sql` and `int_new_hire_compensation_staging.sql` use same logic
- [ ] No hardcoded midpoint calculations remaining
- [ ] Data quality tests validate consistency

### Story 5: Parameter Management Integration
**As an** analyst
**I want to** manage compensation parameters through existing tools
**So that** I can use familiar workflows and maintain audit trails

**Acceptance Criteria:**
- [ ] New compensation parameters in `comp_levers.csv`
- [ ] Parameters integrate with existing parameter resolution system
- [ ] Historical parameter changes tracked in seed file
- [ ] Parameter validation prevents invalid configurations

## Technical Implementation Details

### 1. Configuration Schema

```yaml
# config/simulation_config.yaml additions
new_hire_compensation:
  strategy: "percentile_based"
  default_percentile: 0.50
  level_percentiles:
    1: 0.40  # Conservative for entry level
    2: 0.50  # Baseline for managers
    3: 0.60  # Competitive for senior managers
    4: 0.75  # Aggressive for directors
    5: 0.80  # Premium for executives
  market_scenarios:
    conservative: 0.92
    baseline: 1.00
    competitive: 1.05
    aggressive: 1.15
  variance:
    enabled: true
    std_dev: 0.05
```

### 2. SQL Implementation Pattern

```sql
-- Configurable compensation calculation
WITH compensation_config AS (
  SELECT
    level_id,
    min_compensation,
    max_compensation,
    {{ get_parameter_value('level_id', 'HIRE', 'compensation_percentile') }} as percentile,
    {{ get_parameter_value('level_id', 'HIRE', 'market_adjustment') }} as market_adj
  FROM {{ ref('stg_config_job_levels') }}
),

calculated_compensation AS (
  SELECT
    level_id,
    min_compensation +
    (max_compensation - min_compensation) * percentile * market_adj as target_compensation,
    -- Add variance for realism
    target_compensation * (1 + {{ get_random_normal(0, 0.05) }}) as final_compensation
  FROM compensation_config
)
```

### 3. Streamlit UI Components

```python
# Compensation configurator section
st.subheader("New Hire Compensation Strategy")

# Percentile selection by level
percentiles = {}
for level in [1, 2, 3, 4, 5]:
    percentiles[level] = st.slider(
        f"Level {level} Compensation Percentile",
        min_value=0.25, max_value=0.90,
        value=current_percentiles.get(level, 0.50),
        step=0.05
    )

# Market scenario selector
scenario = st.selectbox(
    "Market Scenario",
    ["conservative", "baseline", "competitive", "aggressive"]
)

# Impact calculator
if st.button("Calculate Impact"):
    impact = calculate_compensation_impact(percentiles, scenario)
    st.metric("Annual Cost Change", f"${impact:,.0f}")
```

## Risk Assessment and Mitigation

### Technical Risks

1. **Configuration Complexity**: Complex YAML structure might be error-prone
   - **Mitigation**: Comprehensive validation and clear documentation
   - **Validation**: Schema validation on config load

2. **Model Performance**: Additional parameter lookups could slow queries
   - **Mitigation**: Cache parameter values, optimize lookup queries
   - **Monitoring**: Track query performance before/after changes

3. **Backward Compatibility**: Changes might affect existing simulations
   - **Mitigation**: Default configuration maintains current behavior
   - **Testing**: Regression tests validate unchanged results with defaults

### Business Risks

1. **Misconfiguration Impact**: Wrong parameters could skew entire simulation
   - **Mitigation**: Parameter validation and reasonable bounds checking
   - **Safeguards**: Warning alerts for extreme configurations

2. **Change Management**: Analysts might resist new complexity
   - **Mitigation**: Comprehensive training and gradual rollout
   - **Support**: Clear documentation and example scenarios

### Data Quality Risks

1. **Parameter Inconsistency**: Different parameters across models
   - **Mitigation**: Single source of truth pattern and automated tests
   - **Monitoring**: Data quality checks for parameter consistency

2. **Unrealistic Combinations**: Invalid percentile/market adjustment combinations
   - **Mitigation**: Business rule validation in configuration loading
   - **Alerts**: Warning system for unusual parameter combinations

## Success Metrics

### Before Implementation (Baseline)
- **Configuration Options**: 1 (hardcoded midpoint)
- **Parameter Flexibility**: 1 adjustment multiplier (3%)
- **Scenario Modeling Time**: 30+ minutes (requires code changes)
- **Cost per Level 3 Hire**: ~$145,000

### After Implementation (Targets)
- **Configuration Options**: 5+ percentile options plus market scenarios
- **Parameter Flexibility**: 10+ configurable parameters
- **Scenario Modeling Time**: <2 minutes (UI-based)
- **Cost Flexibility**: $131k-$151k range for Level 3 (±$14k flexibility)

### Financial Impact Opportunities
- **Conservative Strategy**: $11k-14k savings per hire
- **Competitive Strategy**: $6k-8k premium per hire for talent acquisition
- **Market Responsiveness**: <24 hour turnaround for compensation strategy changes
- **Budget Accuracy**: ±2% accuracy in workforce cost projections

## Business Value Proposition

### Immediate Benefits
1. **Cost Optimization**: $11k+ savings per hire with conservative strategy
2. **Strategic Flexibility**: Model multiple hiring approaches in minutes
3. **Market Responsiveness**: Quickly adjust to competitive pressures
4. **Budget Accuracy**: More precise workforce cost projections

### Long-term Benefits
1. **Competitive Advantage**: Dynamic compensation strategy vs. static competitors
2. **Risk Management**: Model various economic scenarios
3. **Talent Strategy**: Optimize compensation for different talent markets
4. **Process Efficiency**: Eliminate manual compensation calculations

### ROI Analysis
- **Implementation Cost**: ~40 development hours ($8,000)
- **Per-hire Savings**: $11,000 (conservative strategy)
- **Break-even**: 1 hire using conservative strategy
- **Annual Value**: $500k+ (assuming 50 hires/year with 50% conservative strategy)

## Dependencies and Integration Points

### Upstream Dependencies
- `config/simulation_config.yaml` - Configuration loading system
- `dbt/seeds/comp_levers.csv` - Parameter management system
- `stg_config_job_levels` - Job level compensation ranges

### Downstream Impact
- `int_workforce_needs_by_level.sql` - Primary beneficiary
- `int_new_hire_compensation_staging.sql` - Alignment required
- `int_hiring_events.sql` - Compensation source consistency
- `fct_yearly_events.sql` - Audit trail for compensation decisions

### External Integration
- **Streamlit Dashboard**: Real-time parameter adjustment UI
- **Navigator Orchestrator**: Configuration loading and validation
- **Reporting System**: Financial impact analysis and audit trails

## Testing Strategy

### Unit Tests
```sql
-- Test percentile calculation accuracy
SELECT
  level_id,
  percentile_25,
  percentile_50,
  percentile_75
FROM test_percentile_calculations()
WHERE ABS(percentile_50 - expected_midpoint) > 100
```

### Integration Tests
- Full simulation run comparing old vs. new logic with default parameters
- Multi-scenario testing: conservative, baseline, aggressive configurations
- Parameter validation testing with invalid inputs

### Regression Tests
- Verify default configuration produces identical results to current system
- Performance benchmarks for parameter lookup operations
- Data quality validation across all affected models

## Documentation and Training

### Technical Documentation
- [ ] Update CLAUDE.md with new hire compensation patterns
- [ ] dbt model documentation with configuration examples
- [ ] Parameter reference guide with business impact analysis
- [ ] Troubleshooting guide for common configuration issues

### User Documentation
- [ ] Analyst guide for compensation strategy configuration
- [ ] Streamlit UI user manual with scenario examples
- [ ] Best practices guide for parameter selection
- [ ] Financial impact analysis examples

### Training Materials
- [ ] Configuration workshop for analysts
- [ ] Video tutorials for UI usage
- [ ] Scenario modeling exercises
- [ ] Q&A session documentation

## Future Enhancements

### Phase 2 Opportunities
1. **Advanced Distribution Models**: Beta, gamma, or custom distributions
2. **Geographic Adjustments**: Location-based compensation multipliers
3. **Experience Premiums**: Compensation adjustments based on candidate experience
4. **Industry Benchmarking**: External market data integration

### Integration Opportunities
1. **HR Information System**: Direct integration with HRIS for real-time ranges
2. **Market Data Feeds**: Automated salary survey data integration
3. **Machine Learning**: Predictive compensation optimization
4. **Budget Integration**: Direct connection to financial planning systems

---

**Epic Owner**: Claude Code
**Created**: 2025-01-27
**Last Updated**: 2025-01-27
**Related Issues**: #27 (New hire compensation configurability)
**Feature Branch**: `feature/E056-new-hire-compensation-configurability`
