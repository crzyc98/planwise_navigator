# Event Generation Models - Core Workforce Events

## Purpose

The event generation models in `dbt/models/intermediate/events/` represent the core business logic of PlanWise Navigator, implementing sophisticated algorithms to generate realistic workforce events (hiring, promotions, terminations, merit raises) based on probabilistic models and business constraints.

## Architecture

These models implement a sophisticated event-driven workforce simulation using:
- **Hazard-based Probability Models**: Statistical risk calculations for event likelihood
- **Business Rule Enforcement**: Organizational constraints and policy compliance
- **Temporal Sequencing**: Proper event timing and dependencies
- **Budget Constraints**: Financial limits on compensation changes

## Key Event Models

### 1. int_hiring_events.sql - New Hire Generation

**Purpose**: Generate new hire events to achieve growth targets and replace departing employees.

**Core Logic**:
```sql
-- Calculate total hiring need
hiring_need AS (
  SELECT 
    target_growth_hires + replacement_hires + strategic_hires AS total_need,
    LEAST(total_need, budget_constraint, capacity_constraint) AS actual_hires
  FROM workforce_planning
),

-- Generate individual hire events
hire_events AS (
  SELECT
    'H' || ROW_NUMBER() OVER (ORDER BY RANDOM()) AS employee_id,
    'hire' AS event_type,
    simulation_year,
    hire_level,
    starting_salary,
    hire_date
  FROM generate_series(1, actual_hires)
)
```

**Key Features**:
- Growth-driven hiring calculations
- Replacement need assessment
- Realistic salary assignment by level
- Seasonal hiring patterns
- Budget and capacity constraints

### 2. int_promotion_events.sql - Career Advancement

**Purpose**: Generate promotion events using hazard-based probability calculations with organizational constraints.

**Core Logic**:
```sql
-- Identify promotion-eligible employees
eligible_employees AS (
  SELECT 
    employee_id,
    current_level,
    tenure_months,
    performance_rating,
    promotion_probability
  FROM current_workforce w
  JOIN hazard_promotion h ON w.level = h.level
  WHERE tenure_months >= minimum_tenure
    AND current_level < 5  -- Max level constraint
),

-- Apply probabilistic selection
promotion_events AS (
  SELECT
    employee_id,
    'promotion' AS event_type,
    current_level AS from_level,
    current_level + 1 AS to_level,
    new_salary,
    effective_date
  FROM eligible_employees
  WHERE RANDOM() < promotion_probability
    AND employee_id IN (
      SELECT employee_id 
      FROM eligible_employees 
      ORDER BY promotion_probability DESC
      LIMIT promotion_budget_slots
    )
)
```

**Key Features**:
- Tenure-based eligibility
- Performance-weighted probabilities
- Level progression caps
- Budget-constrained selection
- Realistic promotion timing

### 3. int_termination_events.sql - Employee Departures

**Purpose**: Generate termination events based on configurable turnover rates and risk factors.

**Core Logic**:
```sql
-- Calculate termination probabilities by employee segment
termination_risk AS (
  SELECT
    employee_id,
    base_termination_rate * age_multiplier * tenure_multiplier * performance_multiplier AS termination_probability,
    CASE 
      WHEN tenure_months <= 12 THEN new_hire_termination_rate
      ELSE total_termination_rate
    END AS applicable_rate
  FROM current_workforce w
  JOIN hazard_termination h ON w.age_band = h.age_band AND w.tenure_band = h.tenure_band
),

-- Generate termination events
termination_events AS (
  SELECT
    employee_id,
    'termination' AS event_type,
    CASE 
      WHEN RANDOM() < 0.7 THEN 'voluntary'
      ELSE 'involuntary'
    END AS termination_reason,
    effective_date,
    replacement_needed
  FROM termination_risk
  WHERE RANDOM() < termination_probability
)
```

**Key Features**:
- Differentiated new hire vs. tenured employee rates
- Age and tenure risk adjustments
- Performance-based modifications
- Voluntary vs. involuntary classification
- Replacement flagging for hiring needs

### 4. int_merit_events.sql - Performance-Based Raises

**Purpose**: Generate merit raise events based on performance ratings and budget allocation.

