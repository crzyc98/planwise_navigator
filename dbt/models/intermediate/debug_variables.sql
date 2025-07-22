{{ config(materialized='table') }}

-- Debug model to see what variables are being passed

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

SELECT
    {{ simulation_year }} AS debug_simulation_year,
    {{ start_year }} AS debug_start_year,
    '{{ var("simulation_year", "NOT_SET") }}' AS debug_raw_simulation_year,
    '{{ var("start_year", "NOT_SET") }}' AS debug_raw_start_year
