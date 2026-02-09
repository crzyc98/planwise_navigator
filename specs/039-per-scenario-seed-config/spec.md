# Feature Specification: Per-Scenario Seed Configuration

**Feature Branch**: `039-per-scenario-seed-config`
**Created**: 2026-02-09
**Status**: Draft
**Input**: Unify seed-based configs (promotion hazard, age/tenure bands) to be per-scenario instead of global. Single save button. Include in copy-from-scenario.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Unified Save Experience (Priority: P1)

As a plan administrator, I want a single "Save Changes" button that persists all configuration changes — including promotion hazard rates and band definitions — so that I don't have to remember to click multiple save buttons or worry about losing partial changes.

**Why this priority**: The fragmented save experience is the most immediately visible pain point. Users risk saving main config but forgetting to save bands or promotion hazards, leading to inconsistent scenario state. A unified save eliminates an entire class of user errors.

**Independent Test**: Can be tested by making changes across all config sections (main settings, promotion hazard, bands) and confirming a single save persists everything. Verified by reloading the page and checking all values are retained.

**Acceptance Scenarios**:

1. **Given** a user has edited simulation parameters, promotion hazard base rate, and age band boundaries, **When** the user clicks the single "Save Changes" button, **Then** all three categories of changes are persisted and reflected on page reload.
2. **Given** a user has edited only promotion hazard settings (no main config or band changes), **When** the user clicks "Save Changes", **Then** only the changed promotion hazard values are updated; unchanged configs remain as-is.
3. **Given** a user has unsaved changes in any config section, **When** the dirty indicator appears, **Then** it reflects unsaved changes across all config types (not just YAML-based ones).

---

### User Story 2 - Per-Scenario Seed Config Isolation (Priority: P1)

As a plan administrator running multiple scenarios, I want each scenario to have its own promotion hazard rates and band definitions so that Scenario A (e.g., "aggressive promotions") can use different rates than Scenario B (e.g., "conservative baseline") without one overwriting the other.

**Why this priority**: This is the core architectural change that enables the feature. Without per-scenario isolation, scenarios cannot meaningfully differ in promotion or segmentation behavior, severely limiting the value of scenario comparison.

**Independent Test**: Can be tested by creating two scenarios, setting different promotion hazard base rates in each, running simulations for both, and confirming each simulation uses its own configured rates (visible in simulation output or event counts).

**Acceptance Scenarios**:

1. **Given** Scenario A has promotion base rate 0.10 and Scenario B has promotion base rate 0.25, **When** both scenarios are simulated, **Then** Scenario A produces fewer promotion events than Scenario B (proportional to rate difference).
2. **Given** a scenario with no seed config overrides, **When** the scenario is simulated, **Then** the global default seed values (from the global seed CSV files) are used as fallback.
3. **Given** a user edits promotion hazard rates for Scenario A, **When** the user switches to Scenario B, **Then** Scenario B still shows its own (unchanged) promotion hazard rates.
4. **Given** a user edits age band boundaries for a scenario, **When** the scenario is simulated, **Then** the simulation uses the scenario-specific band definitions (not the global defaults).

---

### User Story 3 - Copy Seed Configs Between Scenarios (Priority: P2)

As a plan administrator, I want "Copy from Scenario" to include promotion hazard rates and band definitions so that I can quickly create scenario variants without manually re-entering seed-based configurations.

**Why this priority**: Copy-from-scenario is the primary workflow for creating scenario variants. If it skips seed configs, users must manually duplicate those settings — tedious and error-prone for complex band or hazard configurations.

**Independent Test**: Can be tested by configuring custom promotion hazards and bands on Scenario A, then using "Copy from Scenario" to copy into Scenario B, and verifying all seed config values match.

**Acceptance Scenarios**:

1. **Given** Scenario A has custom promotion hazard rates and custom age bands, **When** a user copies from Scenario A into Scenario B, **Then** Scenario B receives all of Scenario A's promotion hazard rates and band definitions in addition to YAML config values.
2. **Given** a user copies from Scenario A into Scenario B which already has its own custom seed configs, **When** the copy completes, **Then** Scenario B's seed configs are fully replaced by Scenario A's values (not merged).
3. **Given** a user copies from Scenario A, **When** the copy completes but before saving, **Then** the user can review all copied values (including seed configs) and the dirty indicator reflects unsaved changes.