**Core Logic**:
```sql
-- Calculate merit eligibility and budget allocation
merit_pool AS (
  SELECT
    SUM(current_salary) * merit_budget_percentage AS total_merit_budget,
    COUNT(*) AS eligible_employees
  FROM current_workforce
  WHERE performance_rating >= merit_threshold
),

-- Distribute merit increases
merit_events AS (
  SELECT
    employee_id,
    'merit_raise' AS event_type,
    current_salary,
    CASE performance_rating
      WHEN 'exceptional' THEN GREATEST(current_salary * 0.08, individual_budget_allocation)
      WHEN 'exceeds' THEN GREATEST(current_salary * 0.05, individual_budget_allocation * 0.8)
      WHEN 'meets' THEN GREATEST(current_salary * 0.03, individual_budget_allocation * 0.6)
    END AS merit_increase,
    effective_date
  FROM current_workforce w
  JOIN merit_pool p ON 1=1
  WHERE performance_rating IN ('exceptional', 'exceeds', 'meets')
)
```

**Key Features**:
- Budget-constrained merit distribution
- Performance-based raise calculations
- Minimum increase guarantees
- Anniversary date timing
- Equity considerations

## Advanced Features

### Hazard Model Integration
Each event model integrates with sophisticated hazard tables that calculate probabilities based on:
- **Demographics**: Age, tenure, level combinations
- **Performance**: Rating-based adjustments
- **Market Conditions**: Economic and industry factors
- **Organizational Factors**: Department, location, role type

### Temporal Dependencies
Events are generated with proper sequencing:
- Terminations occur before hiring calculations
- Promotions precede merit raise eligibility
- Seasonal patterns affect event timing
- Anniversary dates drive individual event timing

### Business Rule Enforcement
- **Budget Constraints**: Financial limits on compensation changes
- **Organizational Limits**: Span of control and level caps
- **Policy Compliance**: HR policy and regulatory requirements
- **Data Quality**: Referential integrity and business logic validation

## Configuration Integration

### Key Parameters
```yaml
# Event generation rates
workforce:
  target_growth_rate: 0.03
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

# Promotion controls
promotion:
  base_rate: 0.15
  level_caps: {1: 0.20, 2: 0.15, 3: 0.10, 4: 0.05}
  minimum_tenure_months: {1: 12, 2: 18, 3: 24, 4: 36}

# Merit budget
compensation:
  merit_budget: 0.04
  promotion_increase: 0.15
```

## Common Issues

### Inconsistent Growth Rates
**Problem**: Actual growth doesn't match targets
**Solution**: Balance hiring, termination, and backfill rates

### Unrealistic Event Patterns
**Problem**: Events don't follow realistic timing patterns
**Solution**: Implement proper seasonality and anniversary logic

### Budget Overruns
**Problem**: Generated events exceed budget constraints
**Solution**: Implement strict budget validation and event capping

## Dependencies

### Data Dependencies
- `int_previous_year_workforce.sql` - Current workforce state
- `int_hazard_*.sql` - Probability calculations
- Configuration seeds for rates and constraints

### Downstream Dependencies
- `fct_yearly_events.sql` - Event aggregation
- `fct_workforce_snapshot.sql` - Workforce state calculation
- Validation models for data quality

## Related Files

### Hazard Models
- `int_hazard_promotion.sql` - Promotion probability calculations
- `int_hazard_termination.sql` - Termination risk modeling
- `int_hazard_merit.sql` - Merit raise probability

### Supporting Models
- `int_baseline_workforce.sql` - Starting workforce state
- `int_previous_year_workforce.sql` - Year-over-year progression

### Configuration
- `config/simulation_config.yaml` - Event generation parameters
- `dbt/seeds/config_*_hazard_*.csv` - Probability tables

## Implementation Notes

### Performance Optimization
- Use efficient random number generation
- Implement proper indexing on key columns
- Minimize data shuffling with strategic ORDER BY
- Cache expensive calculations within models

### Data Quality
- Validate all generated events against business rules
- Ensure referential integrity across event types
- Implement comprehensive schema tests
- Monitor event volume distributions

### Testing Strategy
- Unit tests for individual event calculations
- Integration tests for event interactions
- Validation tests with known scenarios
- Performance tests with realistic data volumes