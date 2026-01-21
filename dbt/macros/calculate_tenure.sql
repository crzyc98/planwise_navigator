{#
    calculate_tenure - Calculate employee tenure using day-based arithmetic

    Formula: floor((effective_end_date - hire_date) / 365.25)

    This macro provides accurate tenure calculation by:
    1. Computing the number of days between hire date and effective end date
    2. Dividing by 365.25 to account for leap years
    3. Truncating (floor) to get whole years (not rounding)

    For terminated employees, tenure is calculated to their termination date.
    For active employees, tenure is calculated to the plan year end (12/31).

    Usage:
        -- Active employees (no termination date):
        {{ calculate_tenure('employee_hire_date', "MAKE_DATE(2025, 12, 31)") }} AS current_tenure

        -- With termination date handling:
        {{ calculate_tenure('employee_hire_date', "MAKE_DATE(2025, 12, 31)", 'termination_date') }} AS current_tenure

    Parameters:
        hire_date_column: Column name containing the hire date (e.g., 'employee_hire_date')
        as_of_date: SQL expression for the plan year end date (e.g., "MAKE_DATE(2025, 12, 31)")
        termination_date_column: (Optional) Column name for termination date. If provided and not null,
                                 tenure is calculated to termination date instead of as_of_date.

    Edge Cases:
        - NULL hire_date: Returns 0
        - hire_date > effective_end_date: Returns 0 (handles future hires)
        - hire_date = effective_end_date: Returns 0 (hired same day)
        - Terminated employee: Uses termination_date as end date

    Returns: INTEGER representing years of service

    Example Results:
        Active: hire='2020-06-15', as_of='2025-12-31' -> 5 years
        Active: hire='2021-01-01', as_of='2025-12-31' -> 4 years
        Terminated: hire='2020-01-01', term='2025-06-30' -> 5 years (to termination, not year end)

    Note: This calculation matches the Polars pipeline in polars_state_pipeline.py
    for consistency across SQL and Polars execution modes.
#}

{% macro calculate_tenure(hire_date_column, as_of_date, termination_date_column=none) %}
    CASE
        WHEN {{ hire_date_column }} IS NULL THEN 0
        {% if termination_date_column %}
        -- Use termination date if provided and not null, otherwise use plan year end
        WHEN {{ termination_date_column }} IS NOT NULL AND {{ hire_date_column }} > {{ termination_date_column }} THEN 0
        WHEN {{ termination_date_column }} IS NOT NULL THEN FLOOR(DATEDIFF('day', {{ hire_date_column }}::DATE, ({{ termination_date_column }})::DATE) / 365.25)::INTEGER
        {% endif %}
        WHEN {{ hire_date_column }} > {{ as_of_date }} THEN 0
        ELSE FLOOR(DATEDIFF('day', {{ hire_date_column }}::DATE, ({{ as_of_date }})::DATE) / 365.25)::INTEGER
    END
{% endmacro %}
