{#
  Match-Magnet Snap (Feature 102)

  Shared snap decision for both voluntary-enrollment models so the logic
  cannot drift between them. Raises a below-ceiling deferral rate UP to the
  match ceiling for a deterministic fraction of enrollees; never lowers a
  rate by default. Optional downward snapping applies only in AE plans, for
  rates above the ceiling and at or below the AE default. Both directions use
  the same draw. Callers exclude deliberate below-default choices beforehand.

  Returns the snapped (UNBOUNDED) rate — callers apply the configurable
  floor/cap (`GREATEST(0.01, LEAST(voluntary_max_deferral_rate, ...))`)
  afterward so the pre-cap value remains available for audit.

  Arguments:
    - selected_rate: SQL expr/column for the demographically-assigned rate
    - ceiling: SQL expr/column for the per-employee match ceiling
    - magnet_random: SQL expr/column with a deterministic [0,1) draw
    - enabled: Jinja boolean (renders True/False)
    - snap_prob: numeric literal fraction in [0,1]
#}

{% macro match_magnet_snap(selected_rate, ceiling, magnet_random, enabled, snap_prob,
                          downward_enabled=false, auto_default=none, upward_enabled=true) %}
CASE
  WHEN {{ enabled }}
    AND {{ ceiling }} > 0
    {% if upward_enabled %}
    AND {{ selected_rate }} < {{ ceiling }}
    {% else %}
    AND FALSE
    {% endif %}
    AND {{ magnet_random }} < {{ snap_prob }}
  THEN {{ ceiling }}
  {% if downward_enabled and auto_default is not none %}
  WHEN {{ enabled }}
    AND {{ ceiling }} > 0
    AND {{ ceiling }} < {{ auto_default }}
    AND {{ selected_rate }} > {{ ceiling }}
    AND {{ selected_rate }} <= {{ auto_default }}
    AND {{ magnet_random }} < {{ snap_prob }}
  THEN {{ ceiling }}
  {% endif %}
  ELSE {{ selected_rate }}
END
{% endmacro %}
