# E023 Enrollment Engine Refinements Draft

**Status**: Draft Reference Document
**Purpose**: Capture comprehensive agent feedback and refinement suggestions for selective adoption
**Created**: 2025-07-31

This document consolidates feedback from 4 specialized agents plus ChatGPT o3 suggestions for refining the E023 Enrollment Engine MVP. Use this as a reference to selectively adopt improvements rather than wholesale changes.

---

## Executive Summary

### Key Findings from Agent Analysis
- **Workforce Simulation**: Current demographic segmentation oversimplified; missing tenure-based patterns
- **Cost Modeling**: Events lack financial attribution; need employer match calculations and IRS limit enforcement
- **Orchestration**: Should integrate into orchestrator_mvp Step 4 rather than separate processing
- **DuckDB Performance**: Hash-based random generation inefficient; need vectorized operations for <10s target

### Existing Strengths to Preserve
✅ Your `config/test_config.yaml` structure is solid - build on it
✅ Your data schema (`employee_deferral_rate`, `employee_contribution`, `employer_match_contribution`) is well-designed
✅ Event sourcing architecture aligns with existing patterns
✅ 16-point MVP scope is appropriate

---

## Agent Feedback Details

### 1. Workforce Simulation Specialist Feedback

#### Critical Issues Identified
- **Oversimplified Demographics**: 3-tier age segmentation misses behavioral nuances
- **Missing Tenure Patterns**: No distinction between new hires vs. existing employees
- **No Life Event Context**: Marriage, children drive 40% of enrollment changes
- **Missing Peer Influence**: Department/team enrollment rates affect individual decisions

#### Recommended Improvements
```sql
-- Enhanced demographic matrix
SELECT
  CASE
    WHEN tenure_years < 2 THEN 'new_employee'
    WHEN tenure_years < 10 AND current_age < 35 THEN 'young_career_builder'
    WHEN tenure_years >= 10 AND current_age BETWEEN 35 AND 50 THEN 'mid_career_established'
    WHEN current_age > 50 THEN 'pre_retirement'
    ELSE 'career_transitioner'
  END as enrollment_segment
```

#### MVP vs. Future Enhancements
**MVP**: Add tenure-based segmentation (new hire vs. existing employee)
**Future**: Life event triggers, peer influence modeling, economic sensitivity factors

### 2. Cost Modeling Architect Feedback

#### Critical Architecture Gaps
- **Missing Cost Attribution**: Events don't capture financial impact
- **No Match Calculations**: Employer match costs not tracked
- **Missing IRS Compliance**: 402(g)/415(c) limits not enforced in events
- **No Scenario Cost Tracking**: Can't compare financial impact across scenarios

#### Enhanced Event Payload Recommendation
```sql
-- Enhanced enrollment event with cost attribution
json_object(
    'event_type', 'enrollment',
    'plan_id', plan_id,
    'enrollment_date', enrollment_date,
    'deferral_rate', deferral_rate,

    -- ENHANCED: Cost Attribution Fields
    'annual_compensation', annual_compensation,
    'projected_employee_contribution_annual', annual_compensation * deferral_rate,
    'projected_employer_match_annual', LEAST(
        annual_compensation * deferral_rate * {{ var('match_percentage') }},
        annual_compensation * {{ var('max_match_percentage') }}
    ),
    'cost_center', cost_center,
    'match_formula_code', {{ var('match_formula_code') }},

    -- ENHANCED: IRS Compliance
    'irs_limit_monitoring_required', annual_compensation >= {{ var('hce_threshold') }},
    'contribution_within_402g_limit', deferral_rate * annual_compensation <= {{ var('irs_402g_limit') }}
) as payload
```

#### Recommended New Models
- `int_enrollment_cost_attribution.sql` - Financial impact calculations
- `int_enrollment_bucket_split.sql` - IRS limit enforcement and tax allocation

### 3. Orchestration Engineer Feedback

