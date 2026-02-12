# Implementation Plan: Fix Tenure Eligibility Enforcement for Employer Contributions

**Branch**: `047-fix-tenure-eligibility` | **Date**: 2026-02-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/047-fix-tenure-eligibility/spec.md`

## Summary

When `minimum_tenure_years > 0` is configured, the `allow_new_hires` field defaults to `true` at three independent layers (Pydantic model, export function, dbt Jinja), silently bypassing the tenure requirement for new hires. The fix changes the default to be conditional: `true` when `minimum_tenure_years == 0` (backward compat), `false` when `minimum_tenure_years > 0` (correct enforcement). A configuration warning is emitted when `allow_new_hires: true` is explicitly set alongside a non-zero tenure requirement.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator), SQL/Jinja2 (dbt models)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic v2.7.4
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`) — immutable event store
**Testing**: pytest (Python), dbt test (SQL)
**Target Platform**: Linux server / work laptop
**Project Type**: Single project (orchestrator + dbt models)
**Performance Goals**: No performance impact (config default change only)
**Constraints**: Must maintain backward compatibility for `minimum_tenure_years: 0` configs
**Scale/Scope**: 6 files modified, ~90 lines changed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No event schema changes. Output values change but events remain immutable. |
| II. Modular Architecture | PASS | Changes span 5 focused files, each with single responsibility. No new modules. |
| III. Test-First Development | PASS | New tests for conditional default, warning emission, and export correctness. |
| IV. Enterprise Transparency | PASS | Warning emitted for contradictory config. Metadata columns reflect resolved values. |
| V. Type-Safe Configuration | PASS | Pydantic v2 model_validator enforces conditional default. |
| VI. Performance & Scalability | PASS | No performance impact — config default change only. |

## Project Structure

### Documentation (this feature)

```text
specs/047-fix-tenure-eligibility/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 quickstart guide
└── tasks.md             # Phase 2 task list (via /speckit.tasks)
```

### Source Code (files to modify)

```text
planalign_orchestrator/
└── config/
    ├── workforce.py             # Pydantic model: conditional default validator
    ├── export.py                # Export function: conditional default + UI field handling
    └── loader.py                # Warning emission for contradictory config (FR-005)

dbt/
├── models/
│   └── intermediate/
│       └── int_employer_eligibility.sql  # Jinja: conditional default fallback
└── tests/
    └── analysis/
        └── test_e058_business_logic.sql  # Extended dbt eligibility tests

tests/
└── test_match_modes.py          # New test cases for conditional default + warning
```

**Structure Decision**: Single project — all changes are within existing modules. No new files needed.

## Implementation Details

### Change 1: Pydantic Conditional Default (`workforce.py`)

**File**: `planalign_orchestrator/config/workforce.py`
**Lines**: 103-110

Add a `@model_validator(mode='before')` to `EmployerMatchEligibilitySettings`:

```python
from pydantic import model_validator

class EmployerMatchEligibilitySettings(BaseModel):
    """Employer match eligibility requirements configuration."""
    minimum_tenure_years: int = Field(default=0, ge=0, description="Minimum years of service")
    require_active_at_year_end: bool = Field(default=True, description="Must be active on Dec 31")
    minimum_hours_annual: int = Field(default=1000, ge=0, description="Minimum hours worked annually")
    allow_new_hires: bool = Field(default=True, description="Allow new hires to qualify")
    allow_terminated_new_hires: bool = Field(default=False, description="Allow new-hire terminations to qualify")
    allow_experienced_terminations: bool = Field(default=False, description="Allow experienced terminations to qualify")

    @model_validator(mode='before')
    @classmethod
    def resolve_allow_new_hires_default(cls, data):
        """Default allow_new_hires to false when minimum_tenure_years > 0.

        FR-003: Default to false when tenure requirement exists.
        FR-004: Default to true when no tenure requirement (backward compat).
        """
        if isinstance(data, dict):
            min_tenure = data.get('minimum_tenure_years', 0)
            if 'allow_new_hires' not in data:
                data['allow_new_hires'] = (int(min_tenure) == 0)
        return data
```

**Requirements**: FR-003, FR-004

### Change 2: Export Function Conditional Default (`export.py`)

**File**: `planalign_orchestrator/config/export.py`

#### 2a: `_export_employer_match_vars()` (lines 307-313)

Change the hardcoded `True` default for `allow_new_hires` to conditional:

```python
# Current:
'allow_new_hires': employer_data.get('eligibility', {}).get('allow_new_hires', True),

# New:
'allow_new_hires': employer_data.get('eligibility', {}).get(
    'allow_new_hires',
    employer_data.get('eligibility', {}).get('minimum_tenure_years', 0) == 0
),
```

Apply the same fix to the legacy fallback path (lines 362-368).

#### 2b: Add `match_allow_new_hires` to dc_plan export (line ~500)

```python
if dc_plan_dict.get("match_allow_new_hires") is not None:
    match_eligibility_overrides["allow_new_hires"] = bool(dc_plan_dict["match_allow_new_hires"])
```

#### 2c: `_export_core_contribution_vars()` — same pattern

