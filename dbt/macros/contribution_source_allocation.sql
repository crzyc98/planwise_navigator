{% macro contribution_source_allocation() %}
{# Correlated reporting allocation. Totals/events are never mutated here. #}
{% set source = var('contribution_sources', {}) %}
{% set policy = source.get('policy', 'legacy_estimate') %}
{% set fraction = source.get('roth_fraction', 0.15) | float %}
{% set enabled = source.get('mandatory_roth_enabled', false) %}
{% set roth_available = source.get('roth_available', true) %}
{% set year = var('simulation_year', 2025) | int %}
{% set threshold = namespace(amount=none, provenance='unavailable', basis='unavailable') %}
{% if year == 2026 %}
  {% set threshold.amount = 150000 %}
  {% set threshold.provenance = 'IRS Notice 2025-67' %}
  {% set threshold.basis = 'published' %}
{% else %}
  {% for item in source.get('projected_thresholds', []) if item.year == year %}
    {% set threshold.amount = item.threshold | float %}
    {% set threshold.provenance = item.provenance %}
    {% set threshold.basis = 'projected' %}
  {% endfor %}
{% endif %}
{% if policy not in ['legacy_estimate', 'assumed_split'] or fraction < 0 or fraction > 1 %}
  {{ exceptions.raise_compiler_error('Invalid contribution source allocation policy') }}
{% endif %}
{% if policy == 'legacy_estimate' and fraction != 0.15 %}
  {{ exceptions.raise_compiler_error('legacy_estimate requires a 15% Roth fraction') }}
{% endif %}
{% if not roth_available and fraction != 0 %}
  {{ exceptions.raise_compiler_error('A plan without Roth requires a zero Roth fraction') }}
{% endif %}
WITH wage_evidence AS (
  SELECT NULL::VARCHAR AS employee_id, NULL::DECIMAL(18,2) AS wages,
    NULL::VARCHAR AS basis, NULL::VARCHAR AS provenance
  WHERE FALSE
  {% for wage in source.get('wage_evidence', [])
      if wage.wage_year == year - 1 and wage.employer_id == source.get('employer_id') %}
  UNION ALL
  SELECT '{{ wage.employee_id | replace("'", "''") }}',
    {{ wage.wages | float }}::DECIMAL(18,2),
    '{{ wage.basis | replace("'", "''") }}',
    '{{ wage.provenance | replace("'", "''") }}'
  {% endfor %}
), inputs AS (
  SELECT
    ROUND(composed.annual_contribution_amount, 2)::DECIMAL(18,2) AS total,
    ROUND(ROUND(composed.annual_contribution_amount, 2) * {{ fraction }}, 2)::DECIMAL(18,2)
      AS preferred_roth,
    CASE WHEN composed.employee_birth_date IS NOT NULL
      THEN {{ year }} - YEAR(composed.employee_birth_date) END AS year_end_age,
    GREATEST(0, ROUND(composed.annual_contribution_amount - irs_limits.base_limit, 2))
      AS catch_up_used,
    wages, basis, provenance
  FROM (
    SELECT MAX(wages) AS wages, MAX(basis) AS basis, MAX(provenance) AS provenance
    FROM wage_evidence
    WHERE wage_evidence.employee_id = composed.employee_id
  ) evidence
), assessed AS (
  SELECT total, preferred_roth, year_end_age, catch_up_used, wages, basis, provenance,
    CASE
      WHEN NOT {{ enabled }} THEN 'not_evaluated'
      WHEN '{{ source.get('applicability', 'unsupported') }}' != 'single_employer_401k'
        THEN 'unsupported_applicability'
      WHEN {{ year }} < 2026 THEN 'not_applicable_before_2026'
      WHEN catch_up_used = 0 THEN 'no_base_limit_catch_up'
      WHEN year_end_age IS NULL THEN 'unresolved_age'
      WHEN year_end_age < irs_limits.catch_up_age_threshold THEN 'ineligible_catch_up'
      WHEN total > CASE
        WHEN year_end_age BETWEEN irs_limits.super_catch_up_age_min
          AND irs_limits.super_catch_up_age_max THEN irs_limits.super_catch_up_limit
        ELSE irs_limits.catch_up_limit END THEN 'exceeds_modeled_limit'
      WHEN {{ 'NULL' if threshold.amount is none else threshold.amount }} IS NULL
        THEN 'unresolved_threshold'
      WHEN wages IS NULL THEN 'unresolved_wages'
      WHEN wages <= {{ 'NULL' if threshold.amount is none else threshold.amount }}
        THEN 'below_or_equal_threshold'
      WHEN NOT {{ roth_available }} THEN 'blocked_no_roth'
      WHEN basis = 'forecast' OR '{{ threshold.basis }}' = 'projected'
        THEN 'required_under_assumptions'
      ELSE 'required'
    END AS status
  FROM inputs
), allocated AS (
  SELECT total, preferred_roth, year_end_age, catch_up_used, wages, basis, provenance, status,
    CASE
      WHEN status IN ('blocked_no_roth', 'ineligible_catch_up', 'exceeds_modeled_limit')
        THEN NULL
      WHEN status IN ('required', 'required_under_assumptions')
        THEN GREATEST(preferred_roth, catch_up_used)
      ELSE preferred_roth
    END::DECIMAL(18,2) AS roth_amount
  FROM assessed
)
SELECT
  (total - roth_amount)::DECIMAL(18,2) AS pre_tax_contributions,
  roth_amount AS roth_contributions,
  '{{ policy }}'::VARCHAR AS contribution_source_policy,
  {{ fraction }}::DECIMAL(9,8) AS assumed_roth_fraction,
  'source_allocation_v1'::VARCHAR AS contribution_source_version,
  status AS mandatory_roth_status,
  CASE WHEN status IN ('required', 'required_under_assumptions', 'blocked_no_roth') THEN catch_up_used
    WHEN status IN ('no_base_limit_catch_up', 'not_applicable_before_2026',
      'below_or_equal_threshold') THEN 0 END::DECIMAL(18,2) AS mandatory_roth_required,
  CASE WHEN status IN ('required', 'required_under_assumptions') THEN GREATEST(0, catch_up_used - preferred_roth)
    ELSE 0 END::DECIMAL(18,2) AS mandatory_roth_reallocated,
  wages AS prior_year_employer_fica_wages,
  basis AS prior_year_wage_basis,
  provenance AS prior_year_wage_provenance,
  '{{ (source.get('employer_id') or '') | replace("'", "''") }}'::VARCHAR AS source_employer_id,
  {{ year - 1 }} AS source_wage_year,
  year_end_age AS source_year_end_age,
  {{ 'NULL' if threshold.amount is none else threshold.amount }}::DECIMAL(18,2)
    AS mandatory_roth_threshold,
  '{{ threshold.basis }}'::VARCHAR AS mandatory_roth_threshold_basis,
  '{{ threshold.provenance | replace("'", "''") }}'::VARCHAR AS mandatory_roth_threshold_provenance,
  '{{ "sec603_2026_good_faith_v1" if year == 2026 else "sec603_2027_v1" }}'::VARCHAR
    AS mandatory_roth_rule_version,
  'Estimated source election; base-limit catch-up only. Plan-limit and ADP-triggered catch-up unsupported.'
    ::VARCHAR AS contribution_source_assumptions
FROM allocated
{% endmacro %}
