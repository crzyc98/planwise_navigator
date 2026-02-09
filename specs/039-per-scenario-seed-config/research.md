# Research: Per-Scenario Seed Configuration

**Branch**: `039-per-scenario-seed-config` | **Date**: 2026-02-09

## R1: Seed Injection Strategy at Simulation Time

**Decision**: Pre-seed copy — write scenario-specific CSV files to `dbt/seeds/` before running `dbt seed` for each scenario simulation.

**Rationale**: This is the least invasive approach. dbt has a hardcoded `seed-paths: ["seeds"]` in `dbt_project.yml` with no CLI override mechanism. Each scenario already gets its own DuckDB database (`{scenario_path}/simulation.duckdb`), and simulations already run sequentially (DuckDB single-writer lock). Writing scenario-specific CSVs to `dbt/seeds/` just before `dbt seed` runs requires no changes to dbt models, staging SQL, or the `{{ ref() }}` mechanism.

**Alternatives considered**:
- **Symlinks**: Scenario-specific seed directories symlinked as `dbt/seeds/`. Rejected — OS-specific behavior, symlink management adds complexity with no benefit over file copy.
- **Dynamic SQL selection**: Seed files per-scenario with `{{ var('scenario_id') }}` routing in staging models. Rejected — requires changes to every staging model and creates seed file explosion.
- **dbt vars injection**: Pass seed values as dbt vars instead of CSVs. Rejected — dbt vars are scalar, not tabular. Band definitions and multiplier arrays don't fit cleanly.

**Concurrency note**: Sequential execution is already enforced by DuckDB's single-writer lock. Writing CSVs before each scenario's `dbt seed` is safe because scenarios cannot run concurrently.

---

## R2: Config Storage Location for Seed-Type Configs

**Decision**: Store seed-type configs (promotion hazard, bands) in the same `config_overrides` / `base_config.yaml` structure used for all other scenario configuration. At simulation time, the orchestrator reads the merged config and writes CSV files.

**Rationale**: The existing `config_overrides` + `base_config.yaml` + `_deep_merge()` pattern already handles workspace defaults vs. scenario overrides. Adding seed-type configs to this structure gives per-scenario isolation, copy-from-scenario support, and workspace defaults for free. The only new work is the "write CSVs from merged config" step in the orchestrator.

**Alternatives considered**:
- **Per-scenario CSV files in workspace storage**: Store CSVs at `workspaces/{wid}/scenarios/{sid}/seeds/*.csv`. Rejected — creates a parallel storage system that doesn't participate in `_deep_merge()` or `get_merged_config()`, requiring custom merge logic.
- **Keep global CSVs, add override layer**: Keep reading from `dbt/seeds/` but allow scenario overrides. Rejected — two sources of truth creates confusion and merge edge cases.

---

## R3: Merge Strategy for Seed Config Sections

**Decision**: Section-level replacement (clarified in spec). When a scenario overrides `promotion_hazard`, the entire block replaces the default. Same for `age_bands` and `tenure_bands`. The existing `_deep_merge()` function handles this correctly because these sections are leaf-level objects (not deeply nested dicts requiring recursive merge).

**Rationale**: Promotion hazard parameters are interdependent — base_rate and multipliers are tuned together. Field-level merging would allow incoherent combinations (e.g., custom base_rate paired with default multipliers not calibrated for it).

**Implementation note**: `_deep_merge()` recurses into nested dicts. To get section-level replacement, the promotion_hazard, age_bands, and tenure_bands values should be stored as lists/flat objects (not nested dicts) so `_deep_merge()` replaces rather than recurses.

---

## R4: Unified Save — API Design

**Decision**: Extend the existing `PUT /workspaces/{wid}/scenarios/{sid}` endpoint to accept promotion hazard and band configs as part of `config_overrides`. Remove the separate `/config/promotion-hazards` and `/config/bands` write endpoints. Keep read endpoints for convenience (they return merged values).

**Rationale**: The unified save requirement (FR-004) means all config must be saved atomically. Using the existing scenario update endpoint maintains the single-write-path pattern. Adding seed configs to `config_overrides` means the frontend sends one payload and the backend validates + persists atomically.

**Alternatives considered**:
- **Backend orchestration of multiple saves**: Frontend sends one request, backend saves to scenario.json + CSVs. Rejected — CSVs are no longer the source of truth; writing to them at save time is unnecessary (only needed at simulation time).
- **New unified endpoint**: `PUT /workspaces/{wid}/scenarios/{sid}/config/all`. Rejected — the existing `PUT /scenarios/{sid}` already accepts `config_overrides` which is the right place for this data.

---

## R5: Backward Compatibility — Global CSV Fallback

**Decision**: Global seed CSVs in `dbt/seeds/` remain as the ultimate fallback. At simulation time, the orchestrator checks: (1) scenario config_overrides for seed sections, (2) workspace base_config for seed sections, (3) global CSVs. The first source found is used.

**Rationale**: Existing scenarios have no seed config in their overrides. They must continue working by falling back to global CSVs. New scenarios get seed configs when users edit them in the UI. Global CSVs also serve as the initial "factory default" values.

**Implementation**: The orchestrator's pre-simulation hook reads merged config via `get_merged_config()`. If `promotion_hazard` / `age_bands` / `tenure_bands` keys are present, write them as CSVs. If absent, leave the existing global CSVs in place (they're already there).

---

## R6: Frontend Dirty Tracking for Seed Configs

**Decision**: Integrate seed config state into the existing `formData` / `savedFormData` dirty tracking system. Add `promotionHazard` and `bandDefinitions` keys to formData.

**Rationale**: The current dirty tracking compares `formData` vs `savedFormData` via JSON stringification. Adding seed configs to formData means they automatically participate in `isDirty` and `dirtySections` calculations. This is simpler than maintaining parallel dirty state for seed configs.

**Current state**: Promotion hazard has separate state (`promotionHazardConfig`, `promotionHazardSaveStatus`). Bands have their own state (`bandConfig`, `bandSaveStatus`). These will be consolidated into formData.
