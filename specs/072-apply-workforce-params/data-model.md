# Data Model: Apply Workforce Parameters Across Scenarios

**Feature Branch**: `072-apply-workforce-params`
**Date**: 2026-03-16

## Entities

### WorkforceParamsApplyRequest

Request body for the apply endpoint.

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| target_scenario_ids | list[string] | Yes | IDs of scenarios to receive workforce parameters |

### WorkforceParamsApplyResult

Response body showing per-scenario outcome.

| Field | Type | Description |
| ----- | ---- | ----------- |
| source_scenario_id | string | ID of the source scenario |
| results | list[ScenarioApplyOutcome] | Per-target results |
| total_applied | integer | Count of successfully updated scenarios |
| total_failed | integer | Count of failed scenarios |

### ScenarioApplyOutcome

Per-scenario result within the bulk response.

| Field | Type | Description |
| ----- | ---- | ----------- |
| scenario_id | string | Target scenario ID |
| scenario_name | string | Target scenario name (for display) |
| success | boolean | Whether the apply succeeded |
| error | string or null | Error message if failed |

## Workforce Parameter Categories

The following backend config keys are classified as "workforce parameters" and will be copied:

### Category: Growth
- `simulation.target_growth_rate`

### Category: Workforce/Turnover
- `workforce.total_termination_rate`
- `workforce.new_hire_termination_rate`

### Category: Compensation
- `compensation.merit_budget_percent`
- `compensation.cola_rate_percent`
- `compensation.promotion_increase_percent`
- `compensation.promotion_distribution_range_percent`
- `compensation.promotion_budget_percent`
- `compensation.promotion_rate_multiplier`
- `compensation.target_compensation_growth_percent`

### Category: New Hire Demographics
- `new_hire.strategy`
- `new_hire.target_percentile`
- `new_hire.compensation_variance_percent`
- `new_hire.market_scenario`
- `new_hire.age_distribution`
- `new_hire.level_distribution_mode`
- `new_hire.level_distribution`
- `new_hire.job_level_compensation`
- `new_hire.level_market_adjustments`

### Category: Seed Configs (atomic replacement)
- `promotion_hazard` (top-level)
- `age_bands` (top-level)
- `tenure_bands` (top-level)

## Excluded Parameters (DC Plan + Identity + Infrastructure)

These keys are NEVER modified by this feature:

- `dc_plan.*` — all DC plan parameters
- `simulation.name`, `simulation.start_year`, `simulation.end_year`, `simulation.random_seed`
- `data_sources.*`
- `advanced.*`

## State Transitions

No new state machines. The operation is a one-shot bulk update with no intermediate states. Each target scenario's `config_overrides` transitions from its previous value to the merged value in a single write.
