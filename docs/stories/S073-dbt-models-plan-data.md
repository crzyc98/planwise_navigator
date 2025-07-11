# Story S073: Extend dbt Models for Plan Data

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 13
**Priority**: High

## Story

**As a** data engineer
**I want** staging and intermediate models for plan configuration
**So that** downstream models can access plan rules and parameters

## Business Context

This story creates the dbt model infrastructure to support DC plan data processing, building upon the existing workforce simulation models. It establishes staging models for plan configuration, intermediate models for parameter resolution, and fact models for plan events while maintaining integration with existing employee dimensions.

## Acceptance Criteria

### Model Categories
- [ ] **New staging models** for plan_design, irs_limits with proper cleaning and validation
- [ ] **Intermediate models** for effective plan parameters with vectorized processing
- [ ] **Integration with existing** employee dimension tables
- [ ] **Account state snapshot models** for performance optimization
- [ ] **Compliance testing models** for ADP/ACP and 415(c) limits
- [ ] **Plan-year-specific IRS limits** with annual versioning (no mid-year changes)
- [ ] **Validation that IRS limits exist** for each simulation year
- [ ] **Automatic application** of correct year's limits based on plan_year
- [ ] **Historical IRS limit preservation** for audit trail

### dbt Contract Compliance
- [ ] **All models have contracts** with `contract: {enforced: true}`
- [ ] **Complete column definitions** with proper data types
- [ ] **Comprehensive testing** with schema.yml test coverage
- [ ] **Performance optimization** through proper indexing and materialization

## Technical Specifications

### Staging Models

#### stg_irs_limits.sql
```sql
-- Annual IRS contribution and compensation limits
-- Source: seeds/irs_limits.csv
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['staging', 'dc_plan', 'irs_limits']
) }}

SELECT
    plan_year,
    employee_deferral_limit,
    catch_up_contribution_limit,
    annual_additions_limit,
    compensation_limit,
    highly_compensated_threshold,
    key_employee_threshold,
    social_security_wage_base,
    effective_date,
    created_at,
    source_document
FROM {{ ref('irs_limits') }}
WHERE effective_date = DATE_TRUNC('year', effective_date)  -- Enforce annual updates only
```

#### stg_plan_designs.sql
```sql
-- Plan design configurations from YAML/JSON sources
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['staging', 'dc_plan', 'plan_config']
) }}

SELECT
    plan_id,
    plan_name,
    plan_type,
    effective_date,
    plan_year,
    JSON_EXTRACT(features, '$.roth') as roth_enabled,
    JSON_EXTRACT(features, '$.after_tax') as after_tax_enabled,
    JSON_EXTRACT(features, '$.catch_up') as catch_up_enabled,
    JSON_EXTRACT(eligibility, '$.minimum_age') as min_age,
    JSON_EXTRACT(eligibility, '$.minimum_service_months') as min_service_months,
    JSON_EXTRACT(eligibility, '$.hours_requirement') as hours_requirement,
    JSON_EXTRACT(vesting, '$.type') as vesting_type,
    JSON_EXTRACT(vesting, '$.schedule') as vesting_schedule,
    JSON_EXTRACT(matching, '$.formula') as match_formula,
    JSON_EXTRACT(matching, '$.max_match_percentage') as max_match_pct,
    JSON_EXTRACT(matching, '$.true_up') as true_up_enabled,
    created_at,
    updated_at
FROM {{ ref('plan_designs') }}
WHERE effective_date <= CURRENT_DATE
```

### Intermediate Models

#### int_effective_irs_limits.sql
```sql
-- Resolve IRS limits for each plan year with validation
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'irs_limits'],
    indexes=[
        {'columns': ['plan_year'], 'type': 'btree'}
    ]
) }}

WITH validated_limits AS (
    SELECT
        plan_year,
        employee_deferral_limit,
        catch_up_contribution_limit,
        annual_additions_limit,
        compensation_limit,
        highly_compensated_threshold,
        key_employee_threshold,
        social_security_wage_base,
        CASE
            WHEN plan_year >= YEAR(CURRENT_DATE)
            THEN 'projected'
            ELSE 'historical'
        END as limit_status
    FROM {{ ref('stg_irs_limits') }}
),
limit_validation AS (
    SELECT
        *,
        -- Validate limit consistency
        CASE
            WHEN employee_deferral_limit <= 0 THEN 'INVALID_DEFERRAL_LIMIT'
            WHEN annual_additions_limit <= employee_deferral_limit THEN 'INVALID_ADDITIONS_LIMIT'
            WHEN compensation_limit <= highly_compensated_threshold THEN 'INVALID_COMP_LIMIT'
            ELSE 'VALID'
        END as validation_status
    FROM validated_limits
)
SELECT *
FROM limit_validation
WHERE validation_status = 'VALID'
```