---

### User Story 4 - Workspace Default Seed Config (Priority: P3)

As a plan administrator, I want to set workspace-level default seed configs (promotion hazard rates, band definitions) that new scenarios inherit, so that I don't have to configure these for every new scenario from scratch.

**Why this priority**: Without workspace defaults, every new scenario starts with the global CSV values, requiring manual configuration. Workspace defaults reduce repetitive setup while preserving per-scenario override capability.

**Independent Test**: Can be tested by setting custom promotion hazard rates at the workspace level, creating a new scenario, and confirming the new scenario inherits the workspace defaults.

**Acceptance Scenarios**:

1. **Given** a workspace has custom default promotion hazard rates configured, **When** a new scenario is created in that workspace, **Then** the new scenario inherits the workspace's promotion hazard defaults (not the global CSV values).
2. **Given** a workspace has default band definitions and a scenario has its own overrides, **When** the scenario config is loaded, **Then** the scenario's overrides take precedence over workspace defaults.

---

### Edge Cases

- What happens when a scenario has partial seed config overrides (e.g., custom promotion hazard but no custom bands)? Overrides use section-level replacement: if a scenario overrides `promotion_hazard`, the entire promotion hazard block is replaced (base rate, dampener, and all multipliers). Band definitions and promotion hazard are independent sections — overriding one does not require overriding the other. Sections without overrides fall back to workspace/global defaults.
- What happens when global seed CSV files are updated externally (e.g., via direct file edit)? Scenarios with explicit overrides are unaffected; scenarios without overrides pick up the new global defaults on next simulation.
- What happens when band definitions in a scenario create gaps or overlaps? The same validation rules that apply to global band saves apply to per-scenario band saves — invalid configurations are rejected.
- What happens during "Copy from Scenario" if the source scenario has no seed config overrides? The target scenario receives no seed config overrides either (inheriting workspace/global defaults).
- What happens to existing scenarios when this feature is deployed? Existing scenarios have no seed config overrides and continue using global defaults. No data migration is needed.
- What happens when a user clicks "Save Changes" but one section (e.g., bands) has validation errors while others are valid? The entire save is rejected atomically. The user sees validation error indicators on the failing section(s) and must fix all errors before any changes can be saved.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store promotion hazard configuration (base rate, level dampener, age multipliers, tenure multipliers) within a scenario's config overrides, not in global seed CSV files.
- **FR-002**: System MUST store age band definitions within a scenario's config overrides.
- **FR-003**: System MUST store tenure band definitions within a scenario's config overrides.
- **FR-004**: System MUST provide a single "Save Changes" action that atomically persists all configuration categories (simulation parameters, compensation, DC plan, promotion hazard, age bands, tenure bands, and advanced settings) in one operation. If any section fails validation, the entire save is rejected and no changes are persisted.
- **FR-005**: System MUST remove the separate "Save Band Configurations" and "Save Promotion Hazard" buttons from the configuration interface.
- **FR-006**: System MUST include promotion hazard config and band definitions when copying configuration from one scenario to another.
- **FR-007**: System MUST fall back to workspace defaults when a scenario has no explicit seed config overrides. Seed configs (promotion hazard, bands) MUST be editable in the workspace base config editor as workspace-level defaults.
- **FR-008**: System MUST fall back to global seed CSV values when neither the scenario nor the workspace has explicit seed config overrides.
- **FR-009**: System MUST write scenario-specific seed values to the scenario's simulation environment at simulation start, so that the simulation engine picks up the correct per-scenario values.
- **FR-010**: System MUST validate band definitions (no gaps, no overlaps, first band starts at 0, max > min) when saving per-scenario band overrides.
- **FR-011**: System MUST validate promotion hazard values (rates between 0 and 1, correct number of age/tenure band multipliers) when saving per-scenario overrides.
- **FR-012**: System MUST display the dirty indicator (unsaved changes marker) for seed config changes, consistent with how it works for YAML-based config changes.
- **FR-013**: System MUST support the existing "Match Census" band suggestion feature with per-scenario band configs — suggested bands apply to the current scenario, not globally.
- **FR-014**: System MUST preserve backward compatibility — scenarios without explicit seed config overrides continue using global defaults with no behavior change.
- **FR-015**: System MUST use section-level replacement for seed config overrides: when a scenario overrides `promotion_hazard`, the entire promotion hazard block replaces the default (no field-level merging of base_rate, dampener, and multipliers independently). Same applies to `age_bands` and `tenure_bands` — each replaces as a whole unit.

