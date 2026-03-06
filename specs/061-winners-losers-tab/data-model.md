# Data Model: Winners & Losers Comparison Tab

## Entities

### WinnersLosersRequest (API Input)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| workspace_id | str | yes | Path param — workspace context |
| plan_a | str | yes | Query param — scenario ID for Plan A (reference) |
| plan_b | str | yes | Query param — scenario ID for Plan B (alternative) |

### EmployeeComparison (Internal)

| Field | Type | Description |
|-------|------|-------------|
| employee_id | str | Matched across both scenarios |
| age_band | str | From Plan A snapshot (same in both) |
| tenure_band | str | From Plan A snapshot (same in both) |
| plan_a_employer_total | Decimal | employer_match_amount + employer_core_amount in Plan A |
| plan_b_employer_total | Decimal | employer_match_amount + employer_core_amount in Plan B |
| delta | Decimal | plan_b_employer_total - plan_a_employer_total |
| status | str | "winner" / "loser" / "neutral" |

### BandGroupResult (API Output)

| Field | Type | Description |
|-------|------|-------------|
| band_label | str | Age band or tenure band label |
| winners | int | Count of winners in this band |
| losers | int | Count of losers in this band |
| neutral | int | Count of neutral in this band |
| total | int | Total employees in this band |

### HeatmapCell (API Output)

| Field | Type | Description |
|-------|------|-------------|
| age_band | str | Row label |
| tenure_band | str | Column label |
| winners | int | Winner count in this cell |
| losers | int | Loser count in this cell |
| neutral | int | Neutral count in this cell |
| total | int | Total employees in this cell |
| net_pct | float | (winners - losers) / total * 100 |

### WinnersLosersResponse (API Output)

| Field | Type | Description |
|-------|------|-------------|
| plan_a_scenario_id | str | Plan A scenario ID |
| plan_b_scenario_id | str | Plan B scenario ID |
| final_year | int | The simulation year used for comparison |
| total_compared | int | Employees present in both scenarios |
| total_excluded | int | Employees in only one scenario |
| total_winners | int | Total winners |
| total_losers | int | Total losers |
| total_neutral | int | Total neutral |
| age_band_results | list[BandGroupResult] | Breakdown by age band |
| tenure_band_results | list[BandGroupResult] | Breakdown by tenure band |
| heatmap | list[HeatmapCell] | Age x tenure grid cells |

## Data Flow

```
Plan A DB ──→ fct_workforce_snapshot (final year, active) ──→ employee_id, age_band, tenure_band, employer contributions
                                                                    │
                                                              INNER JOIN on employee_id
                                                                    │
Plan B DB ──→ fct_workforce_snapshot (final year, active) ──→ employee_id, employer contributions
                                                                    │
                                                              Compute delta, classify winner/loser/neutral
                                                                    │
                                                              Aggregate by age_band, tenure_band, age×tenure
                                                                    │
                                                              WinnersLosersResponse
```

## Source Table: fct_workforce_snapshot

Key columns used:
- `employee_id` — join key across scenarios
- `simulation_year` — filter to MAX year
- `employment_status` — filter to 'active' (FR-010)
- `employer_match_amount` — employer match $ value
- `employer_core_amount` — employer core $ value
- `age_band` — pre-assigned age band label
- `tenure_band` — pre-assigned tenure band label
