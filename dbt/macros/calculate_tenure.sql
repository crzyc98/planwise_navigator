{#
    calculate_tenure - Calculate employee tenure using day-based arithmetic

    Formula: floor((as_of_date - hire_date) / 365.25)

    This macro provides accurate tenure calculation by:
    1. Computing the number of days between hire date and as-of date
    2. Dividing by 365.25 to account for leap years
    3. Truncating (floor) to get whole years (not rounding)

    Usage:
        {{ calculate_tenure('employee_hire_date', "MAKE_DATE(" ~ var('simulation_year') ~ ", 12, 31)") }} AS current_tenure

    Parameters:
        hire_date_column: Column name containing the hire date (e.g., 'employee_hire_date')
        as_of_date: SQL expression for the reference date (e.g., "MAKE_DATE(2025, 12, 31)")

    Edge Cases:
        - NULL hire_date: Returns 0
        - hire_date > as_of_date: Returns 0 (handles future hires)
        - hire_date = as_of_date: Returns 0 (hired same day)

    Returns: INTEGER representing years of service

    Example Results:
        hire_date='2020-06-15', as_of='2025-12-31' -> 5 years (2025 days / 365.25 = 5.54 -> 5)
        hire_date='2021-01-01', as_of='2025-12-31' -> 4 years (1826 days / 365.25 = 4.99 -> 4)
        hire_date='2025-07-01', as_of='2025-12-31' -> 0 years (183 days / 365.25 = 0.50 -> 0)

    Note: This calculation matches the Polars pipeline in polars_state_pipeline.py (lines 1860-1866)
    for consistency across SQL and Polars execution modes.
#}

{% macro calculate_tenure(hire_date_column, as_of_date) %}
    CASE
        WHEN {{ hire_date_column }} IS NULL THEN 0
        WHEN {{ hire_date_column }} > {{ as_of_date }} THEN 0
        ELSE FLOOR(({{ as_of_date }} - {{ hire_date_column }}) / 365.25)::INTEGER
    END
{% endmacro %}
