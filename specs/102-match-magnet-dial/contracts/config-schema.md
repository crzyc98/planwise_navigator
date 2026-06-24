# Contract: Configuration Schema Additions

## Pydantic (YAML config path) — `planalign_orchestrator/config/workforce.py`

New model nested under `EnrollmentSettings`:

```python
class MatchMagnetSettings(BaseModel):
    """Voluntary 'defer-to-the-match' behavior controls."""
    enabled: bool = True
    snap_probability: float = Field(default=0.45, ge=0.0, le=1.0,
        description="Fraction of below-ceiling voluntary enrollees who snap to the match ceiling.")
    max_deferral_rate: float = Field(default=0.10, ge=0.01, le=1.0,
        description="Maximum employee deferral rate for voluntary enrollment (bounds magnet-snapped rates).")

class EnrollmentSettings(BaseModel):
    auto_enrollment: AutoEnrollmentSettings = Field(default_factory=AutoEnrollmentSettings)
    proactive_enrollment: ProactiveEnrollmentSettings = Field(default_factory=ProactiveEnrollmentSettings)
    timing: EnrollmentTimingSettings = Field(default_factory=EnrollmentTimingSettings)
    match_magnet: MatchMagnetSettings = Field(default_factory=MatchMagnetSettings)   # NEW
```

YAML example (`config/simulation_config.yaml`):

```yaml
enrollment:
  match_magnet:
    enabled: true
    snap_probability: 0.45
    max_deferral_rate: 0.10
```

## dc_plan (Studio UI path)

UI form fields → `dc_plan` payload (`buildConfigPayload.ts`) → mapped in `_apply_dc_plan_enrollment_overrides`:

| Form field (`formData`) | dc_plan key | Transform |
|-------------------------|-------------|-----------|
| `dcMatchMagnetEnabled` | `match_magnet_enabled` | `Boolean(...)` |
| `dcMatchMagnetProbability` | `match_magnet_probability` | `Number(...) / 100` |
| `dcMaxVoluntaryDeferral` | `max_voluntary_deferral_percent` | `Number(...) / 100` |

## Studio UI surface

- **DCPlanSection.tsx**: three controls in the enrollment/match area — magnet enable toggle, snap-probability % input, max-voluntary-deferral % input. Disable the % inputs when the toggle is off (snap %) / always enabled (max deferral).
- **types.ts / constants.ts**: add the three `formData` fields with defaults `true`, `45`, `10`.
- **ConfigContext.tsx**: load existing scenario values into the new fields.
- **CopyScenarioModal.tsx**: **MUST** copy the three new fields (FR-005) — mirrors the #326/#327 fix that added `voluntary_enrollment_rate` to copy.

## Validation / precedence rules

- dc_plan (UI) overrides take precedence over YAML defaults, consistent with the existing `_export_enrollment_vars` ordering.
- Out-of-range values rejected by Pydantic (`ge/le`); UI should constrain inputs to the same bounds.
- Unset everywhere → `dbt_project.yml` defaults apply (backward compatible).