#### Integration Issues
- **Missing Integration Point**: E023 not integrated into orchestrator_mvp workflow
- **Duplicate Processing**: E022 and E023 both process same 100K employees separately
- **No Asset Dependencies**: Missing Dagster asset chain eligibility → enrollment
- **Missing Monitoring**: No enrollment-specific validation or circuit breakers

#### Recommended Integration Pattern
```python
# Enhanced Step 4: Event Generation with Enrollment
def _execute_event_generation(self, year: int) -> None:
    """Enhanced event generation including enrollment processing."""
    try:
        # 4a. Standard workforce events (existing)
        calc_result = self.results['step_details'][year]['calc_result']
        generate_and_store_all_events(calc_result, year, random_seed, self.config)

        # 4b. NEW: Enrollment event processing (E023 integration)
        enrollment_results = self._process_enrollment_events(year)
        self.results['step_details'][year]['enrollment_results'] = enrollment_results

    except Exception as e:
        logger.error(f"❌ Event generation (with enrollment) failed: {str(e)}")
        raise
```

#### Performance Optimization
- **Combined Processing**: Single SQL operation for both eligibility and enrollment
- **Asset Dependencies**: Proper Dagster asset chain
- **Circuit Breakers**: Prevent enrollment failures from cascading

### 4. DuckDB/dbt Optimizer Feedback

#### Critical Performance Issues
- **Inefficient Random Generation**: Hash-based approach prevents vectorization
- **Multiple Sequential CTEs**: Causes memory pressure and prevents optimization
- **String-Based Demographics**: Inefficient compared to integer segments

#### Optimized SQL Structure
```sql
WITH eligible_population_optimized AS (
    SELECT
        employee_id,
        current_age,
        current_compensation,

        -- Vectorized demographic segmentation using CASE expressions
        CASE WHEN current_age <= 25 THEN 1
             WHEN current_age <= 35 THEN 2
             WHEN current_age <= 50 THEN 3
             ELSE 4 END AS age_segment_id,

        -- Deterministic but DuckDB-optimized random using row_number
        (ROW_NUMBER() OVER (ORDER BY employee_id) * 2654435761 + {{ var('enrollment_seed') }}) % 1000000 / 1000000.0 as random_draw

    FROM {{ ref('int_eligibility_determination') }}
    WHERE is_eligible = true
)
```

#### Expected Performance Improvements
| Optimization | Current Time | Optimized Time | Improvement |
|-------------|-------------|----------------|------------|
| Demographic Segmentation | ~3 seconds | ~0.5 seconds | 6x faster |
| Random Generation | ~4 seconds | ~0.8 seconds | 5x faster |
| **Total Pipeline** | **~9 seconds** | **~1.6 seconds** | **5.6x faster** |

---

## ChatGPT o3 Suggestions

### Configuration Refinements
**Issue**: Current approach scatters variables in `dbt_project.yml`
**Suggestion**: Use dedicated configuration structure in `config/test_config.yaml`

```yaml
# Add to existing config/test_config.yaml
enrollment:
  auto_enrollment_enabled: true
  default_deferral_rate: 0.06
  opt_out_window_days: 90

  # Match optimization
  match_percentage: 1.0  # 100% match on deferrals
  max_match_percentage: 0.05  # Up to 5% of compensation

  # Proactive enrollment distribution
  deferral_distribution:
    match_max_rate: 0.05
    buckets:
      - rate: 0.05
        probability: 0.50  # 50% choose match-max
      - rate: 0.06
        probability: 0.25
      - rate: 0.04
        probability: 0.15
      - rate: 0.03
        probability: 0.10

# IRS Limits (build on existing structure)
irs_limits_2025:
  elective_402g: 23000      # 2025 402(g) limit
  overall_415c: 70000       # 2025 415(c) limit
  catch_up_limit: 7500      # 2025 catch-up limit
  hce_threshold: 155000     # 2025 HCE threshold
```

