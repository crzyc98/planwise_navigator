# Quickstart: Adding New Event Types

**Feature**: 004-event-type-abstraction
**Date**: 2025-12-12

## Overview

This guide explains how to add a new workforce event type to PlanAlign Engine using the event type abstraction layer. The process requires creating one generator class and one registry entry.

## Prerequisites

- Python 3.11+ environment
- Understanding of the existing event types (HIRE, TERMINATION, PROMOTION, MERIT, ENROLLMENT)
- Familiarity with Pydantic v2 models

## Step-by-Step Guide

### Step 1: Define the Event Payload

Add a new payload class to `config/events.py`:

```python
# In config/events.py

class SabbaticalPayload(BaseModel):
    """Employee sabbatical leave event."""

    event_type: Literal["sabbatical"] = "sabbatical"
    start_date: date
    end_date: date
    reason: Literal["academic", "personal", "medical"]
    compensation_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    @field_validator("compensation_percentage")
    @classmethod
    def validate_percentage(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.0001"))
```

### Step 2: Register Payload in SimulationEvent

Add the payload to the discriminated union in `config/events.py`:

```python
# In SimulationEvent class

payload: Union[
    # ... existing payloads ...
    Annotated[SabbaticalPayload, Field(discriminator="event_type")],
] = Field(..., discriminator="event_type")
```

### Step 3: Create the Event Generator

Create a new file `planalign_orchestrator/generators/sabbatical.py`:

```python
"""Sabbatical event generator."""

from __future__ import annotations

from typing import List

from config.events import SimulationEvent, SabbaticalPayload
from planalign_orchestrator.generators.base import (
    EventGenerator,
    EventContext,
    ValidationResult,
)
from planalign_orchestrator.generators.registry import EventRegistry


@EventRegistry.register("sabbatical")
class SabbaticalEventGenerator(EventGenerator):
    """Generator for sabbatical leave events."""

    event_type = "sabbatical"
    execution_order = 45  # After merit (40), before enrollment (50)
    requires_hazard = False
    supports_sql = True
    supports_polars = False  # Can add later

    def generate_events(self, context: EventContext) -> List[SimulationEvent]:
        """Generate sabbatical events for eligible employees."""

        # Query eligible employees (example: tenure > 5 years)
        def _query_eligible(conn):
            return conn.execute("""
                SELECT employee_id, employee_ssn
                FROM fct_workforce_snapshot
                WHERE simulation_year = ?
                  AND current_tenure >= 5
                  AND employment_status = 'active'
            """, [context.simulation_year]).fetchall()

        eligible = context.db_manager.execute_with_retry(_query_eligible)

        events = []
        for emp in eligible:
            # Use deterministic selection (example: 2% sabbatical rate)
            random_val = self._get_random_value(
                emp[0], context.simulation_year, context.random_seed
            )
            if random_val < 0.02:
                event = self._create_event(emp, context)
                events.append(event)

        return events

    def validate_event(self, event: SimulationEvent) -> ValidationResult:
        """Validate sabbatical event."""
        errors = []
        warnings = []

        if not isinstance(event.payload, SabbaticalPayload):
            errors.append(f"Expected SabbaticalPayload, got {type(event.payload)}")
            return ValidationResult(is_valid=False, errors=errors)

        payload = event.payload
        if payload.end_date <= payload.start_date:
            errors.append("end_date must be after start_date")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def _get_random_value(self, employee_id: str, year: int, seed: int) -> float:
        """Deterministic random value matching dbt hash_rng."""
        import hashlib
        hash_key = f"{seed}|{employee_id}|{year}|sabbatical"
        hash_value = hashlib.md5(hash_key.encode()).hexdigest()
        hash_int = int(hash_value[:8], 16)
        return (hash_int % 2147483647) / 2147483647.0

    def _create_event(self, employee: tuple, context: EventContext) -> SimulationEvent:
        """Create a sabbatical event for an employee."""
        from datetime import timedelta
        from decimal import Decimal
        from uuid import uuid4

        employee_id, employee_ssn = employee
        start_date = date(context.simulation_year, 7, 1)  # Example: July 1

        payload = SabbaticalPayload(
            start_date=start_date,
            end_date=start_date + timedelta(days=180),
            reason="academic",
            compensation_percentage=Decimal("0.50")
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=context.scenario_id,
            plan_design_id=context.plan_design_id,
            effective_date=start_date,
            source_system="sabbatical_generator",
            payload=payload
        )
```

### Step 4: Register in Package Init

Add import to `planalign_orchestrator/generators/__init__.py`:

```python
from .base import EventGenerator, EventContext, ValidationResult
from .registry import EventRegistry

# Import all generators to trigger registration
from . import hire
from . import termination
from . import promotion
from . import merit
from . import enrollment
from . import sabbatical  # NEW

__all__ = [
    "EventGenerator",
    "EventContext",
    "ValidationResult",
    "EventRegistry",
]
```

