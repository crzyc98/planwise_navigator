{#
  Match-Magnet Snap (Feature 102)

  Shared snap decision for both voluntary-enrollment models so the logic
  cannot drift between them. Raises a below-ceiling deferral rate UP to the
  match ceiling for a deterministic fraction of enrollees; never lowers a
  rate (selected_rate is preserved when it already meets/exceeds the ceiling
  or when the magnet does not fire).

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

{% macro match_magnet_snap(selected_rate, ceiling, magnet_random, enabled, snap_prob) %}
CASE
  WHEN {{ enabled }}
    AND {{ ceiling }} > 0
    AND {{ selected_rate }} < {{ ceiling }}
    AND {{ magnet_random }} < {{ snap_prob }}
  THEN {{ ceiling }}
  ELSE {{ selected_rate }}
END
{% endmacro %}