#### int_effective_plan_parameters.sql
```sql
-- Resolve effective plan parameters with scenario/design variations
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'parameters'],
    indexes=[
        {'columns': ['scenario_id', 'plan_design_id'], 'type': 'hash'},
        {'columns': ['plan_id', 'plan_year'], 'type': 'hash'}
    ]
) }}

WITH base_plans AS (
    SELECT
        plan_id,
        plan_year,
        'baseline' as scenario_id,
        'standard' as plan_design_id,
        roth_enabled,
        after_tax_enabled,
        catch_up_enabled,
        min_age,
        min_service_months,
        hours_requirement,
        vesting_type,
        vesting_schedule,
        match_formula,
        max_match_pct,
        true_up_enabled
    FROM {{ ref('stg_plan_designs') }}
),
plan_variations AS (
    SELECT
        pv.scenario_id,
        pv.plan_design_id,
        pv.plan_id,
        pv.plan_year,
        pv.design_name,
        JSON_EXTRACT(pv.variations, '$.matching.formula') as override_match_formula,
        JSON_EXTRACT(pv.variations, '$.features.auto_enrollment') as override_auto_enrollment,
        JSON_EXTRACT(pv.variations, '$.features.auto_escalation') as override_auto_escalation,
        pv.effective_date
    FROM {{ ref('scenario_plan_designs') }} pv
    WHERE pv.effective_date <= CURRENT_DATE
),
effective_parameters AS (
    SELECT
        COALESCE(pv.scenario_id, bp.scenario_id) as scenario_id,
        COALESCE(pv.plan_design_id, bp.plan_design_id) as plan_design_id,
        bp.plan_id,
        bp.plan_year,
        bp.roth_enabled,
        bp.after_tax_enabled,
        bp.catch_up_enabled,
        bp.min_age,
        bp.min_service_months,
        bp.hours_requirement,
        bp.vesting_type,
        bp.vesting_schedule,
        -- Apply variations to base plan parameters
        COALESCE(pv.override_match_formula, bp.match_formula) as effective_match_formula,
        bp.max_match_pct,
        bp.true_up_enabled,
        COALESCE(pv.override_auto_enrollment, FALSE) as auto_enrollment_enabled,
        COALESCE(pv.override_auto_escalation, FALSE) as auto_escalation_enabled,
        pv.design_name
    FROM base_plans bp
    LEFT JOIN plan_variations pv
        ON bp.plan_id = pv.plan_id
        AND bp.plan_year = pv.plan_year
)
SELECT * FROM effective_parameters
```

#### int_hce_determination.sql
```sql
-- Calculate HCE status for each employee based on YTD compensation
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'hce'],
    indexes=[
        {'columns': ['employee_id', 'plan_year'], 'type': 'hash'}
    ]
) }}

WITH ytd_compensation AS (
    SELECT
        e.employee_id,
        e.plan_year,
        e.hire_date,
        SUM(c.compensation_amount) as ytd_compensation,
        COUNT(DISTINCT c.pay_period_end) as pay_periods,
        -- Annualize for partial year employees
        CASE
            WHEN e.hire_date >= DATE_TRUNC('year', CURRENT_DATE) THEN
                SUM(c.compensation_amount) * 12.0 / COUNT(DISTINCT c.pay_period_end)
            ELSE
                SUM(c.compensation_amount)
        END as annualized_compensation
    FROM {{ ref('int_employee_demographics') }} e
    JOIN {{ ref('fct_compensation_events') }} c
        ON e.employee_id = c.employee_id
        AND c.plan_year = e.plan_year
    GROUP BY e.employee_id, e.plan_year, e.hire_date
),
hce_status AS (
    SELECT
        yc.*,
        il.highly_compensated_threshold as hce_threshold,
        yc.annualized_compensation >= il.highly_compensated_threshold as is_hce,
        LAG(yc.annualized_compensation >= il.highly_compensated_threshold)
            OVER (PARTITION BY yc.employee_id ORDER BY yc.plan_year) as prior_year_hce
    FROM ytd_compensation yc
    JOIN {{ ref('int_effective_irs_limits') }} il
        ON yc.plan_year = il.plan_year
)
SELECT
    *,
    -- Flag when HCE status changes
    CASE
        WHEN is_hce != COALESCE(prior_year_hce, FALSE) THEN TRUE
        ELSE FALSE
    END as hce_status_changed
FROM hce_status
```