### Step 5: Add Tests

Create `tests/unit/test_sabbatical_generator.py`:

```python
"""Tests for sabbatical event generator."""

import pytest
from datetime import date
from decimal import Decimal

from planalign_orchestrator.generators import EventRegistry
from planalign_orchestrator.generators.sabbatical import SabbaticalEventGenerator
from config.events import SimulationEvent, SabbaticalPayload


class TestSabbaticalEventGenerator:
    """Test suite for SabbaticalEventGenerator."""

    def test_registration(self):
        """Verify generator is registered."""
        assert "sabbatical" in EventRegistry.list_all()

    def test_execution_order(self):
        """Verify execution order is correct."""
        generator = EventRegistry.get("sabbatical")
        assert generator.execution_order == 45

    def test_validate_valid_event(self):
        """Validate a correctly formed event."""
        generator = SabbaticalEventGenerator()

        payload = SabbaticalPayload(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 12, 31),
            reason="academic",
            compensation_percentage=Decimal("0.50")
        )

        event = SimulationEvent(
            employee_id="EMP_001",
            scenario_id="test",
            plan_design_id="default",
            effective_date=date(2025, 7, 1),
            source_system="test",
            payload=payload
        )

        result = generator.validate_event(event)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_invalid_dates(self):
        """Reject event where end_date <= start_date."""
        generator = SabbaticalEventGenerator()

        payload = SabbaticalPayload(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 6, 1),  # Invalid: before start
            reason="personal",
            compensation_percentage=Decimal("0.25")
        )

        event = SimulationEvent(
            employee_id="EMP_001",
            scenario_id="test",
            plan_design_id="default",
            effective_date=date(2025, 7, 1),
            source_system="test",
            payload=payload
        )

        result = generator.validate_event(event)
        assert not result.is_valid
        assert "end_date must be after start_date" in result.errors
```

### Step 6: Run Tests

```bash
# Run new tests
pytest tests/unit/test_sabbatical_generator.py -v

# Run full fast test suite
pytest -m fast

# Verify registration
python -c "from planalign_orchestrator.generators import EventRegistry; print(EventRegistry.list_all())"
```

## Adding Hazard-Based Events

For events that use hazard probability tables (like promotions), use the mixin:

```python
from planalign_orchestrator.generators.base import (
    EventGenerator,
    HazardBasedEventGeneratorMixin,
)

@EventRegistry.register("lateral_move")
class LateralMoveEventGenerator(HazardBasedEventGeneratorMixin, EventGenerator):
    """Generator for lateral move events using hazard tables."""

    event_type = "lateral_move"
    execution_order = 32
    requires_hazard = True
    hazard_table_name = "config_lateral_move_hazard"

    def generate_events(self, context: EventContext) -> List[SimulationEvent]:
        # Get active workforce
        workforce = self._get_active_workforce(context)

        # Add bands
        for emp in workforce:
            emp["age_band"] = self.assign_age_band(emp["current_age"])
            emp["tenure_band"] = self.assign_tenure_band(emp["current_tenure"])

        # Select by hazard probability
        selected = self.select_by_hazard(workforce, context)

        # Create events
        return [self._create_event(emp, context) for emp in selected]
```

## Disabling Event Types

To disable an event type for a specific scenario:

```python
# In scenario configuration or simulation setup
from planalign_orchestrator.generators import EventRegistry

EventRegistry.disable("sabbatical", scenario_id="baseline")
```

Or via configuration file:

```yaml
# config/simulation_config.yaml
scenarios:
  baseline:
    disabled_events:
      - sabbatical
```

## Checklist

When adding a new event type, verify:

- [ ] Payload class added to `config/events.py`
- [ ] Payload registered in `SimulationEvent` discriminated union
- [ ] Generator class created with `@EventRegistry.register` decorator
- [ ] `event_type`, `execution_order` defined
- [ ] `generate_events()` implemented
- [ ] `validate_event()` implemented
- [ ] Generator imported in `__init__.py`
- [ ] Unit tests created and passing
- [ ] Integration test verifies events appear in `fct_yearly_events`

## Troubleshooting

### "Event type not registered"

Ensure the generator module is imported in `__init__.py`. Registration happens at import time.

### "Missing required method"

The ABC enforces `generate_events()` and `validate_event()`. Check for typos in method names.

### "Hazard rate not found"

For hazard-based generators, ensure the `hazard_table_name` seed file exists in `dbt/seeds/`.

### "Determinism mismatch"

Verify RNG uses the same hash format as dbt macro:
```
{seed}|{employee_id}|{year}|{event_type}
```
