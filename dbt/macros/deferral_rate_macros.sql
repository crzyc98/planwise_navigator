/*
Epic E049: Census Deferral Rate Integration - Macros
Provides standardized deferral rate configuration functions
*/

{% macro default_deferral_rate() %}
    {{ var('auto_enrollment_default_deferral_rate', 0.02) }}
{% endmacro %}

{% macro plan_deferral_cap() %}
    {{ var('plan_deferral_cap', 0.75) }}
{% endmacro %}

{% macro normalize_deferral_rate(rate_field) %}
    LEAST(
        {{ plan_deferral_cap() }},
        GREATEST(0.0,
            CASE
                WHEN {{ rate_field }} > 1.0 THEN {{ rate_field }} / 100.0
                ELSE {{ rate_field }}
            END
        )
    )
{% endmacro %}

{% macro census_fallback_rate() %}
    {{ var('census_fallback_rate', 0.03) }}
{% endmacro %}
