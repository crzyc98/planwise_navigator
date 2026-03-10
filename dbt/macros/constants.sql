{# ============================================================
   Domain Constants Macros
   ============================================================
   Centralized string literals for the PlanAlign dbt project.
   Eliminates duplicated magic strings flagged by SonarQube.

   Naming convention:
     - status_*()       → employment status values
     - evt_*()          → lowercase event types (event stream layer)
     - EVT_*()          → UPPERCASE event types (seed/parameter layer)
     - cat_*()          → event category values
     - dq_*()           → data quality flag values
     - default_*()      → default identifiers

   Composite helpers:
     - event_priority(col)            → CASE for event sort order
     - event_category_from_type(col)  → CASE mapping event_type → category
     - is_compensation_event(col)     → IN-list for comp-affecting events
     - is_enrollment_event(col)       → IN-list for enrollment events
#}

{# ── Status constants ─────────────────────────────────── #}

{% macro status_active() %}'active'{% endmacro %}
{% macro status_terminated() %}'terminated'{% endmacro %}

{# ── Event types (lowercase – event stream layer) ─────── #}

{% macro evt_hire() %}'hire'{% endmacro %}
{% macro evt_termination() %}'termination'{% endmacro %}
{% macro evt_promotion() %}'promotion'{% endmacro %}
{% macro evt_raise() %}'raise'{% endmacro %}
{% macro evt_merit() %}'merit'{% endmacro %}
{% macro evt_enrollment() %}'enrollment'{% endmacro %}
{% macro evt_enrollment_change() %}'enrollment_change'{% endmacro %}
{% macro evt_deferral_escalation() %}'deferral_escalation'{% endmacro %}
{% macro evt_deferral_match_response() %}'deferral_match_response'{% endmacro %}
{% macro evt_eligibility() %}'eligibility'{% endmacro %}
{% macro evt_initial_state() %}'initial_state'{% endmacro %}

{# ── Event types (UPPERCASE – seed/parameter layer) ───── #}

{% macro EVT_HIRE() %}'HIRE'{% endmacro %}
{% macro EVT_TERMINATION() %}'TERMINATION'{% endmacro %}
{% macro EVT_PROMOTION() %}'PROMOTION'{% endmacro %}
{% macro EVT_RAISE() %}'RAISE'{% endmacro %}
{% macro EVT_MERIT() %}'MERIT'{% endmacro %}
{% macro EVT_ENROLLMENT() %}'ENROLLMENT'{% endmacro %}

{# ── Event categories ─────────────────────────────────── #}

{% macro cat_workforce() %}'workforce'{% endmacro %}
{% macro cat_compensation() %}'compensation'{% endmacro %}
{% macro cat_benefits() %}'benefits'{% endmacro %}

{# ── Data quality ─────────────────────────────────────── #}

{% macro dq_valid() %}'VALID'{% endmacro %}

{# ── Defaults ─────────────────────────────────────────── #}

{% macro default_scenario() %}'default'{% endmacro %}

{# ============================================================
   Composite Helpers
   ============================================================ #}

{# Event priority CASE – maps event_type to sort order (1-11).
   Used for conflict resolution when multiple events occur on the same day. #}
{% macro event_priority(col) %}
CASE {{ col }}
  WHEN {{ evt_termination() }} THEN 1
  WHEN {{ evt_hire() }} THEN 2
  WHEN {{ evt_eligibility() }} THEN 3
  WHEN {{ evt_enrollment() }} THEN 4
  WHEN {{ evt_enrollment_change() }} THEN 5
  WHEN {{ evt_deferral_match_response() }} THEN 6
  WHEN {{ evt_deferral_escalation() }} THEN 7
  WHEN {{ evt_promotion() }} THEN 8
  WHEN {{ evt_raise() }} THEN 9
  WHEN {{ evt_merit() }} THEN 10
  ELSE 11
END
{% endmacro %}

{# Event category CASE – maps event_type to its category. #}
{% macro event_category_from_type(col) %}
CASE
  WHEN {{ col }} IN ({{ evt_hire() }}, {{ evt_termination() }}) THEN {{ cat_workforce() }}
  WHEN {{ col }} IN ({{ evt_promotion() }}, {{ evt_merit() }}) THEN {{ cat_compensation() }}
  WHEN {{ col }} LIKE '%enrollment%' THEN {{ cat_benefits() }}
  WHEN {{ col }} LIKE 'deferral%' THEN {{ cat_benefits() }}
  ELSE 'other'
END
{% endmacro %}

{# Returns TRUE when col is a compensation-affecting event type. #}
{% macro is_compensation_event(col) %}
{{ col }} IN ({{ evt_hire() }}, {{ evt_promotion() }}, {{ evt_raise() }})
{% endmacro %}

{# Returns TRUE when col is an enrollment-related event type. #}
{% macro is_enrollment_event(col) %}
{{ col }} IN ({{ evt_enrollment() }}, {{ evt_enrollment_change() }})
{% endmacro %}
