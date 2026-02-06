# Quickstart: Events Module Modularization

**Feature**: 035-events-modularization
**Date**: 2026-02-06

## What Changed

The 1,056-line `config/events.py` has been split into domain-specific modules:

```
config/
├── events.py              # Compatibility layer (still works!)
└── events/
    ├── __init__.py
    ├── validators.py      # Shared Decimal quantization
    ├── workforce.py       # HirePayload, PromotionPayload, etc.
    ├── dc_plan.py         # EnrollmentPayload, ContributionPayload, etc.
    ├── admin.py           # ForfeiturePayload, HCEStatusPayload, etc.
    └── core.py            # SimulationEvent + Factories
```

## For Existing Code (No Changes Needed)

All existing imports continue to work:

```python
# These still work exactly as before
from config.events import SimulationEvent
from config.events import WorkforceEventFactory, DCPlanEventFactory
from config.events import HirePayload, ContributionPayload
```

## For New Code (Optional Direct Imports)

You can now import directly from domain modules for clarity:

```python
# Direct imports (optional, for better IDE navigation)
from config.events.workforce import HirePayload, MeritPayload
from config.events.dc_plan import ContributionPayload, EnrollmentPayload
from config.events.admin import ForfeiturePayload
from config.events.core import SimulationEvent, WorkforceEventFactory
```

## Using Shared Validators

When creating new payload classes, use the shared validators:

```python
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
from config.events.validators import quantize_amount, quantize_rate

class MyNewPayload(BaseModel):
    """Example new payload using shared validators."""

    amount: Decimal = Field(..., gt=0)
    rate: Decimal = Field(..., ge=0, le=1)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return quantize_amount(v)  # 6 decimal places

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, v: Decimal) -> Decimal:
        return quantize_rate(v)  # 4 decimal places
```

## Module Guide

### Where to Find What

| If you need... | Look in... |
|----------------|------------|
| HirePayload, PromotionPayload, TerminationPayload, MeritPayload, SabbaticalPayload | `workforce.py` |
| EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload | `dc_plan.py` |
| AutoEnrollmentWindowPayload, EnrollmentChangePayload | `dc_plan.py` |
| ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload | `admin.py` |
| SimulationEvent, EventFactory, WorkforceEventFactory | `core.py` |
| DCPlanEventFactory, PlanAdministrationEventFactory | `core.py` |
| quantize_amount, quantize_rate, quantize_amount_dict | `validators.py` |

### Adding New Event Types

1. **Choose the domain module** based on event category
2. **Add the payload class** to the appropriate module
3. **Import shared validators** if needed
4. **Update `core.py`** to include the new payload in SimulationEvent's union
5. **Update `__init__.py`** to export the new payload
6. **Update `events.py`** to re-export the new payload

Example: Adding a `TransferPayload` to workforce events:

```python
# config/events/workforce.py
from .validators import quantize_amount

class TransferPayload(BaseModel):
    """Employee department transfer."""
    event_type: Literal["transfer"] = "transfer"
    from_department: str = Field(..., min_length=1)
    to_department: str = Field(..., min_length=1)
    effective_date: date

# config/events/core.py - Add to SimulationEvent.payload union
# config/events/__init__.py - Add to exports
# config/events.py - Add to re-exports and __all__
```

## Running Tests

```bash
# Run all event tests (unchanged behavior)
pytest tests/unit/events/ -v

# Run new validator tests
pytest tests/unit/test_validators.py -v

# Verify backward compatibility
pytest -m fast
```

## Troubleshooting

### ImportError: cannot import name 'X' from 'config.events'

The symbol might not be in `__all__`. Check that:
1. The symbol is exported from its domain module
2. The symbol is re-exported in `config/events.py`
3. The symbol is listed in `__all__`

### Circular Import Error

Check that you're not importing from `core.py` in a payload module. The dependency order is:
```
validators → payloads (workforce, dc_plan, admin) → core
```
