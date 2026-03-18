# Research: Voluntary Enrollment Rate Configuration

**Feature**: 075-voluntary-enrollment-config
**Date**: 2026-03-18

## R1: Where to Add the Config Field

**Decision**: Add `voluntary_enrollment_rate: Optional[float]` to `AutoEnrollmentSettings` in `planalign_orchestrator/config/workforce.py`

**Rationale**: `AutoEnrollmentSettings` is the Pydantic BaseModel that holds all enrollment-related configuration and flows through the export pipeline to dbt. Despite "voluntary" being independent of "auto-enrollment", this is where all enrollment config lives, and the export function `_export_auto_enrollment_fields()` already handles this class.

**Alternatives considered**:
- Adding to `AutoEnrollmentOptions` dataclass in `config/events/dc_plan.py` — rejected because that's an event payload schema, not a simulation config model
- Creating a new `VoluntaryEnrollmentSettings` class — rejected as over-engineering; one field doesn't warrant a new class

## R2: How Enrollment Probability Is Currently Calculated

**Decision**: Use the existing multiplicative model and add `voluntary_enrollment_rate` as an additional multiplier

**Rationale**: Current formula is `final_probability = base_rate(age) × income_multiplier × job_level_multiplier`. Adding `× voluntary_enrollment_rate` preserves demographic variation while scaling overall participation. When `voluntary_enrollment_rate` is NULL/not set, the multiplier defaults to 1.0 (no change).

**Current architecture**:
- `int_voluntary_enrollment_decision.sql` uses deterministic hash-based random: `enrollment_random < final_enrollment_probability`
- `int_proactive_voluntary_enrollment.sql` uses identical probability model for new hires
- Both models already support `{{ var() }}` overrides for all demographic rates

## R3: dbt Variable Integration

**Decision**: Export as `voluntary_enrollment_rate` dbt variable, defaulting to `null` in `dbt_project.yml`

**Rationale**: Follows existing pattern where `_set_if_not_none()` only exports non-null values. In SQL, `COALESCE({{ var('voluntary_enrollment_rate', none) }}, 1.0)` produces 1.0 when not set, preserving backwards compatibility.

**Implementation in SQL**:
```sql
-- Apply after existing probability calculation
final_enrollment_probability * COALESCE({{ var('voluntary_enrollment_rate', none) }}, 1.0)
```

## R4: UI Component Approach

**Decision**: Add the voluntary enrollment rate field to the existing `DCPlanSection.tsx` component alongside auto-enrollment controls

**Rationale**: `DCPlanSection.tsx` already contains all enrollment-related form fields (auto-enrollment toggle, deferral rate, opt-out rate, etc.). Adding a field here follows the established pattern. No new component file needed.

**Alternatives considered**:
- Creating a new `DCPlanConfigForm.tsx` (mentioned in issue) — rejected because `DCPlanSection.tsx` already serves this purpose and is fully editable

## R5: Config Persistence Flow

**Decision**: Use existing `config_overrides` flexible dict pattern — no schema migration needed

**Rationale**: The API stores `config_overrides: Dict[str, Any]` as JSON in `scenario.json`. Adding `voluntary_enrollment_rate` to the `dc_plan` section of this dict requires zero backend schema changes. The `buildConfigPayload.ts` frontend function transforms form data to the API payload format.

**Flow**: FormData (`dcVoluntaryEnrollmentRate`) → `buildConfigPayload.ts` (`voluntary_enrollment_rate`) → API PUT → `scenario.json` → `get_merged_config()` → `SimulationConfig` → `_export_enrollment_vars()` → dbt `--vars` → SQL `{{ var() }}`

## R6: Independence from Auto-Enrollment

**Decision**: The voluntary enrollment rate applies unconditionally — both enrollment models (`int_voluntary_enrollment_decision.sql` and `int_proactive_voluntary_enrollment.sql`) apply the multiplier regardless of `auto_enrollment_enabled`

**Rationale**: The issue explicitly requires independence. The SQL models already run independently of the auto-enrollment flag. The voluntary enrollment rate simply scales existing probabilities in both models.
