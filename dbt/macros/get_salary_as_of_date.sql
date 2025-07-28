{#
    Macro to calculate an employee's salary rate as of a specific date,
    incorporating all prior compensation events with deterministic ordering.

    Parameters:
    - employee_id_column: Column name for employee identifier
    - as_of_date_column: Column name for the target date
    - events_table_ref: Reference to the events table (typically fct_yearly_events)
    - base_salary_column: Starting salary column from base table

    Returns the compensation_amount from the latest applicable event,
    or the base salary if no events have occurred.
#}

{% macro get_salary_as_of_date(employee_id_column, as_of_date_column, events_table_ref, base_salary_column) %}

    COALESCE(
        (
            SELECT compensation_amount
            FROM {{ events_table_ref }} events
            WHERE events.employee_id = {{ employee_id_column }}
                AND events.event_type IN ('RAISE', 'promotion')
                AND events.effective_date <= {{ as_of_date_column }}
            ORDER BY
                events.effective_date DESC,
                events.event_sequence DESC  -- Handle same-day events deterministically
            LIMIT 1
        ),
        {{ base_salary_column }}  -- Fallback to base salary if no events
    )

{% endmacro %}
