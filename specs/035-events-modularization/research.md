# Research: Events Module Modularization

**Feature**: 035-events-modularization
**Date**: 2026-02-06

## Research Questions

### 1. Python Package vs Module Coexistence

**Question**: Can `config/events.py` (file) and `config/events/` (directory) coexist?

**Decision**: Use the file as the compatibility layer

**Rationale**: In Python, when both `config/events.py` and `config/events/` exist, the **file takes precedence** for imports. This allows:
- Existing `from config.events import X` to continue working
- New code can optionally use `from config.events.workforce import HirePayload` for direct access

**Alternatives Considered**:
1. Rename `events.py` to `_events_compat.py` and make `events/` the package
   - Rejected: Breaks existing imports
2. Move everything to `config/events/` and update all imports
   - Rejected: Violates backward compatibility requirement (FR-003)

### 2. Shared Validator Pattern for Pydantic v2

**Question**: How to share validators across multiple Pydantic models without duplication?

**Decision**: Create standalone functions that can be called from `@field_validator` decorators

**Rationale**: Pydantic v2 `@field_validator` can call any function. The pattern:
```python
# validators.py
def quantize_compensation(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.000001"))

# workforce.py
class HirePayload(BaseModel):
    annual_compensation: Decimal = Field(..., gt=0)

    @field_validator("annual_compensation")
    @classmethod
    def validate_compensation(cls, v: Decimal) -> Decimal:
        return quantize_compensation(v)
```

**Alternatives Considered**:
1. Pydantic `BeforeValidator` with `Annotated` types
   - Rejected: Would require updating all Field annotations, higher risk
2. Mixin classes with shared validators
   - Rejected: Pydantic v2 validator inheritance is complex; simpler to use functions
3. Custom Pydantic types (e.g., `CompensationDecimal`)
   - Rejected: Over-engineering; simple functions suffice

### 3. Import Cycle Prevention

**Question**: How to prevent circular imports between submodules?

**Decision**: Strict dependency order: validators → payloads → core

**Rationale**: The dependency graph is:
```
validators.py (no dependencies)
    ↓
workforce.py, dc_plan.py, admin.py (import validators only)
    ↓
core.py (imports all payload modules)
    ↓
__init__.py / events.py (re-exports from core and payloads)
```

Each layer only imports from layers above it. No circular dependencies possible.

**Alternatives Considered**:
1. Lazy imports with `TYPE_CHECKING`
   - Rejected: Not needed; clean dependency order eliminates cycles
2. Forward references for type hints
   - Rejected: All types are concrete; no forward refs needed

### 4. Discriminated Union Preservation

**Question**: How does SimulationEvent's discriminated union work when payloads are in separate files?

**Decision**: Import all payload types into `core.py` and define the union there

**Rationale**: Pydantic discriminated unions require all types to be available at class definition time. The `core.py` module imports all payloads and defines:
```python
from .workforce import HirePayload, PromotionPayload, ...
from .dc_plan import EligibilityPayload, EnrollmentPayload, ...
from .admin import ForfeiturePayload, HCEStatusPayload, ...

class SimulationEvent(BaseModel):
    payload: Union[
        Annotated[HirePayload, Field(discriminator="event_type")],
        ...
    ]
```

This preserves identical runtime behavior.

### 5. Validator Precision Standards

**Question**: What precision levels are used across the codebase?

**Decision**: Standardize on 3 precision levels

**Analysis of existing validators**:

| Pattern | Decimal Places | Used For |
|---------|---------------|----------|
| `0.000001` | 6 | Compensation, amounts (monetary values) |
| `0.0001` | 4 | Rates, percentages (e.g., contribution rates, vesting %) |

**Shared validators to create**:
1. `quantize_amount(v: Decimal) -> Decimal` - 6 decimal places
2. `quantize_rate(v: Decimal) -> Decimal` - 4 decimal places
3. `quantize_amount_dict(d: Dict[str, Decimal]) -> Dict[str, Decimal]` - For source balance dicts

### 6. Re-export Pattern for `__all__`

**Question**: How to maintain the exact same `__all__` list in the compatibility layer?

**Decision**: Copy the existing `__all__` list and add explicit imports

**Rationale**: The compatibility layer (`config/events.py`) will:
1. Import all symbols from submodules
2. Import re-exported symbols from `planalign_orchestrator.generators`
3. Define identical `__all__` list

```python
# config/events.py (compatibility layer)
from config.events.core import (
    SimulationEvent, LegacySimulationEvent,
    EventFactory, WorkforceEventFactory, DCPlanEventFactory, PlanAdministrationEventFactory,
)
from config.events.workforce import HirePayload, PromotionPayload, ...
from config.events.dc_plan import EligibilityPayload, EnrollmentPayload, ...
from config.events.admin import ForfeiturePayload, HCEStatusPayload, ...

# Re-export from orchestrator (unchanged)
from planalign_orchestrator.generators import (
    EventRegistry, EventGenerator, EventContext, ValidationResult, GeneratorMetrics,
)

__all__ = [
    # Exact same list as before
    ...
]
```

## Validation Findings

### Current Validator Duplication

Found **18 validator occurrences** in `config/events.py`:

| Validator Type | Count | Classes Using It |
|---------------|-------|------------------|
| Compensation (6 places) | 5 | HirePayload, PromotionPayload, MeritPayload, HCEStatusPayload, SabbaticalPayload |
| Amount (6 places) | 4 | ContributionPayload, ForfeiturePayload, ComplianceEventPayload |
| Rate/Percentage (4 places) | 7 | MeritPayload, EnrollmentPayload, VestingPayload, AutoEnrollmentWindowPayload, EnrollmentChangePayload, ForfeiturePayload, SabbaticalPayload |
| Source Balances Dict | 1 | VestingPayload |
| String Validation | 3 | SimulationEvent (employee_id, scenario_id, plan_design_id) |

### Consumer Analysis

Files importing from `config.events`:

| File | Symbols Used |
|------|--------------|
| `planalign_orchestrator/generators/base.py` | SimulationEvent |
| `planalign_orchestrator/generators/hire.py` | HirePayload, WorkforceEventFactory |
| `planalign_orchestrator/generators/termination.py` | TerminationPayload, WorkforceEventFactory |
| `planalign_orchestrator/generators/promotion.py` | PromotionPayload, WorkforceEventFactory |
| `planalign_orchestrator/generators/merit.py` | MeritPayload, WorkforceEventFactory |
| `planalign_orchestrator/generators/enrollment.py` | EnrollmentPayload, DCPlanEventFactory |
| `planalign_orchestrator/generators/sabbatical.py` | SabbaticalPayload, WorkforceEventFactory |
| `tests/unit/events/test_simulation_event.py` | EventFactory, HirePayload, SimulationEvent, WorkforceEventFactory |
| `tests/unit/events/test_dc_plan_events.py` | Multiple DC plan payloads and factories |
| `tests/unit/events/test_plan_administration_events.py` | Admin payloads and factory |
| `tests/utils/factories.py` | WorkforceEventFactory |
| `tests/integration/test_multi_year_coordination.py` | WorkforceEventFactory |

All imports use `from config.events import ...` pattern - 100% compatible with re-export approach.

## Conclusions

1. **No blockers identified** - All research questions have clear solutions
2. **Backward compatibility confirmed** - File-over-package precedence enables seamless migration
3. **Validator consolidation achievable** - 18 validators → 4 shared functions
4. **Test impact minimal** - No test modifications required