### Fact Models

#### fct_retirement_events.sql
```sql
-- Central fact table for all DC plan events
{{ config(
    materialized='incremental',
    unique_key=['event_id'],
    on_schema_change='fail',
    contract={'enforced': true},
    tags=['critical', 'dc_plan', 'events'],
    indexes=[
        {'columns': ['employee_id', 'plan_year'], 'type': 'hash'},
        {'columns': ['scenario_id', 'plan_design_id'], 'type': 'hash'},
        {'columns': ['event_type', 'effective_date'], 'type': 'btree'}
    ]
) }}

SELECT
    event_id,
    employee_id,
    event_type,
    effective_date,
    plan_year,
    plan_id,
    scenario_id,
    plan_design_id,
    -- Event-specific payload columns
    CASE
        WHEN event_type = 'contribution' THEN JSON_EXTRACT(payload, '$.source')
        ELSE NULL
    END as contribution_source,
    CASE
        WHEN event_type = 'contribution' THEN CAST(JSON_EXTRACT(payload, '$.amount') AS DECIMAL(15,2))
        ELSE NULL
    END as contribution_amount,
    CASE
        WHEN event_type = 'enrollment' THEN CAST(JSON_EXTRACT(payload, '$.pre_tax_contribution_rate') AS DECIMAL(5,4))
        ELSE NULL
    END as pre_tax_rate,
    CASE
        WHEN event_type = 'enrollment' THEN CAST(JSON_EXTRACT(payload, '$.roth_contribution_rate') AS DECIMAL(5,4))
        ELSE NULL
    END as roth_rate,
    CASE
        WHEN event_type = 'vesting' THEN CAST(JSON_EXTRACT(payload, '$.vested_percentage') AS DECIMAL(5,4))
        ELSE NULL
    END as vested_percentage,
    CASE
        WHEN event_type = 'hce_status' THEN CAST(JSON_EXTRACT(payload, '$.is_hce') AS BOOLEAN)
        ELSE NULL
    END as is_hce,
    CASE
        WHEN event_type = 'compliance' THEN JSON_EXTRACT(payload, '$.compliance_type')
        ELSE NULL
    END as compliance_type,
    payload as full_payload,
    created_at,
    source_system
FROM {{ ref('retirement_plan_events') }}
{% if is_incremental() %}
    WHERE created_at > (SELECT MAX(created_at) FROM {{ this }})
{% endif %}
```

#### fct_participant_account_summary.sql
```sql
-- Optimized account balance summary for performance
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'plan_id', 'scenario_id', 'plan_design_id', 'as_of_date'],
    on_schema_change='fail',
    contract={'enforced': true},
    tags=['critical', 'dc_plan', 'account_summary'],
    indexes=[
        {'columns': ['scenario_id', 'plan_design_id'], 'type': 'hash'},
        {'columns': ['employee_id', 'plan_id'], 'type': 'hash'},
        {'columns': ['as_of_date'], 'type': 'btree'}
    ]
) }}

SELECT
    employee_id,
    plan_id,
    scenario_id,
    plan_design_id,
    as_of_date,
    SUM(CASE WHEN contribution_source = 'employee_pre_tax' THEN contribution_amount ELSE 0 END) as pre_tax_balance,
    SUM(CASE WHEN contribution_source = 'employee_roth' THEN contribution_amount ELSE 0 END) as roth_balance,
    SUM(CASE WHEN contribution_source = 'employee_after_tax' THEN contribution_amount ELSE 0 END) as after_tax_balance,
    SUM(CASE WHEN contribution_source = 'employer_match' THEN contribution_amount ELSE 0 END) as match_balance,
    SUM(CASE WHEN contribution_source = 'employer_match_true_up' THEN contribution_amount ELSE 0 END) as true_up_balance,
    SUM(CASE WHEN contribution_source = 'employer_nonelective' THEN contribution_amount ELSE 0 END) as nonelective_balance,
    SUM(CASE WHEN contribution_source = 'employer_profit_sharing' THEN contribution_amount ELSE 0 END) as profit_sharing_balance,
    SUM(CASE WHEN contribution_source = 'forfeiture_allocation' THEN contribution_amount ELSE 0 END) as forfeiture_balance,
    SUM(contribution_amount) as total_balance,
    COUNT(*) as event_count,
    MAX(created_at) as last_updated
FROM {{ ref('fct_retirement_events') }}
WHERE event_type = 'contribution'
{% if is_incremental() %}
    AND as_of_date > (SELECT MAX(as_of_date) FROM {{ this }})
{% endif %}
GROUP BY employee_id, plan_id, scenario_id, plan_design_id, as_of_date
```

