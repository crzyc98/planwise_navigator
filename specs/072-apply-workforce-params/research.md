# Research: Apply Workforce Parameters Across Scenarios

**Feature Branch**: `072-apply-workforce-params`
**Date**: 2026-03-16

## R1: Workforce vs. DC Plan Parameter Boundary

**Decision**: Define workforce parameters as backend config keys under specific top-level sections, and exclude all `dc_plan.*` keys.

**Workforce Parameter Keys (INCLUDED)**:
- `simulation.target_growth_rate` — growth target only (not name/year/seed)
- `workforce.*` — all keys (`total_termination_rate`, `new_hire_termination_rate`)
- `compensation.*` — all keys (`merit_budget_percent`, `cola_rate_percent`, `promotion_increase_percent`, `promotion_distribution_range_percent`, `promotion_budget_percent`, `promotion_rate_multiplier`, `target_compensation_growth_percent`)
- `new_hire.*` — all keys (`strategy`, `target_percentile`, `compensation_variance_percent`, `market_scenario`, `age_distribution`, `level_distribution_mode`, `level_distribution`, `job_level_compensation`, `level_market_adjustments`)
- `promotion_hazard` — top-level seed config (atomic replacement)
- `age_bands` — top-level seed config (atomic replacement)
- `tenure_bands` — top-level seed config (atomic replacement)

**DC Plan Parameter Keys (EXCLUDED)**:
- `dc_plan.*` — all keys (eligibility, enrollment, match, core, escalation)

**Other Excluded Keys**:
- `simulation.name`, `simulation.start_year`, `simulation.end_year`, `simulation.random_seed` — scenario identity
- `data_sources.*` — census file paths
- `advanced.*` — infrastructure/engine settings

**Rationale**: The backend `config_overrides` dict already organizes parameters by domain. The `dc_plan.*` namespace perfectly isolates retirement plan design from workforce assumptions. Seed configs (`promotion_hazard`, `age_bands`, `tenure_bands`) are workforce-related and must be included.

**Alternatives Considered**:
- Allow user to pick individual parameter categories → rejected for complexity; the whole point is "one click to standardize workforce"
- Include `simulation.target_growth_rate` under a separate "simulation" copy → rejected; growth rate is a workforce economic assumption

## R2: API Design — Bulk Apply Endpoint

**Decision**: Add a new `POST /{workspace_id}/scenarios/{scenario_id}/apply-workforce-params` endpoint that reads workforce params from the source scenario and writes them to multiple target scenarios.

**Rationale**:
- Server-side approach because the operation modifies multiple scenarios atomically
- Source scenario is identified by URL path (the "current" scenario)
- Target scenarios are specified in the request body
- Returns per-scenario success/failure for partial failure handling

**Alternatives Considered**:
- Client-side loop calling `updateScenario()` per target → rejected; no atomicity guarantees, race conditions, poor error handling
- Generic "copy params" endpoint with parameter category selection → over-engineered for the use case; YAGNI

## R3: Frontend Update Strategy

**Decision**: Add a new `ApplyWorkforceParamsModal` component triggered from `ConfigStudio.tsx`, separate from the existing `CopyScenarioModal`.

**Rationale**:
- Different UX flow: CopyScenarioModal copies FROM another scenario INTO the current form (single source → single target). The new modal applies FROM current scenario TO multiple targets (single source → multiple targets).
- CopyScenarioModal is client-side only (populates form state). The new modal calls a server-side API.
- Keeping them separate avoids complicating the existing copy flow.

**Alternatives Considered**:
- Extend CopyScenarioModal with a "direction" toggle → rejected; fundamentally different flow (one-to-many vs. one-to-one)
- Add to scenario list page instead of config page → rejected; issue spec explicitly places it on the config page

## R4: Notification System

**Decision**: Use inline status feedback (banner + button state) consistent with the existing save flow. No new toast library needed.

**Rationale**: The existing ConfigStudio already uses `saveStatus` state with banner messages for success/error. The apply operation can follow the same pattern within the modal, plus close the modal on success with a brief status message.

**Alternatives Considered**:
- Add a toast notification library (react-hot-toast, sonner) → rejected; adds dependency for one feature; can be added later as a separate enhancement
- Use browser `alert()` → rejected; poor UX

## R5: Config Update Mechanics

**Decision**: For each target scenario, read its current `config_overrides`, selectively replace workforce keys while preserving DC plan keys, then call `update_scenario()` with the merged result.

**Rationale**: The existing `update_scenario()` method replaces the entire `config_overrides` dict. To preserve DC plan parameters, we must read-merge-write. Seed configs (`promotion_hazard`, `age_bands`, `tenure_bands`) are already treated as atomic replacement sections by the storage layer, which aligns perfectly.

**Alternatives Considered**:
- Add a PATCH-style partial update to storage layer → over-engineered; read-merge-write is simple and sufficient for <10 scenarios
- Copy at the dbt seed level → wrong layer; this is a UI/API config operation