### Key Entities

- **Scenario Config Overrides**: Extended to include `promotion_hazard` and `band_definitions` sections alongside existing simulation/compensation/DC plan settings. Represents a scenario's complete configuration delta from workspace defaults.
- **Workspace Base Config**: Extended to optionally include default `promotion_hazard` and `band_definitions` sections. Provides workspace-level defaults that new scenarios inherit.
- **Promotion Hazard Config**: Contains base_rate, level_dampener_factor, age_multipliers (one per age band), and tenure_multipliers (one per tenure band). Currently stored as three CSV files; will be stored as structured config.
- **Band Definitions**: Contains age_bands (list of min/max/label) and tenure_bands (list of min/max/label). Currently stored as two CSV files; will be stored as structured config.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can save all configuration changes (including promotion hazard and band settings) with a single action, with no more than one "Save" button visible in the configuration interface.
- **SC-002**: Two scenarios within the same workspace can be configured with different promotion hazard base rates, and simulations produce different promotion event counts consistent with their configured rates.
- **SC-003**: "Copy from Scenario" transfers 100% of configurable settings (including promotion hazard and band definitions) — no manual re-entry required for any config that has a UI editor.
- **SC-004**: Existing scenarios (created before this feature) continue to simulate correctly using global defaults with zero manual intervention or data migration.
- **SC-005**: Band validation (gaps, overlaps, boundaries) works identically for per-scenario saves as it does for the current global save flow.
- **SC-006**: All config changes (including seed-type configs) trigger the unsaved-changes indicator, and all are persisted or discarded together.

## Clarifications

### Session 2026-02-09

- Q: When unified save encounters validation errors in one section (e.g., invalid bands) but other sections are valid, should the save be atomic or partial? → A: Atomic — entire save fails if any section has validation errors. No partial persistence.
- Q: When a scenario overrides only part of promotion hazard config (e.g., base_rate but not multipliers), should the merge be field-level or section-level? → A: Section-level replace — if a scenario overrides promotion_hazard, it replaces the entire promotion_hazard block. Same applies to band_definitions (age_bands and tenure_bands each replace as whole units).
- Q: Should seed configs (bands, promotion hazard) be editable at workspace base config level (as defaults) or only at scenario level? → A: Both levels — editable at workspace base config (as defaults that new scenarios inherit) and at scenario level (as overrides).

## Assumptions

- **A-001**: The existing config override merge strategy (deep merge of scenario overrides on top of workspace base config) is sufficient for seed-type configs. No new merge strategy is needed.
- **A-002**: Global seed CSV files (`dbt/seeds/config_*.csv`) will continue to exist as the ultimate fallback defaults. They are not removed.
- **A-003**: Configs that don't currently have UI editors (`config_job_levels.csv`, `config_termination_hazard_base.csv`) remain global-only for now and are out of scope.
- **A-004**: The promotion hazard API endpoints will be refactored since their current design of reading/writing global CSVs is fundamentally incompatible with per-scenario storage.
- **A-005**: At simulation time, scenario-specific seed values will be materialized in a way compatible with the simulation engine's existing seed-loading mechanism. No changes to simulation model logic are needed.
- **A-006**: The "Match Census" band suggestion feature will continue to work by analyzing census data and proposing band boundaries, but the resulting bands will be saved to the scenario's config overrides (not global CSVs).
