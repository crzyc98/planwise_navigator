{% macro get_eligibility_status(eligibility_date_column, as_of_date) %}
{%- if as_of_date is not defined -%}
    {%- set as_of_date = "CURRENT_DATE" -%}
{%- endif -%}
    CASE
        WHEN {{ eligibility_date_column }} IS NULL THEN 'unknown'
        WHEN {{ eligibility_date_column }} <= {{ as_of_date }} THEN 'eligible'
        ELSE 'pending'
    END
{% endmacro %}

{% macro get_eligibility_status_detailed(eligibility_date_column, waiting_period_days_column, as_of_date) %}
{%- if as_of_date is not defined -%}
    {%- set as_of_date = "CURRENT_DATE" -%}
{%- endif -%}
    CASE
        WHEN {{ eligibility_date_column }} IS NULL THEN 'no_determination'
        WHEN {{ waiting_period_days_column }} = 0 THEN 'immediate_eligible'
        WHEN {{ eligibility_date_column }} <= {{ as_of_date }} THEN 'service_met_eligible'
        ELSE 'waiting_period_pending'
    END
{% endmacro %}

{% macro days_until_eligible(eligibility_date_column, as_of_date) %}
{%- if as_of_date is not defined -%}
    {%- set as_of_date = "CURRENT_DATE" -%}
{%- endif -%}
    CASE
        WHEN {{ eligibility_date_column }} IS NULL THEN NULL
        WHEN {{ eligibility_date_column }} <= {{ as_of_date }} THEN 0
        ELSE DATEDIFF('day', {{ as_of_date }}, {{ eligibility_date_column }})
    END
{% endmacro %}