### Compliance Models

#### int_402g_compliance_check.sql
```sql
-- Validate Section 402(g) elective deferral limits
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'compliance'],
    indexes=[
        {'columns': ['employee_id', 'plan_year'], 'type': 'hash'}
    ]
) }}

WITH participant_deferrals AS (
    SELECT
        e.employee_id,
        e.plan_year,
        e.birth_date,
        YEAR(CURRENT_DATE) - YEAR(e.birth_date) as current_age,
        SUM(CASE WHEN re.contribution_source = 'employee_pre_tax' THEN re.contribution_amount ELSE 0 END) as pre_tax_deferrals,
        SUM(CASE WHEN re.contribution_source = 'employee_roth' THEN re.contribution_amount ELSE 0 END) as roth_deferrals,
        SUM(CASE WHEN re.contribution_source IN ('employee_pre_tax', 'employee_roth') THEN re.contribution_amount ELSE 0 END) as total_deferrals
    FROM {{ ref('int_employee_demographics') }} e
    JOIN {{ ref('fct_retirement_events') }} re
        ON e.employee_id = re.employee_id
        AND re.plan_year = e.plan_year
    WHERE re.event_type = 'contribution'
    GROUP BY e.employee_id, e.plan_year, e.birth_date
),
compliance_check AS (
    SELECT
        pd.*,
        il.employee_deferral_limit,
        il.catch_up_contribution_limit,
        -- Check if participant is catch-up eligible (age 50+ by year end)
        CASE
            WHEN pd.current_age >= 50 OR
                 (YEAR(DATE(pd.plan_year || '-12-31')) - YEAR(pd.birth_date)) >= 50
            THEN TRUE
            ELSE FALSE
        END as catch_up_eligible,
        -- Calculate applicable limit
        CASE
            WHEN pd.current_age >= 50 OR
                 (YEAR(DATE(pd.plan_year || '-12-31')) - YEAR(pd.birth_date)) >= 50
            THEN il.employee_deferral_limit + il.catch_up_contribution_limit
            ELSE il.employee_deferral_limit
        END as applicable_limit,
        -- Check for excess
        GREATEST(pd.total_deferrals - il.employee_deferral_limit, 0) as excess_amount
    FROM participant_deferrals pd
    JOIN {{ ref('int_effective_irs_limits') }} il
        ON pd.plan_year = il.plan_year
)
SELECT
    *,
    CASE
        WHEN excess_amount > 0 THEN 'VIOLATION'
        WHEN total_deferrals >= applicable_limit * 0.95 THEN 'WARNING'
        ELSE 'COMPLIANT'
    END as compliance_status
FROM compliance_check
```

