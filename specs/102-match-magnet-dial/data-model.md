# Phase 1 Data Model: Match-Magnet Dial & Ceiling Fidelity

No new database tables or event types. This feature adds **configuration** entities and a derived per-employee value used inside existing voluntary-enrollment models.

## Entity: MatchMagnetSettings (configuration)

Scenario-level settings governing voluntary "defer-to-the-match" behavior. New Pydantic model nested under `EnrollmentSettings` (`planalign_orchestrator/config/workforce.py`).

| Field | Type | Default | Constraints | Maps to dbt var |
|-------|------|---------|-------------|-----------------|
| `enabled` | bool | `True` | — | `enrollment_match_magnet_enabled` |
| `snap_probability` | float | `0.45` | `ge=0.0, le=1.0` | `enrollment_match_magnet_probability` |
| `max_deferral_rate` | float | `0.10` | `ge=0.01, le=1.0` | `voluntary_max_deferral_rate` |

Defaults reproduce current behavior (FR-006, SC-004). `enabled=False` → no snapping (FR-007); `snap_probability=0` behaves as disabled (deterministic, edge case).

## dc_plan (UI) keys

UI sends a `dc_plan` dict; mapped in `_apply_dc_plan_enrollment_overrides` (`export.py`). Percentages divided by 100 to match the existing convention.

| dc_plan key (UI) | Source form field | Transform | dbt var |
|------------------|-------------------|-----------|---------|
| `match_magnet_enabled` | toggle | bool | `enrollment_match_magnet_enabled` |
| `match_magnet_probability` | percent input | `/100` → decimal | `enrollment_match_magnet_probability` |
| `max_voluntary_deferral_percent` | percent input | `/100` → decimal | `voluntary_max_deferral_rate` |

## Entity: Match Ceiling (derived, per-employee)

Not persisted as config — computed at simulation time and consumed by the voluntary-enrollment models. Its derivation depends on `employer_match_status`:

| `employer_match_status` | Ceiling source | Granularity |
|-------------------------|----------------|-------------|
| `deferral_based` (default) | `employer_match_max_deferral_rate` (scalar from active formula's top-tier `employee_max` / `max_match_percentage`) | Plan-wide |
| `graded_by_service`, `tenure_graded` | `get_tiered_match_max_deferral(years_of_service, employer_match_graded_schedule, default)` | Per-employee |
| `points_based` | points-tier max-deferral macro over `points_match_tiers` | Per-employee |
| match disabled / unknown | `0` → magnet inactive | — |

**Validation rules** (enforced by macro + model):
- Ceiling MUST reflect the active formula, independent of `deferral_match_response` (FR-003).
- Magnet only raises rates toward the ceiling, never lowers (FR-008): applied as `WHEN selected_rate < ceiling AND snap_random < snap_probability THEN ceiling`.
- Final selected rate bounded by `[0.01, voluntary_max_deferral_rate]` (FR-009/FR-013).

## Output columns (audit, existing models — extended)

Both `int_voluntary_enrollment_decision` and `int_proactive_voluntary_enrollment` already emit audit fields; extend/keep:

| Column | Meaning |
|--------|---------|
| `raw_deferral_rate` | Demographically-assigned rate before magnet (existing) |
| `match_optimized_rate` | Rate after magnet snap, before bounds (existing) |
| `selected_deferral_rate` / `proactive_deferral_rate` | Final bounded rate (existing) |
| `match_magnet_ceiling` *(new, optional)* | The per-employee ceiling used, for transparency/audit (Principle IV) |

## Relationships

- `MatchMagnetSettings` belongs to one **Scenario** (alongside `AutoEnrollmentSettings`, `EmployerMatchSettings`).
- The **Match Ceiling** is derived from the scenario's **Employer-Match Formula** (`EmployerMatchSettings` / `employer_match` formulas) — this feature makes voluntary enrollment read that ceiling reliably.
- The ceiling and dial together determine each **Voluntary-Enrollee Deferral Decision** (a per-employee row, ultimately an enrollment event in `fct_yearly_events`).

## State / lifecycle

None beyond existing enrollment-event lifecycle. Deferral selection remains a deterministic function of (employee_id, simulation_year, seed, config) — reproducibility preserved (FR-010, SC-005).
