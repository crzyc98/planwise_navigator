# Research: Fix Tenure Eligibility Enforcement

**Feature Branch**: `047-fix-tenure-eligibility`
**Date**: 2026-02-11

## R1: Root Cause — `allow_new_hires` Default Bypasses Tenure Requirement

### Decision
The `allow_new_hires: true` default is applied at **three independent layers**, all of which must be fixed:

1. **Pydantic model** (`planalign_orchestrator/config/workforce.py:108`):
   ```python
   allow_new_hires: bool = Field(default=True, description="Allow new hires to qualify")
   ```

2. **Export function** (`planalign_orchestrator/config/export.py:289,311`):
   ```python
   'allow_new_hires': employer_data.get('eligibility', {}).get('allow_new_hires', True)
   ```

3. **dbt model** (`dbt/models/intermediate/int_employer_eligibility.sql:44,57`):
   ```jinja
   {% set match_allow_new_hires = match_eligibility.get('allow_new_hires', true) %}
   {% set core_allow_new_hires = core_eligibility.get('allow_new_hires', true) %}
   ```

### Rationale
All three layers have independent fallback defaults. Fixing only one layer leaves the other two as escape hatches where the old `true` default persists.

### Alternatives Considered
- Fix only the dbt model (rejected: Pydantic defaults still show `true` in audits)
- Fix only the Pydantic model (rejected: export function has independent hardcoded defaults)
- Remove `allow_new_hires` entirely (rejected: some plans legitimately need it for rehire scenarios)
- Always default to `false` (rejected: breaks backward compat for `minimum_tenure_years: 0`)

---

## R2: How To Distinguish Explicit vs Default `allow_new_hires`

### Decision
Use Pydantic v2 `model_validator(mode='before')` to detect whether `allow_new_hires` was explicitly provided.

### Rationale
Pydantic v2 applies field defaults before `model_validator(mode='after')` runs, making it impossible to distinguish "user set true" from "default true" in after-mode. The `mode='before'` validator receives raw input data before defaults are applied.

### Implementation Pattern
```python
@model_validator(mode='before')
@classmethod
def resolve_allow_new_hires_default(cls, data):
    if isinstance(data, dict):
        min_tenure = data.get('minimum_tenure_years', 0)
        if 'allow_new_hires' not in data:
            data['allow_new_hires'] = (min_tenure == 0)
    return data
```

### Alternatives Considered
- Change default to `None` (rejected: breaks existing consumers expecting bool)
- Use `Optional[bool]` (rejected: type mismatch in dbt var export)

---

## R3: UI Export Gap for `allow_new_hires`

### Decision
The UI (PlanAlign Studio) sends `dc_plan` settings that are merged into dbt vars. Currently, `match_allow_new_hires` and `core_allow_new_hires` from dc_plan are **NOT** exported.

### Current dc_plan match overrides (export.py:491-500)
Handled: `match_min_tenure_years`, `match_require_year_end_active`, `match_min_hours_annual`, `match_allow_terminated_new_hires`, `match_allow_experienced_terminations`.
**Missing**: `match_allow_new_hires`, `core_allow_new_hires`.

### Fix Required
Add export handling for `match_allow_new_hires` and `core_allow_new_hires` in dc_plan merge sections.

---

## R4: dbt Model Conditional Default Pattern

### Decision
Change Jinja defaults for `allow_new_hires` to be conditional on `minimum_tenure_years`.

### Implementation
```jinja
{# Resolve allow_new_hires: default to false when tenure requirement exists #}
{% set match_allow_new_hires_raw = match_eligibility.get('allow_new_hires', none) %}
{% if match_allow_new_hires_raw is none %}
    {% set match_allow_new_hires = (match_minimum_tenure_years == 0) %}
{% else %}
    {% set match_allow_new_hires = match_allow_new_hires_raw %}
{% endif %}
```

### Rationale
`none` sentinel distinguishes "not provided" from "explicitly set to true/false". The dbt model is the last line of defense and must produce correct behavior even when called directly via `dbt run`.

---

## R5: Warning Emission Pattern

### Decision
Add `_validate_eligibility_configuration()` to `PipelineOrchestrator`, called during simulation startup alongside `_validate_compensation_parameters()`.

### Existing Pattern (pipeline_orchestrator.py:810-830)
```python
def _validate_compensation_parameters(self) -> None:
    warnings = []
    if comp.base_cola_rate < 0.0 or comp.base_cola_rate > 0.1:
        warnings.append(f"...")
    if warnings and self.verbose:
        print("\n⚠️ Compensation Parameter Warnings:")
```

### Rationale
- Follows existing console warning pattern (emoji prefix, verbose-gated)
- Fires at startup before dbt execution (within first 5 seconds per SC-003)
- Only warns on contradictory config (FR-005), not on resolved defaults

---

## R6: Backward Compatibility (`apply_eligibility: false`)

### Decision
No changes needed. The backward-compat code path (int_employer_eligibility.sql:303-309) uses simple `active + 1000 hours` logic that never checks tenure or `allow_new_hires`.

```sql
WHEN NOT {{ match_apply_eligibility }} THEN
    CASE WHEN employment_status_eoy = 'active' AND annual_hours_worked >= 1000 THEN TRUE
    ELSE FALSE END
```

---

## R7: Existing Test Infrastructure

### Key Test Files
- `tests/test_match_modes.py` — Python config/eligibility tests (793 lines)
- `dbt/tests/analysis/test_e058_business_logic.sql` — dbt eligibility tests (310 lines)
- `dbt/models/intermediate/schema.yml` — dbt schema tests

### New Tests Needed
- Python: `allow_new_hires` conditional default validator
- Python: Config warning for contradictory settings
- Python: Export function produces correct `allow_new_hires` based on tenure
- dbt: Tenure-based exclusion when `allow_new_hires` defaults to false

---

## R8: Impact on Default Config

### Decision
No changes to `config/simulation_config.yaml`.

### Rationale
The YAML has `minimum_tenure_years: 0` with explicit `allow_new_hires: true`. Since tenure is 0, the new conditional default also resolves to `true` — no behavioral change.