### Match-Max Optimizer
**Issue**: No employer match calculation in current approach
**Suggestion**: Proactive joiners should evaluate employer match formula

```sql
-- Match optimization logic
CASE
    WHEN enrollment_type = 'proactive' THEN
        LEAST(
            {{ var('max_match_percentage') }}, -- e.g., 5%
            calculated_optimal_rate
        )
    ELSE {{ var('default_deferral_rate') }}
END as final_deferral_rate
```

### Bucket Allocation Model
**Issue**: No separate model for IRS limit enforcement
**Suggestion**: Create `int_enrollment_bucket_split.sql` for tax allocation and limit validation

---

## Selective Implementation Suggestions

### Phase 1: Quick Wins (1-2 days)
1. **Add IRS Limits to Config**: Extend `config/test_config.yaml` with 402(g)/415(c) limits
2. **Tenure-Based Segmentation**: Add new hire vs. existing employee distinction
3. **Enhanced Event Payloads**: Add employer match calculation to enrollment events

### Phase 2: Performance Optimization (3-4 days)
1. **Optimize Random Generation**: Replace hash-based with linear congruential generator
2. **Vectorized Demographics**: Use integer segment IDs instead of strings
3. **Memory Configuration**: Add DuckDB settings for 100K employee processing

### Phase 3: Architecture Integration (1 week)
1. **Orchestrator Integration**: Add enrollment to orchestrator_mvp Step 4
2. **Cost Attribution Model**: Create `int_enrollment_cost_attribution.sql`
3. **Asset Dependencies**: Proper Dagster asset chain

### Phase 4: Advanced Features (Future)
1. **Life Event Integration**: Marriage, children impact on enrollment
2. **Peer Influence Modeling**: Department-level enrollment rate effects
3. **Economic Sensitivity**: Market conditions affecting retirement savings behavior

---

## Python Utility Suggestions

### enrollment_utils.py
```python
from decimal import Decimal
from typing import Dict, Any

def pick_default_deferral_rate(employee_segment: str, config: Dict) -> Decimal:
    """Select appropriate default deferral rate based on employee segment."""
    segment_rates = config.get('deferral_distribution', {})
    return Decimal(str(segment_rates.get('default_rate', 0.06)))

def calculate_employer_match(
    employee_contribution: Decimal,
    annual_compensation: Decimal,
    config: Dict
) -> Decimal:
    """Calculate employer match based on plan formula."""
    match_pct = Decimal(str(config.get('match_percentage', 1.0)))
    max_match_pct = Decimal(str(config.get('max_match_percentage', 0.05)))

    # Standard match formula: 100% of first X% of compensation
    max_match_amount = annual_compensation * max_match_pct
    potential_match = employee_contribution * match_pct

    return min(potential_match, max_match_amount)

def validate_irs_limits(
    contribution: Decimal,
    compensation: Decimal,
    employee_age: int,
    config: Dict
) -> Dict[str, Any]:
    """Validate contribution against IRS limits."""
    limits = config.get('irs_limits_2025', {})

    # 402(g) limit
    elective_limit = Decimal(str(limits.get('elective_402g', 23000)))
    if employee_age >= 50:
        elective_limit += Decimal(str(limits.get('catch_up_limit', 7500)))

    return {
        'within_402g_limit': contribution <= elective_limit,
        'within_415c_limit': contribution <= compensation * Decimal('1.0'),  # Simplified
        'max_allowed_contribution': min(elective_limit, compensation),
        'excess_contribution': max(Decimal('0'), contribution - elective_limit)
    }
```

---

## Testing Framework Enhancements

