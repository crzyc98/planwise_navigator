{% snapshot scd_workforce_state_optimized %}
    {{
        config(
            target_schema='snapshots',
            unique_key='employee_id',
            strategy='check',
            check_cols=[
                'current_compensation',
                'level_id',
                'employment_status',
                'termination_date'
            ],
            invalidate_hard_deletes=True,
            updated_at='snapshot_created_at'
        )
    }}

    -- Optimized SCD workforce state with hash-based change detection
    -- Significant performance improvements over manual SCD logic
    WITH workforce_with_hash AS (
        SELECT
            employee_id,
            employee_ssn,
            employee_birth_date,
            employee_hire_date,
            current_compensation,
            prorated_annual_compensation,
            full_year_equivalent_compensation,
            current_age,
            current_tenure,
            level_id,
            age_band,
            tenure_band,
            employment_status,
            termination_date,
            termination_reason,
            detailed_status_code,
            simulation_year,
            snapshot_created_at,
            -- Hash-based change detection for performance
            {{ dbt_utils.generate_surrogate_key([
                'current_compensation',
                'level_id',
                'employment_status',
                'termination_date'
            ]) }} as change_hash
        FROM {{ ref('fct_workforce_snapshot') }}
        WHERE simulation_year = {{ var('simulation_year', 2025) }}
    )

    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        current_compensation,
        prorated_annual_compensation,
        full_year_equivalent_compensation,
        current_age,
        current_tenure,
        level_id,
        age_band,
        tenure_band,
        employment_status,
        termination_date,
        termination_reason,
        detailed_status_code,
        simulation_year,
        snapshot_created_at,
        change_hash
    FROM workforce_with_hash

{% endsnapshot %}
