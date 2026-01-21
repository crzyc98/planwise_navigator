{#
    generate_termination_date - Generate distributed termination dates

    Uses year-aware hashing to ensure dates are distributed across the year
    while maintaining determinism for reproducibility.

    Bug Fix: This macro addresses the issue where termination dates were
    clustering on a single date because the hash only used employee_id.
    By including simulation_year in the hash, each year produces a
    different distribution while maintaining determinism.

    Parameters:
        employee_id_column: Column containing employee ID (e.g., 'w.employee_id')
        simulation_year: The simulation year (integer or variable)
        random_seed: Optional random seed for additional entropy (default: 42)

    Returns: DATE within the simulation year

    Example Usage:
        {{ generate_termination_date('w.employee_id', var('simulation_year')) }} AS effective_date
        {{ generate_termination_date('employee_id', 2026, 123) }} AS termination_date
#}

{% macro generate_termination_date(employee_id_column, simulation_year, random_seed=42) %}
    CAST('{{ simulation_year }}-01-01' AS DATE)
    + INTERVAL (
        (ABS(HASH({{ employee_id_column }} || '|' || CAST({{ simulation_year }} AS VARCHAR) || '|DATE|{{ random_seed }}')) % 365)
    ) DAY
{% endmacro %}
