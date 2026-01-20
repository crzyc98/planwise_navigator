# Data Model: Fix Current Tenure Calculation

**Feature**: 020-fix-tenure-calculation
**Date**: 2026-01-20

## Entities

### Employee (existing)

No schema changes required. The `current_tenure` field already exists.

| Field | Type | Description |
|-------|------|-------------|
| employee_id | VARCHAR | Primary identifier |
| employee_hire_date | DATE | Original hire date from census |
| current_tenure | INTEGER | **Calculated**: Years of service as of 12/31 of simulation year |

### Calculation Rules

#### Initial Tenure (Year 1)

```
current_tenure = FLOOR((simulation_year_end_date - hire_date) / 365.25)

Where:
- simulation_year_end_date = December 31 of simulation year
- hire_date = employee_hire_date from census
- Result is truncated to integer (not rounded)
```

**Edge Cases**:
| Condition | Result |
|-----------|--------|
| hire_date IS NULL | 0 |
| hire_date > simulation_year_end_date | 0 |
| hire_date = simulation_year_end_date | 0 |
| Normal case | FLOOR((end_date - hire_date) / 365.25) |

#### Year-over-Year (Year 2+)

```
current_tenure = previous_year_tenure + 1
```

For continuing employees (not terminated in prior year), tenure increments by exactly 1.

#### New Hires (Mid-Simulation)

```
current_tenure = FLOOR((simulation_year_end_date - hire_date) / 365.25)
```

New hires generated during the simulation use the same formula as initial tenure.

## State Transitions

```
┌─────────────────────────────────────────────────────────────────┐
│                      Tenure State Machine                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    Year N → Year N+1    ┌──────────────────┐  │
│  │   Census     │ ─────────────────────► │  Continuing      │  │
│  │  Employee    │   Initial calculation    │   Employee       │  │
│  │  tenure = T  │   T = floor((end-hire)   │   tenure = T+1   │  │
│  │              │       / 365.25)          │                  │  │
│  └──────────────┘                          └──────────────────┘  │
│                                                     │            │
│                                                     │ Year N+1   │
│                                                     │ → Year N+2 │
│                                                     ▼            │
│                                            ┌──────────────────┐  │
│                                            │   tenure = T+2   │  │
│                                            └──────────────────┘  │
│                                                                  │
│  ┌──────────────┐    Same Year              ┌──────────────────┐ │
│  │   New Hire   │ ──────────────────────► │   New Employee   │ │
│  │  Generated   │   T = floor((end-hire)   │   tenure = T     │ │
│  │              │       / 365.25)          │   (often 0)      │ │
│  └──────────────┘                          └──────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Validation Rules

| Rule ID | Rule | Error Action |
|---------|------|--------------|
| VR-001 | tenure >= 0 | Fail validation |
| VR-002 | tenure <= 70 | Warn (likely data error) |
| VR-003 | hire_date NOT NULL for census employees | Warn, default tenure to 0 |
| VR-004 | SQL tenure = Polars tenure | Fail (mode parity violation) |

## Downstream Dependencies

Models that consume `current_tenure`:

| Model | Usage |
|-------|-------|
| `int_employer_core_contributions.sql` | Service-based contribution tiers |
| `dim_hazard_table.sql` | Tenure-based termination probabilities |
| `int_promotion_events.sql` | Tenure-based promotion eligibility |
| `fct_workforce_snapshot.sql` | Final tenure value in snapshot |
| `assign_tenure_band.sql` (macro) | Tenure band classification |

## Tenure Bands (Reference)

From `config_tenure_bands.csv`:

| Band | min_value | max_value | Interpretation |
|------|-----------|-----------|----------------|
| < 2 | 0 | 2 | tenure in [0, 2) |
| 2-4 | 2 | 5 | tenure in [2, 5) |
| 5-9 | 5 | 10 | tenure in [5, 10) |
| 10-19 | 10 | 20 | tenure in [10, 20) |
| 20+ | 20 | NULL | tenure >= 20 |

**Convention**: [min, max) - lower bound inclusive, upper bound exclusive
