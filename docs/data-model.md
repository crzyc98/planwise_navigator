# Data Model

## Events

All event payloads are Pydantic v2 models in `planalign_core/events/`, organized by
domain. Every event carries `employee_id`, `scenario_id`, `plan_design_id`, an
effective date, and a UUID; money uses `Decimal`.

### Workforce events (`planalign_core/events/workforce.py`)

| Payload | Meaning |
|---------|---------|
| `HirePayload` | New employee onboarding (department, level, compensation) |
| `TerminationPayload` | Departure with reason code |
| `PromotionPayload` | Level/band change with comp adjustment |
| `MeritPayload` | Salary changes (COLA, merit, market adjustment) |
| `SabbaticalPayload` | Example custom event type (generator template) |

### DC-plan events (`planalign_core/events/dc_plan.py`)

| Payload | Meaning |
|---------|---------|
| `EligibilityPayload` | Retirement-plan eligibility determination |
| `EnrollmentPayload` | Plan enrollment (deferral rate, investment election) |
| `EnrollmentChangePayload` | Deferral-rate / election changes |
| `AutoEnrollmentWindowPayload` | Auto-enrollment window events |
| `ContributionPayload` | Employee/employer contributions |
| `VestingPayload` | Vesting schedule progression |

### Plan-administration events (`planalign_core/events/admin.py`)

| Payload | Meaning |
|---------|---------|
| `ForfeiturePayload` | Forfeiture processing |
| `HCEStatusPayload` | Highly Compensated Employee determination |
| `ComplianceEventPayload` | IRS/compliance events |

Factories (`planalign_core/events/core.py`) construct validated events:

```python
from planalign_core.events import WorkforceEventFactory
from decimal import Decimal
from datetime import date

event = WorkforceEventFactory.create_hire_event(
    employee_id="EMP_2025_001",
    scenario_id="baseline_2025",
    plan_design_id="standard_401k",
    hire_date=date(2025, 1, 15),
    department="Engineering",
    job_level=3,
    annual_compensation=Decimal("125000.00"),
)
```

## Key tables (dbt marts)

| Table | Grain | Role |
|-------|-------|------|
| `fct_yearly_events` | one row per event | **System of record.** Append-only, incremental by (scenario, plan design, employee, year) |
| `fct_workforce_snapshot` | employee × year | Point-in-time workforce state projected from events |
| `fct_employer_match_events` | match contribution events | Employer match results (incl. tenure-graded formulas) |
| `fct_compensation_growth` | year | Compensation growth mart used by calibration (S051) |
| `fct_payroll_ledger` / `dim_payroll_calendar` | pay period | Payroll-level detail |
| `dim_hazard_table` | age × tenure × level bands | Termination/promotion hazard rates |

Standard join keys: `(scenario_id, plan_design_id, employee_id)` plus
`simulation_year` where relevant.

## Band conventions

Age and tenure bands come from seeds (`dbt/seeds/config_age_bands.csv`,
`config_tenure_bands.csv`) applied via the `assign_age_band()` /
`assign_tenure_band()` macros. Intervals are **[min, max)** — lower bound inclusive,
upper bound exclusive (age 35 → the 35+ band, not the 25–34 band).

## Querying

```bash
duckdb dbt/simulation.duckdb "SELECT event_type, COUNT(*) FROM fct_yearly_events GROUP BY 1"
duckdb dbt/simulation.duckdb "SELECT * FROM fct_workforce_snapshot LIMIT 10"
```

From Python, always resolve the path via
`planalign_orchestrator.config.get_database_path()` (honors `DATABASE_PATH`).
