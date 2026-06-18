-- Test: Verify tenure-graded match config has no gaps/overlaps at band OR tier level
-- Feature 099 / FR-008 (run-time hard block): this is the last line of defense for
-- configs that bypass the Pydantic loader (e.g., raw `dbt --vars` invocation), since
-- the Pydantic EmployerMatchSettings validator (the first line of defense) cannot
-- catch malformed vars passed directly to dbt.
-- Uses [min, max) interval convention, mirroring test_tenure_band_no_gaps.sql.

{% set tenure_graded_bands = var('tenure_graded_bands', []) %}

{% if tenure_graded_bands | length == 0 %}
-- No tenure-graded config active in this invocation — nothing to validate.
SELECT NULL AS violation_type, NULL AS detail WHERE FALSE
{% else %}

WITH band_bounds AS (
    SELECT * FROM (
        VALUES
        {% for band in tenure_graded_bands %}
        ({{ loop.index0 }}, {{ band['min_years'] }}, {{ band['max_years'] if band['max_years'] is not none else 'NULL' }})
        {%- if not loop.last %},{% endif %}
        {% endfor %}
    ) AS t(band_index, min_years, max_years)
),

ordered_bands AS (
    SELECT
        band_index, min_years, max_years,
        LEAD(min_years) OVER (ORDER BY min_years) AS next_min_years
    FROM band_bounds
),

band_gaps_overlaps AS (
    SELECT
        'band' AS violation_type,
        'min=' || min_years || ' max=' || COALESCE(max_years::VARCHAR, 'inf') ||
            ' next_min=' || next_min_years AS detail
    FROM ordered_bands
    WHERE next_min_years IS NOT NULL
      AND (max_years IS NULL OR max_years != next_min_years)
),

bands_not_starting_at_zero AS (
    SELECT
        'band' AS violation_type,
        'first band does not start at 0: min=' || MIN(min_years)::VARCHAR AS detail
    FROM band_bounds
    HAVING MIN(min_years) != 0
),

tier_bounds AS (
    SELECT * FROM (
        VALUES
        {%- set tier_rows = [] -%}
        {%- for band_idx in range(tenure_graded_bands | length) -%}
          {%- for tier in tenure_graded_bands[band_idx]['tiers'] -%}
            {%- set _ = tier_rows.append(
                '(' ~ band_idx ~ ', ' ~ tier['employee_min'] ~ ', ' ~ tier['employee_max'] ~ ')'
            ) -%}
          {%- endfor -%}
        {%- endfor -%}
        {{ tier_rows | join(',\n        ') }}
    ) AS t(band_index, employee_min, employee_max)
),

ordered_tiers AS (
    SELECT
        band_index, employee_min, employee_max,
        LEAD(employee_min) OVER (PARTITION BY band_index ORDER BY employee_min) AS next_employee_min
    FROM tier_bounds
),

tier_gaps_overlaps AS (
    SELECT
        'tier' AS violation_type,
        'band_index=' || band_index || ' employee_max=' || employee_max ||
            ' next_employee_min=' || next_employee_min AS detail
    FROM ordered_tiers
    WHERE next_employee_min IS NOT NULL
      AND employee_max != next_employee_min
),

tiers_not_starting_at_zero AS (
    SELECT
        'tier' AS violation_type,
        'band_index=' || band_index || ' first tier does not start at 0: employee_min=' || MIN(employee_min)::VARCHAR AS detail
    FROM tier_bounds
    GROUP BY band_index
    HAVING MIN(employee_min) != 0
)

SELECT violation_type, detail FROM band_gaps_overlaps
UNION ALL
SELECT violation_type, detail FROM bands_not_starting_at_zero
UNION ALL
SELECT violation_type, detail FROM tier_gaps_overlaps
UNION ALL
SELECT violation_type, detail FROM tiers_not_starting_at_zero

{% endif %}
