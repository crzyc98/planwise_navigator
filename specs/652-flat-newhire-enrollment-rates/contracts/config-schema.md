# Contract: Configuration Schema

**Feature**: 652-flat-newhire-enrollment-rates

## Pydantic — `AutoEnrollmentSettings`

```python
voluntary_enrollment_rate: Optional[float] = Field(
    default=None,
    ge=0,
    le=1,
    description=(
        "Fraction of eligible new hires who voluntarily enroll in their hire "
        "year (0.0-1.0). None = use demographic enrollment probabilities."
    ),
)
new_hire_opt_out_rate: Optional[float] = Field(
    default=None,
    ge=0,
    le=1,
    description=(
        "Fraction of auto-enrolled new hires who opt out (0.0-1.0). "
        "None = use the demographic opt-out model."
    ),
)
```

The field type and constraints on `voluntary_enrollment_rate` are unchanged; only the description and downstream meaning change. `new_hire_opt_out_rate` mirrors it exactly so the two behave identically at the boundaries.

## YAML

```yaml
enrollment:
  auto_enrollment:
    voluntary_enrollment_rate: 0.6   # 60% of eligible new hires enroll on their own
    new_hire_opt_out_rate: 0.1       # 10% of the auto-enrolled remainder opt out
    opt_out_rates:
      target: 0.09                   # unchanged; governs continuing employees
```

Omitting either key selects the demographic model for that decision.

## Export

Both fields flow through `_set_if_not_none` in `planalign_orchestrator/config/export.py`, which omits the dbt variable when the value is `None` and emits it when the value is `0.0`. That distinction is load-bearing: `0.0` means "nobody voluntarily enrolls", not "use demographics". It is already covered by `tests/unit/orchestrator/test_config_export.py::test_voluntary_enrollment_rate_zero`.

## Studio payload

`buildConfigPayload.ts` emits under `dc_plan`:

| Key | Source field | Emitted when |
|---|---|---|
| `voluntary_enrollment_rate` | `dcVoluntaryEnrollmentRate` | field is not `''` |
| `new_hire_opt_out_rate` | `dcNewHireOptOutRate` | field is not `''` |

Both are sent as decimals; the form holds percentages and divides by 100, matching the existing convention at `buildConfigPayload.ts:95`.

**Default change**: `constants.ts` currently sets `dcVoluntaryEnrollmentRate: '30'`, so Studio scenarios store an explicit `0.30` (research R2). This becomes `''` so that the Studio default matches the Python default of unset. `dcNewHireOptOutRate` is introduced as `''`.

This is the one place where the compatibility guarantee has a real limit: Studio scenarios already saved with `0.30` carry an explicit value and will be read under the new meaning. See decision D1.

## Labels

| Surface | Before | After |
|---|---|---|
| `DCPlanSection.tsx` heading and input | "Voluntary Enrollment Rate" | "New Hire Voluntary Enrollment %" |
| `DCPlanSection.tsx` | — | "New Hire Opt-Out %" (new input) |
| `PlanDesignModal.tsx` read-only field | "Voluntary Enrollment Rate" | "New Hire Voluntary Enrollment %" |

Both inputs show "Default" when empty, matching `PlanDesignModal.tsx:158`, and their help text must state that empty means demographic behavior — the unset state is now meaningful and has to be discoverable (FR-016).