#### int_415c_compliance_check.sql
```sql
-- Validate Section 415(c) annual additions limits
{{ config(
    materialized='table',
    contract={'enforced': true},
    tags=['intermediate', 'dc_plan', 'compliance'],
    indexes=[
        {'columns': ['employee_id', 'plan_year'], 'type': 'hash'}
    ]
) }}

WITH annual_additions AS (
    SELECT
        e.employee_id,
        e.plan_year,
        -- Employee contributions
        SUM(CASE WHEN re.contribution_source IN ('employee_pre_tax', 'employee_roth', 'employee_after_tax')
            THEN re.contribution_amount ELSE 0 END) as employee_contributions,
        -- Employer contributions (including true-up)
        SUM(CASE WHEN re.contribution_source IN ('employer_match', 'employer_match_true_up', 'employer_nonelective', 'employer_profit_sharing')
            THEN re.contribution_amount ELSE 0 END) as employer_contributions,
        -- Forfeitures allocated
        SUM(CASE WHEN re.contribution_source = 'forfeiture_allocation' THEN re.contribution_amount ELSE 0 END) as forfeitures,
        -- Total annual additions
        SUM(re.contribution_amount) as total_annual_additions
    FROM {{ ref('int_employee_demographics') }} e
    JOIN {{ ref('fct_retirement_events') }} re
        ON e.employee_id = re.employee_id
        AND re.plan_year = e.plan_year
    WHERE re.event_type IN ('contribution', 'forfeiture_allocation')
    GROUP BY e.employee_id, e.plan_year
),
compliance_check AS (
    SELECT
        aa.*,
        il.annual_additions_limit,
        il.compensation_limit,
        -- Check for excess
        GREATEST(aa.total_annual_additions - il.annual_additions_limit, 0) as excess_amount,
        -- Calculate remaining capacity
        il.annual_additions_limit - aa.total_annual_additions as remaining_capacity
    FROM annual_additions aa
    JOIN {{ ref('int_effective_irs_limits') }} il
        ON aa.plan_year = il.plan_year
)
SELECT
    *,
    CASE
        WHEN excess_amount > 0 THEN 'VIOLATION'
        WHEN remaining_capacity <= annual_additions_limit * 0.05 THEN 'WARNING'
        ELSE 'COMPLIANT'
    END as compliance_status,
    -- Suggest corrective action
    CASE
        WHEN excess_amount > 0 AND excess_amount <= employer_contributions
            THEN 'REDUCE_EMPLOYER_CONTRIBUTION'
        WHEN excess_amount > 0
            THEN 'REFUND_EMPLOYEE_CONTRIBUTION'
        ELSE NULL
    END as suggested_correction
FROM compliance_check
```

## Implementation Tasks

### Phase 1: Staging Models
- [ ] **Create staging models** for IRS limits and plan designs
- [ ] **Implement data validation** and cleansing logic
- [ ] **Add comprehensive tests** with schema.yml coverage
- [ ] **Establish contract enforcement** for all staging models

### Phase 2: Intermediate Models
- [ ] **Build parameter resolution models** with scenario support
- [ ] **Implement HCE determination** using existing workforce data
- [ ] **Create compliance validation models** for IRS regulations
- [ ] **Add performance optimization** through proper indexing

### Phase 3: Fact Models
- [ ] **Create central retirement events fact table** with incremental loading
- [ ] **Build account summary models** for performance optimization
- [ ] **Implement scenario isolation** through composite keys
- [ ] **Add comprehensive testing** and validation

## Dependencies

- **S072**: Retirement Plan Event Schema (provides event definitions)
- **Existing workforce models**: Employee demographics, compensation events
- **IRS limits seed data**: Annual regulatory limits
- **Plan design configurations**: YAML/JSON plan definitions

## Success Metrics

### Performance Requirements
- [ ] **Model materialization**: <5 minutes for full refresh
- [ ] **Incremental processing**: <30 seconds for daily updates
- [ ] **Query performance**: <100ms for account balance lookups
- [ ] **Memory efficiency**: Models support 100K+ participants

### Data Quality Requirements
- [ ] **Contract compliance**: 100% of models have enforced contracts
- [ ] **Test coverage**: >95% test coverage for all models
- [ ] **Data validation**: Zero invalid records in production models
- [ ] **Historical preservation**: Complete audit trail maintained

## Definition of Done

- [ ] **All staging models implemented** with proper contracts and testing
- [ ] **Intermediate models created** for parameter resolution and compliance
- [ ] **Fact models built** with optimal performance characteristics
- [ ] **Integration verified** with existing workforce models
- [ ] **Performance benchmarks met** for enterprise scale processing
- [ ] **Comprehensive testing** with edge case coverage
- [ ] **Documentation complete** with model lineage and business logic
- [ ] **Code review approved** following dbt best practices
