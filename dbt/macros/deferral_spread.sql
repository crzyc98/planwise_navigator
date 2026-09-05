{#
  Issue #652: upward-only deferral-rate spread.

  The demographic deferral table assigns every member of a cell the identical
  rate, so a cell renders as a single spike -- 264 of 621 new hires in the
  reproduction all sat at exactly 6%. Real elections scatter.

  The table value is treated as a FLOOR, not a centre: employees move up from
  it, never down. Decided with the analyst (D5). Weights decay from the floor:

      +0pp  40%   <- floor stays the most common single outcome
      +1pp  30%
      +2pp  15%
      +3pp  10%
      +4pp   5%

  This raises the cell average by roughly 1.1 percentage points, which is
  intended (D6): today's averages are artificially low precisely because
  everyone sits on the floor.

  `max_lift` is in whole percentage points. 0 (the default) disables the
  spread entirely and returns the base rate untouched, so existing scenarios
  are unaffected until an analyst opts in. A max_lift below 4 caps the draw,
  piling the remaining mass at the cap.

  `spread_random` MUST be drawn from its own seed. Reusing the match-magnet
  draw would correlate "spread upward" with "snapped to the match ceiling"
  and produce a lopsided distribution that still looks plausible.
#}
{% macro deferral_spread(base_rate, spread_random, max_lift) %}
{%- if max_lift is none or max_lift|int <= 0 -%}
{{ base_rate }}
{%- else -%}
({{ base_rate }} + LEAST(
  CASE
    WHEN {{ spread_random }} < 0.40 THEN 0
    WHEN {{ spread_random }} < 0.70 THEN 1
    WHEN {{ spread_random }} < 0.85 THEN 2
    WHEN {{ spread_random }} < 0.95 THEN 3
    ELSE 4
  END,
  {{ max_lift|int }}
) * 0.01)
{%- endif -%}
{% endmacro %}
