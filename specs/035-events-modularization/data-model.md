# Data Model: Events Module Modularization

**Feature**: 035-events-modularization
**Date**: 2026-02-06

## Overview

This refactoring does not change the data model - it reorganizes existing Pydantic models into domain-specific modules. All models, fields, and validation behavior remain identical.

## Module Organization

### Validators Module (`config/events/validators.py`)

Standalone functions for Decimal precision standardization:

```python
def quantize_amount(v: Decimal) -> Decimal:
    """Quantize monetary amounts to 6 decimal places (18,6 precision)."""
    return v.quantize(Decimal("0.000001"))

def quantize_rate(v: Decimal) -> Decimal:
    """Quantize rates/percentages to 4 decimal places."""
    return v.quantize(Decimal("0.0001"))

def quantize_amount_dict(d: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Quantize all values in a source balance dictionary."""
    return {k: quantize_amount(v) for k, v in d.items()}
```

### Workforce Payloads (`config/events/workforce.py`)

| Class | Fields | Validators Used |
|-------|--------|-----------------|
| HirePayload | event_type, plan_id, hire_date, department, job_level, annual_compensation | quantize_amount |
| PromotionPayload | event_type, plan_id, new_job_level, new_annual_compensation, effective_date | quantize_amount |
| TerminationPayload | event_type, plan_id, termination_reason, final_pay_date | (none) |
| MeritPayload | event_type, plan_id, new_compensation, merit_percentage | quantize_amount, quantize_rate |
| SabbaticalPayload | event_type, plan_id, start_date, end_date, reason, compensation_percentage | quantize_rate |

### DC Plan Payloads (`config/events/dc_plan.py`)

| Class | Fields | Validators Used |
|-------|--------|-----------------|
| EligibilityPayload | event_type, plan_id, eligible, eligibility_date, reason | (none) |
| EnrollmentPayload | event_type, plan_id, enrollment_date, pre_tax_contribution_rate, roth_contribution_rate, after_tax_contribution_rate, auto_enrollment, opt_out_window_expires, enrollment_source, auto_enrollment_window_start, auto_enrollment_window_end, proactive_enrollment_eligible, window_timing_compliant | quantize_rate |
| ContributionPayload | event_type, plan_id, source, amount, pay_period_end, contribution_date, ytd_amount, payroll_id, irs_limit_applied, inferred_value | quantize_amount |
| VestingPayload | event_type, plan_id, vested_percentage, source_balances_vested, vesting_schedule_type, service_computation_date, service_credited_hours, service_period_end_date | quantize_rate, quantize_amount_dict |
| AutoEnrollmentWindowPayload | event_type, plan_id, window_action, window_start_date, window_end_date, window_duration_days, default_deferral_rate, eligible_for_proactive, proactive_window_end | quantize_rate |
| EnrollmentChangePayload | event_type, plan_id, change_type, change_reason, previous_enrollment_date, new_pre_tax_rate, new_roth_rate, previous_pre_tax_rate, previous_roth_rate, within_opt_out_window, penalty_applied | quantize_rate |

### Admin Payloads (`config/events/admin.py`)

| Class | Fields | Validators Used |
|-------|--------|-----------------|
| ForfeiturePayload | event_type, plan_id, forfeited_from_source, amount, reason, vested_percentage | quantize_amount, quantize_rate |
| HCEStatusPayload | event_type, plan_id, determination_method, ytd_compensation, annualized_compensation, hce_threshold, is_hce, determination_date, prior_year_hce | quantize_amount |
| ComplianceEventPayload | event_type, plan_id, compliance_type, limit_type, applicable_limit, current_amount, monitoring_date | quantize_amount |

### Core Module (`config/events/core.py`)

| Class | Description |
|-------|-------------|
| SimulationEvent | Core event model with discriminated union payload |
| EventFactory | Base factory with create_event and validate_schema |
| WorkforceEventFactory | Factory for workforce events (hire, promotion, termination, merit) |
| DCPlanEventFactory | Factory for DC plan events (eligibility, enrollment, contribution, vesting, auto-enrollment) |
| PlanAdministrationEventFactory | Factory for admin events (forfeiture, HCE status, compliance) |
| LegacySimulationEvent | Alias for SimulationEvent (backward compatibility) |

## Import Dependencies

```
validators.py
    │
    ├──> workforce.py (imports: quantize_amount, quantize_rate)
    ├──> dc_plan.py   (imports: quantize_amount, quantize_rate, quantize_amount_dict)
    └──> admin.py     (imports: quantize_amount, quantize_rate)
            │
            v
        core.py (imports all payloads)
            │
            v
        __init__.py / events.py (re-exports all symbols)
```

## Compatibility Layer (`config/events.py`)

The existing file becomes a thin re-export layer:

```python
# Re-export all symbols from submodules
from config.events.validators import quantize_amount, quantize_rate, quantize_amount_dict
from config.events.workforce import (
    HirePayload, PromotionPayload, TerminationPayload, MeritPayload, SabbaticalPayload
)
from config.events.dc_plan import (
    EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload,
    AutoEnrollmentWindowPayload, EnrollmentChangePayload
)
from config.events.admin import (
    ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload
)
from config.events.core import (
    SimulationEvent, LegacySimulationEvent,
    EventFactory, WorkforceEventFactory, DCPlanEventFactory, PlanAdministrationEventFactory
)

# Re-export from orchestrator (unchanged)
from planalign_orchestrator.generators import (
    EventRegistry, EventGenerator, EventContext, ValidationResult, GeneratorMetrics
)

__all__ = [
    # Core event models
    "SimulationEvent",
    "LegacySimulationEvent",
    # Payload types
    "HirePayload",
    "PromotionPayload",
    "TerminationPayload",
    "MeritPayload",
    "EligibilityPayload",
    "EnrollmentPayload",
    "ContributionPayload",
    "VestingPayload",
    "AutoEnrollmentWindowPayload",
    "EnrollmentChangePayload",
    "ForfeiturePayload",
    "HCEStatusPayload",
    "ComplianceEventPayload",
    "SabbaticalPayload",
    # Factories
    "EventFactory",
    "WorkforceEventFactory",
    "DCPlanEventFactory",
    "PlanAdministrationEventFactory",
    # Event Generator Abstraction Layer (E004)
    "EventRegistry",
    "EventGenerator",
    "EventContext",
    "ValidationResult",
    "GeneratorMetrics",
]
```

## Validation Rules (Unchanged)

All validation rules from the original file are preserved:

| Rule | Target | Constraint |
|------|--------|------------|
| Compensation precision | Decimal fields for money | 6 decimal places |
| Rate precision | Decimal fields for percentages | 4 decimal places |
| Job level range | job_level, new_job_level | 1-10 |
| Non-empty strings | employee_id, scenario_id, plan_design_id, department | min_length=1 |
| Positive amounts | annual_compensation, amount, etc. | gt=0 or ge=0 |
| Rate bounds | contribution rates, vesting % | 0-1 (ge=0, le=1) |
| Date ordering | SabbaticalPayload end_date | Must be after start_date |
