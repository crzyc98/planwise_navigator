{% macro contribution_source_allocation() %}
{# Correlated reporting allocation. Totals/events are never mutated here. #}
{% set source = var('contribution_sources', {}) %}
{% set policy = source.get('policy', 'legacy_estimate') %}
{% set fraction = source.get('roth_fraction', 0.15) | float %}
{% set enabled = source.get('mandatory_roth_enabled', false) %}
{% set roth_available = source.get('roth_available', true) %}
{% set year = var('simulation_year', 2025) | int %}
{% set threshold = namespace(amount=none, provenance=none) %}
{% for item in source.get('projected_thresholds', []) if item.year == year %}
  {% set threshold.amount = item.threshold | float %}
  {% set threshold.provenance = item.provenance %}
{% endfor %}
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
    COALESCE({{ year }} - YEAR(composed.employee_birth_date), composed.current_age)
      AS year_end_age,
    GREATEST(0, ROUND(composed.annual_contribution_amount - irs_limits.base_limit, 2))
      AS catch_up_used,
    CASE WHEN wages IS NULL AND composed.employee_hire_date >= DATE '{{ year }}-01-01'
      THEN 0::DECIMAL(18,2) ELSE wages END AS wages,
    CASE WHEN wages IS NULL AND composed.employee_hire_date >= DATE '{{ year }}-01-01'
      THEN 'structural' ELSE basis END AS basis,
    CASE WHEN wages IS NULL AND composed.employee_hire_date >= DATE '{{ year }}-01-01'
      THEN 'No prior-year wages from this employer for a current-year hire'
      ELSE provenance END AS provenance
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
      WHEN COALESCE({{ 'NULL' if threshold.amount is none else threshold.amount }},
        irs_limits.roth_catch_up_wage_threshold) IS NULL
        THEN 'unresolved_threshold'
      WHEN wages IS NULL THEN 'unresolved_wages'
      WHEN wages <= COALESCE({{ 'NULL' if threshold.amount is none else threshold.amount }},
        irs_limits.roth_catch_up_wage_threshold)
        THEN 'below_or_equal_threshold'
      WHEN NOT {{ roth_available }} THEN 'blocked_no_roth'
      WHEN basis = 'forecast' OR {{ 'TRUE' if threshold.amount is not none else 'irs_limits.is_estimated' }}
        THEN 'required_under_assumptions'
      ELSE 'required'
    END AS status
  FROM inputs
), allocated AS (
  SELECT total, preferred_roth, year_end_age, catch_up_used, wages, basis, provenance, status,
    CASE
      WHEN status IN ('blocked_no_roth', 'ineligible_catch_up') THEN 0
      WHEN status = 'exceeds_modeled_limit' THEN
        LEAST(preferred_roth, GREATEST(0, CASE WHEN year_end_age BETWEEN irs_limits.super_catch_up_age_min
          AND irs_limits.super_catch_up_age_max THEN irs_limits.super_catch_up_limit
          ELSE irs_limits.catch_up_limit END - irs_limits.base_limit))
      WHEN status IN ('required', 'required_under_assumptions')
        THEN GREATEST(preferred_roth, catch_up_used)
      ELSE preferred_roth
    END::DECIMAL(18,2) AS roth_amount,
    CASE
      WHEN status IN ('blocked_no_roth', 'ineligible_catch_up') THEN catch_up_used
      WHEN status = 'exceeds_modeled_limit' THEN GREATEST(0, total -
        CASE WHEN year_end_age BETWEEN irs_limits.super_catch_up_age_min
          AND irs_limits.super_catch_up_age_max THEN irs_limits.super_catch_up_limit
          ELSE irs_limits.catch_up_limit END)
      ELSE 0
    END::DECIMAL(18,2) AS disallowed_catch_up_contributions
  FROM assessed
)
SELECT
  (total - roth_amount - disallowed_catch_up_contributions)::DECIMAL(18,2)
    AS pre_tax_contributions,
  roth_amount AS roth_contributions,
  disallowed_catch_up_contributions,
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
  COALESCE({{ 'NULL' if threshold.amount is none else threshold.amount }},
    irs_limits.roth_catch_up_wage_threshold)::DECIMAL(18,2)
    AS mandatory_roth_threshold,
  CASE WHEN {{ 'TRUE' if threshold.amount is not none else 'FALSE' }} OR irs_limits.is_estimated
    THEN 'projected' ELSE 'published' END::VARCHAR AS mandatory_roth_threshold_basis,
  {{ ("'" ~ (threshold.provenance | replace("'", "''")) ~ "'") if threshold.provenance is not none else "CASE WHEN irs_limits.is_estimated THEN 'IRS seed planning estimate' ELSE 'IRS Notice 2025-67' END" }}::VARCHAR AS mandatory_roth_threshold_provenance,
  CASE
    WHEN {{ year }} < 2026 THEN 'not_applicable_before_2026'
    WHEN irs_limits.limit_year = 2026 THEN 'sec603_2026_good_faith_v1'
    ELSE 'sec603_' || irs_limits.limit_year::VARCHAR || '_v1'
  END::VARCHAR
    AS mandatory_roth_rule_version,
  'Estimated source election; base-limit catch-up only. Plan-limit and ADP-triggered catch-up unsupported.'
    ::VARCHAR AS contribution_source_assumptions
FROM allocated
{% endmacro %}
