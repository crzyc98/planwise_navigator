# dbt Variable Contract: Enrollment Match Magnet

**Feature**: 084-fix-match-magnet
**Type**: Configuration interface (dbt variables)
**Consumers**: `int_voluntary_enrollment_decision.sql`, `int_proactive_voluntary_enrollment.sql`

## New Variables (this feature)

| Variable | Type | Default | Valid Range | Description |
|----------|------|---------|-------------|-------------|
| `enrollment_match_magnet_enabled` | boolean | `true` | `true` / `false` | Enables or disables the match-threshold attraction effect at enrollment. When `false`, enrollment deferral rates are determined purely by the demographic matrix (pre-fix baseline behavior). |
| `enrollment_match_magnet_probability` | decimal | `0.45` | `0.0` – `1.0` | Fraction of enrollees whose demographic-based rate falls below the match-maximizing rate who will elect exactly the match-maximizing rate instead. |

## Upstream Variables (read-only, exported by orchestrator)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `employer_match_status` | string | `'deferral_based'` | Match formula mode. Magnet only activates for `'deferral_based'`. |
| `deferral_match_response_match_max_rate` | decimal or `none` | `none` | Pre-computed match-maximizing deferral rate from orchestrator. Used as primary source. |
| `match_tiers` | list | `[{employee_min:0.00, employee_max:0.03, match_rate:1.00}, ...]` | Jinja fallback: iterate tiers to find max `employee_max`. |

## Behavior Matrix

| `enabled` | `match_max_rate` | Employee rate vs threshold | Outcome |
|-----------|-----------------|---------------------------|---------|
| `false` | any | any | No magnet effect; pure demographic rate |
| `true` | `0.0` | any | No magnet effect (no match or non-deferral-based) |
| `true` | `> 0` | rate ≥ threshold | No change; magnet is upward-only |
| `true` | `> 0` | rate < threshold | Snap to `match_max_rate` with probability `magnet_probability` |

## Override Example

```yaml
# High-literacy workforce scenario (override in scenario config or --vars):
enrollment_match_magnet_enabled: true
enrollment_match_magnet_probability: 0.70

# Disable for backward-compatibility comparison:
enrollment_match_magnet_enabled: false
```
