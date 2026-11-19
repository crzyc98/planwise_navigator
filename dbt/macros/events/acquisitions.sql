{% macro acquisitions_joining(simulation_year) %}
  {#-
    Acquisitions (#1226) whose effective date falls in simulation_year.

    Reads the `acquisitions` var exported from workforce.acquisitions. Each
    entry keeps its 1-based position in the configured list as `ordinal`,
    which fixes the member SSN block. Returns an empty list when none join.
  -#}
  {%- set joining = [] -%}
  {%- for item in var('acquisitions', []) -%}
    {%- if ((item['effective_date'] | string)[:4] | int) == (simulation_year | int) -%}
      {%- do joining.append({
        'id': item['id'],
        'headcount': item['headcount'] | int,
        'effective_date': item['effective_date'] | string,
        'ordinal': loop.index,
        'service_credit': item.get('service_credit', 'prior_service'),
        'average_pay': item.get('average_pay'),
        'relative_pay': item.get('relative_pay'),
        'average_age': item.get('average_age'),
        'average_service': item.get('average_service')
      }) -%}
    {%- endif -%}
  {%- endfor -%}
  {{ return(joining) }}
{% endmacro %}


{% macro acquisitions_where(setting, value, default) %}
  {#- Configured acquisitions (#1227) whose plan setting equals value. -#}
  {%- set matched = [] -%}
  {%- for item in var('acquisitions', []) -%}
    {%- if item.get(setting, default) == value -%}
      {%- do matched.append(item) -%}
    {%- endif -%}
  {%- endfor -%}
  {{ return(matched) }}
{% endmacro %}


{% macro acquisitions_with_starting_participation() %}
  {#- Acquisitions (#1227) whose members start with a set participation. -#}
  {%- set matched = [] -%}
  {%- for item in var('acquisitions', []) -%}
    {%- if item.get('starting_participation_rate') is not none -%}
      {%- do matched.append(item) -%}
    {%- endif -%}
  {%- endfor -%}
  {{ return(matched) }}
{% endmacro %}


{% macro acquisition_member_id(acquisition_id, member_seq) -%}
  'ACQ_' || {{ acquisition_id }} || '_' || LPAD(CAST({{ member_seq }} AS VARCHAR), 6, '0')
{%- endmacro %}


{% macro acquisition_id_of(employee_id, acquisitions=none) -%}
  {#-
    The acquisition a member joined with, or NULL (#1227). Matches the exact
    id form acquisition_member_id builds, for the given acquisitions (all
    configured ones by default). Plan-stage models read employees from tables
    that do not carry acquisition_id, so membership is read from the id.
  -#}
  {%- set items = var('acquisitions', []) if acquisitions is none else acquisitions -%}
  {%- if items -%}
  NULLIF(regexp_extract({{ employee_id }}, '^ACQ_({{ items | map(attribute='id') | join('|') }})_[0-9]{6}$', 1), '')
  {%- else -%}
  CAST(NULL AS VARCHAR)
  {%- endif -%}
{%- endmacro %}


{% macro acquisition_cohort(employee_id) -%}
  {#-
    Extra PARTITION BY key that keeps acquired members (#1227) in a cohort of
    their own, so cohort-normalized draws for everyone else match a run
    without the acquisition. Renders nothing when no acquisition is set.
  -#}
  {%- if var('acquisitions', []) -%}, {{ acquisition_id_of(employee_id) }}{%- endif -%}
{%- endmacro %}


{% macro carried_tenure_at(hire_date_column, year_end_tenure_column, simulation_year, end_date) %}
  {#-
    Service at end_date for an employee whose tenure does not start at the
    hire date (acquired members carry prior service, #1226). Year-end tenure
    advances by one per simulated year, so taking off the years since the hire
    year gives the service carried in, which is then added to the years served
    up to end_date.
  -#}
  GREATEST(0,
    {{ year_end_tenure_column }}
    - ({{ simulation_year }} - YEAR({{ hire_date_column }}))
    + {{ calculate_tenure(hire_date_column, end_date) }}
  )
{% endmacro %}
