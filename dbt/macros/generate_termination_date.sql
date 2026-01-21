{#
    generate_termination_date - Generate distributed termination dates constrained by hire date

    Uses year-aware hashing to ensure dates are distributed across the year
    while maintaining determinism for reproducibility.

    Bug Fix (E021): This macro addresses the issue where termination dates were
    clustering on a single date because the hash only used employee_id.
    By including simulation_year in the hash, each year produces a
    different distribution while maintaining determinism.

    Bug Fix (E022): This macro now accepts hire_date_column to ensure
    termination dates are always >= hire_date. The date is computed as:
    - For employees hired before this year: Jan 1 + (hash % 365) → full year range
    - For employees hired this year: hire_date + (hash % days_until_year_end)
    This prevents impossible scenarios where employees are terminated before hired.

    Parameters:
        employee_id_column: Column containing employee ID (e.g., 'w.employee_id')
        simulation_year: The simulation year (integer or variable)
        hire_date_column: Column containing the employee's hire date (e.g., 'w.employee_hire_date')
        random_seed: Optional random seed for additional entropy (default: 42)

    Returns: DATE within the simulation year, always >= hire_date

    Example Usage:
        {{ generate_termination_date('w.employee_id', var('simulation_year'), 'w.employee_hire_date') }} AS effective_date
        {{ generate_termination_date('employee_id', 2026, 'hire_date', 123) }} AS termination_date

    Edge Cases:
        - Employee hired on Dec 31 of sim year: Returns Dec 31 (same-day termination)
        - Employee hired in future year: Returns NULL (should not be terminated)
        - NULL hire_date: Returns NULL (cannot calculate valid termination date)
#}

{% macro generate_termination_date(employee_id_column, simulation_year, hire_date_column, random_seed=42) %}
    CASE
        -- Handle NULL hire_date - cannot generate valid termination date
        WHEN {{ hire_date_column }} IS NULL THEN NULL
        -- Handle hire_date after year end - should not be terminated this year
        WHEN {{ hire_date_column }} > CAST('{{ simulation_year }}-12-31' AS DATE) THEN NULL
        -- Employee hired this year: termination date = hire_date + offset within remaining days
        WHEN {{ hire_date_column }} >= CAST('{{ simulation_year }}-01-01' AS DATE) THEN
            {{ hire_date_column }}::DATE
            + INTERVAL (
                ABS(HASH({{ employee_id_column }} || '|' || CAST({{ simulation_year }} AS VARCHAR) || '|DATE|{{ random_seed }}'))
                % GREATEST(1, DATEDIFF('day', {{ hire_date_column }}::DATE, CAST('{{ simulation_year }}-12-31' AS DATE)) + 1)
            ) DAY
        -- Employee hired before this year: termination date = Jan 1 + offset (full year range)
        -- Since hire_date < Jan 1, any date in the simulation year is valid
        ELSE
            CAST('{{ simulation_year }}-01-01' AS DATE)
            + INTERVAL (
                ABS(HASH({{ employee_id_column }} || '|' || CAST({{ simulation_year }} AS VARCHAR) || '|DATE|{{ random_seed }}'))
                % 365
            ) DAY
    END
{% endmacro %}