Add `core_allow_new_hires` to dc_plan export (line ~700):

```python
if dc_plan_dict.get("core_allow_new_hires") is not None:
    core_eligibility_overrides["allow_new_hires"] = bool(dc_plan_dict["core_allow_new_hires"])
```

**Requirements**: FR-003, FR-004, FR-007

### Change 3: dbt Jinja Conditional Default (`int_employer_eligibility.sql`)

**File**: `dbt/models/intermediate/int_employer_eligibility.sql`
**Lines**: 44, 57

Replace unconditional `true` defaults with conditional logic:

```jinja
-- Match (line 57, currently):
{% set match_allow_new_hires = match_eligibility.get('allow_new_hires', true) %}

-- Match (new):
{% set match_allow_new_hires_raw = match_eligibility.get('allow_new_hires', none) %}
{% if match_allow_new_hires_raw is none %}
    {% set match_allow_new_hires = (match_minimum_tenure_years == 0) %}
{% else %}
    {% set match_allow_new_hires = match_allow_new_hires_raw %}
{% endif %}

-- Core (line 44, currently):
{% set core_allow_new_hires = core_eligibility.get('allow_new_hires', true) %}

-- Core (new):
{% set core_allow_new_hires_raw = core_eligibility.get('allow_new_hires', none) %}
{% if core_allow_new_hires_raw is none %}
    {% set core_allow_new_hires = (core_minimum_tenure_years == 0) %}
{% else %}
    {% set core_allow_new_hires = core_allow_new_hires_raw %}
{% endif %}
```

**Requirements**: FR-001, FR-002, FR-003, FR-004

### Change 4: Configuration Warning (`loader.py`)

**File**: `planalign_orchestrator/config/loader.py`

Add `validate_eligibility_configuration()` method to `SimulationConfig`, following the existing `validate_threading_configuration()` pattern:

```python
import warnings

def validate_eligibility_configuration(self) -> None:
    """Warn when allow_new_hires contradicts minimum_tenure_years (FR-005)."""
    match = getattr(self, 'employer_match', None)
    if match:
        elig = match.eligibility if hasattr(match, 'eligibility') else None
        if elig and elig.minimum_tenure_years > 0 and elig.allow_new_hires:
            warnings.warn(
                f"Match eligibility: allow_new_hires is true but "
                f"minimum_tenure_years is {elig.minimum_tenure_years}. "
                f"New hires will bypass the tenure requirement."
            )

    core = getattr(self, 'employer_core_contribution', None)
    if core:
        elig = core.get('eligibility', {}) if isinstance(core, dict) else {}
        min_tenure = elig.get('minimum_tenure_years', 0)
        allow_new = elig.get('allow_new_hires', min_tenure == 0)
        if min_tenure > 0 and allow_new:
            warnings.warn(
                f"Core eligibility: allow_new_hires is true but "
                f"minimum_tenure_years is {min_tenure}. "
                f"New hires will bypass the tenure requirement."
            )
```

Call alongside existing `validate_threading_configuration()` in config loading.

**Requirements**: FR-005

### Change 5: Tests (`test_match_modes.py`)

**File**: `tests/test_match_modes.py`

Add test cases:

```python
class TestAllowNewHiresConditionalDefault:
    """Tests for FR-003/FR-004: allow_new_hires conditional default."""

    def test_defaults_true_when_no_tenure_requirement(self):
        settings = EmployerMatchEligibilitySettings(minimum_tenure_years=0)
        assert settings.allow_new_hires is True

    def test_defaults_false_when_tenure_requirement(self):
        settings = EmployerMatchEligibilitySettings(minimum_tenure_years=2)
        assert settings.allow_new_hires is False

    def test_explicit_true_overrides_default(self):
        settings = EmployerMatchEligibilitySettings(
            minimum_tenure_years=2, allow_new_hires=True
        )
        assert settings.allow_new_hires is True

    def test_explicit_false_respected(self):
        settings = EmployerMatchEligibilitySettings(
            minimum_tenure_years=0, allow_new_hires=False
        )
        assert settings.allow_new_hires is False

    def test_boundary_tenure_one(self):
        settings = EmployerMatchEligibilitySettings(minimum_tenure_years=1)
        assert settings.allow_new_hires is False
```

**Requirements**: FR-003, FR-004, SC-002, SC-004

## Unchanged Components

- `config/simulation_config.yaml` — already has `minimum_tenure_years: 0`, no change needed
- `apply_eligibility: false` code path — uses simple logic, no tenure check (FR-006)
- `fct_workforce_snapshot.sql` — downstream consumer, automatically reflects corrected eligibility
- `int_employee_match_calculations.sql` — uses eligibility output, no direct changes
- `int_employer_core_contributions.sql` — uses eligibility output, no direct changes

## Complexity Tracking

No constitution violations. All changes are minimal and focused:
- 6 files modified (workforce.py, export.py, loader.py, int_employer_eligibility.sql, test_match_modes.py, test_e058_business_logic.sql)
- ~90 lines changed
- No new files, modules, or abstractions
- No schema changes