### Unit Tests for IRS Limit Enforcement
```python
def test_irs_limit_validation():
    """Test 402(g) and 415(c) limit enforcement."""
    config = {'irs_limits_2025': {'elective_402g': 23000, 'catch_up_limit': 7500}}

    # Test under-50 employee
    result = validate_irs_limits(
        contribution=Decimal('20000'),
        compensation=Decimal('100000'),
        employee_age=35,
        config=config
    )
    assert result['within_402g_limit'] == True

    # Test over-50 employee with catch-up
    result = validate_irs_limits(
        contribution=Decimal('25000'),
        compensation=Decimal('150000'),
        employee_age=55,
        config=config
    )
    assert result['within_402g_limit'] == True  # 23000 + 7500 catch-up
```

### Performance Tests
```python
def test_deferral_distribution_accuracy():
    """Chi-square test for deferral rate distribution drift."""
    # Generate 10,000 enrollment decisions
    results = []
    for i in range(10000):
        rate = pick_proactive_deferral_rate('mid_career', test_config)
        results.append(rate)

    # Verify distribution matches expected probabilities
    from scipy.stats import chisquare
    observed = [results.count(r) for r in [0.03, 0.04, 0.05, 0.06]]
    expected = [1000, 1500, 5000, 2500]  # Based on config probabilities

    chi2, p_value = chisquare(observed, expected)
    assert p_value > 0.05, f"Distribution drift detected: p={p_value}"
```

---

## Data Quality Validations

### Enrollment Rate Validation
```sql
-- dbt test: enrollment_rate_reasonable
SELECT COUNT(*) as violations
FROM {{ ref('int_enrollment_determination') }}
WHERE (
    -- Total enrollment rate should be 20-80%
    (SELECT AVG(CASE WHEN enrolled THEN 1.0 ELSE 0.0 END)
     FROM {{ this }}) NOT BETWEEN 0.20 AND 0.80
)
```

### Cost Attribution Validation
```sql
-- dbt test: employer_match_calculation_accurate
SELECT COUNT(*) as violations
FROM {{ ref('int_enrollment_cost_attribution') }}
WHERE ABS(
    projected_employer_match_annual -
    LEAST(
        projected_employee_contribution_annual * {{ var('match_percentage') }},
        annual_compensation * {{ var('max_match_percentage') }}
    )
) > 0.01  -- Allow 1 cent rounding difference
```

---

## Integration Patterns

### Dagster Asset Structure
```python
@asset(
    deps=["int_eligibility_determination"],  # E022 output
    description="E023: Process enrollment decisions for eligible employees"
)
def enrollment_determination_model(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> pd.DataFrame:
    """Run enrollment determination dbt model with eligibility input."""
    with duckdb.get_connection() as conn:
        conn.execute("CALL dbt_run_model('int_enrollment_determination')")
        return conn.execute("SELECT * FROM int_enrollment_determination").df()

@asset(
    ins={"enrollment_data": AssetIn("enrollment_determination_model")},
    description="E023: Generate enrollment events for event sourcing"
)
def enrollment_events_generated(
    context: AssetExecutionContext,
    enrollment_data: pd.DataFrame,
    duckdb: DuckDBResource
) -> Dict[str, Any]:
    """Generate enrollment and opt-out events."""
    # Event generation logic using existing field structure
    return {
        'total_enrolled': len(enrollment_data[enrollment_data['enrolled']]),
        'avg_deferral_rate': enrollment_data['employee_deferral_rate'].mean(),
        'total_employer_match_cost': enrollment_data['employer_match_contribution'].sum()
    }
```

---

## Conclusion

This draft consolidates comprehensive feedback from domain experts while respecting your existing architecture and data schema. The suggestions are organized by priority and complexity, allowing selective adoption based on your specific needs and timeline.

**Key Takeaways**:
- Your existing schema and config structure are solid - build on them
- Focus on performance optimizations and orchestration integration first
- Cost attribution and IRS limit enforcement provide high business value
- Advanced behavioral modeling can be deferred to future phases

**Next Steps**:
1. Review suggestions and identify high-value, low-effort improvements
2. Prioritize based on MVP timeline and business impact
3. Consider creating separate implementation stories for major enhancements
4. Use this as input for E024 advanced features planning
