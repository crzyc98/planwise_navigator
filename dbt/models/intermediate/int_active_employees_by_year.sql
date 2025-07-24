{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id']},
        {'columns': ['simulation_year']}
    ],
    tags=["foundation", "critical", "unified_interface"]
) }}

/*
  Secondary helper model providing unified interface for active employees across all years.
  
  This model serves as a clean abstraction layer that provides a single interface
  for accessing active employees regardless of the simulation year.
  
  Logic:
  - For year 1 (start_year): Select from int_baseline_workforce
  - For subsequent years: Select from int_active_employees_prev_year_snapshot
  
  Dependencies:
  - int_baseline_workforce (for first year)
  - int_active_employees_prev_year_snapshot (for subsequent years)
*/

with baseline_employees as (
  select
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    employment_status,
    termination_date,
    
    -- Calculate age and tenure bands
    case
      when current_age < 25 then 'Under 25'
      when current_age < 35 then '25-34'
      when current_age < 45 then '35-44'
      when current_age < 55 then '45-54'
      when current_age < 65 then '55-64'
      else '65+'
    end as age_band,
    
    case
      when current_tenure < 1 then 'Less than 1 year'
      when current_tenure < 3 then '1-2 years'
      when current_tenure < 5 then '3-4 years'
      when current_tenure < 10 then '5-9 years'
      when current_tenure < 20 then '10-19 years'
      else '20+ years'
    end as tenure_band,
    
    {{ var('simulation_year') }} as simulation_year,
    'baseline' as data_source,
    
    -- Data quality validation
    case
      when employee_id is null then false
      when employee_ssn is null then false
      when employee_birth_date is null then false
      when employee_hire_date is null then false
      when employee_gross_compensation <= 0 then false
      when current_age < 0 or current_age > 100 then false
      when current_tenure < 0 then false
      else true
    end as data_quality_valid,
    
    'baseline' as dependency_resolution_method
    
  from {{ ref('int_baseline_workforce') }}
  where employment_status = 'active'
),

helper_model_employees as (
  select
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    employment_status,
    termination_date,
    age_band,
    tenure_band,
    simulation_year,
    data_source,
    data_quality_valid,
    'helper_model' as dependency_resolution_method
    
  from {{ ref('int_active_employees_prev_year_snapshot') }}
),

unified_employees as (
  {% if var('simulation_year') == var('start_year') %}
    -- First year: use baseline workforce
    select * from baseline_employees
  {% else %}
    -- Subsequent years: use helper model with error handling
    select * from helper_model_employees
    
    {% if not var('simulation_year', none) %}
      union all
      select 
        null as employee_id,
        null as employee_ssn,
        null as employee_birth_date,
        null as employee_hire_date,
        0 as employee_gross_compensation,
        0 as current_age,
        0 as current_tenure,
        null as level_id,
        'error' as employment_status,
        null as termination_date,
        'Error' as age_band,
        'Error' as tenure_band,
        {{ var('simulation_year') }} as simulation_year,
        'error_no_previous_data' as data_source,
        false as data_quality_valid,
        'error_handling' as dependency_resolution_method
      where not exists (select 1 from helper_model_employees)
    {% endif %}
  {% endif %}
)

select *
from unified_employees
where data_quality_valid = true