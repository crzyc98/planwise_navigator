# Data Model: Age-Banded Employer Core Contributions

## Configuration entities

### Employer core contribution settings

| Field | Type | Rules |
|---|---|---|
| `status` | enum | Includes `age_banded` in addition to existing modes. |
| `contribution_rate` | decimal fraction | Existing flat fallback rate. |
| `age_schedule` | list of age tiers | Used by direct YAML configuration. Empty is permitted for the specified fallback. |

### Age core tier

| Field | Type | Rules |
|---|---|---|
| `min_age` | non-negative integer | Inclusive lower bound. A nonempty schedule begins at 0. |
| `max_age` | non-negative integer or null | Exclusive upper bound. When present, it must exceed `min_age`; only the final tier may be null. |
| `contribution_rate` | non-negative decimal fraction | Contribution rate, stored in configuration as a decimal such as `0.06`. |

### Studio plan configuration representation

| Field | Type | Rules |
|---|---|---|
| `core_status` | enum | `age_banded` selects the age-tier editor and rendering. |
| `core_age_schedule` | list of age tiers | Serialized with snake-case tier bounds and decimal `contribution_rate`. |

## Derived calculation entities

### Exported dbt schedule

`employer_core_age_schedule` is transient execution configuration. Each tier is `{min_age, max_age, rate}`, where `rate` is a percentage such as `6.0`. It is derived from the decimal configuration rate by multiplying by 100 once.

### Annual core-rate decision

For each employee, scenario, plan design, and simulation year:

1. Use the annual workforce `current_age`.
2. Find the tier where `min_age <= current_age < max_age`, treating null `max_age` as unbounded.
3. Apply that rate to existing eligible/prorated compensation rules.
4. Record the same resolved rate in both the contribution calculation and audit output.

No new persisted relation is introduced. Existing annual intermediate and workforce snapshot outputs retain their schemas.

## Validation and state rules

- A nonempty age-banded schedule is ordered/validated as contiguous coverage from age 0 through an unbounded final tier.
- A gap, overlap, finite range with `min_age >= max_age`, negative rate, or nonfinal unbounded tier fails configuration loading.
- An empty `age_banded` schedule is allowed and resolves to the configured flat core rate.
- Age tiers are evaluated annually, not prorated around a birthday. Mid-year hire proration applies only to the compensation basis.

## Relationships

```text
Direct YAML age_schedule ─┐
                         ├─> validated core settings ─> exported age schedule
Studio core_age_schedule ─┘                                  │
                                                            v
annual workforce current_age ──────────────────────> annual core-rate decision
                                                            │
                                                            ├─> core contribution amount
                                                            └─> audited core contribution rate
```
