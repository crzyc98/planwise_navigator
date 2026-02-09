# Tasks: Per-Scenario Seed Configuration

**Input**: Design documents from `/specs/039-per-scenario-seed-config/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Exact file paths included in descriptions

## Phase 1: Setup

**Purpose**: No new project structure needed — this feature modifies existing files. Setup creates the two new foundational modules.

- [x] T001 [P] Create seed config validator service in planalign_api/services/seed_config_validator.py — Pydantic v2 models and validation functions for promotion_hazard (base_rate 0-1, level_dampener 0-1, multipliers >= 0, correct count), age_bands (no gaps, no overlaps, first starts at 0, max > min), and tenure_bands (same rules). Return structured error objects with section, field, and message. See data-model.md for field definitions and validation rules.
- [x] T002 [P] Create seed CSV writer module in planalign_orchestrator/pipeline/seed_writer.py — Functions to write config dicts to CSV files: write_promotion_hazard_csvs(config, seeds_dir), write_band_csvs(config, seeds_dir), write_all_seed_csvs(merged_config, seeds_dir). Each reads the relevant section from merged config dict and writes to the 5 CSV files listed in data-model.md (config_promotion_hazard_base.csv, config_promotion_hazard_age_multipliers.csv, config_promotion_hazard_tenure_multipliers.csv, config_age_bands.csv, config_tenure_bands.csv). If a section is absent from config, skip writing that CSV (leave global default in place).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend infrastructure that all user stories depend on — merged config fallback and validation wiring.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Extend get_merged_config() in planalign_api/storage/workspace_storage.py to include global CSV fallback — After the existing _deep_merge(base_config, config_overrides), check if the merged result contains promotion_hazard, age_bands, and tenure_bands keys. For each missing key, read the corresponding global CSV seed files (using existing PromotionHazardService.read_all() and BandService.read_band_configs()) and inject the values into the merged config dict. This implements the 3-tier fallback: scenario overrides → workspace base_config → global CSVs (FR-007, FR-008).
- [x] T004 Add seed config validation to scenario update in planalign_api/routers/scenarios.py — In the PUT /workspaces/{workspace_id}/scenarios/{scenario_id} handler, before calling storage.update_scenario(), extract promotion_hazard, age_bands, and tenure_bands from config_overrides (if present). Validate each using seed_config_validator.py (T001). If any validation fails, return 422 with structured error response per api-contracts.md. This enforces atomic save (FR-004): if any section invalid, reject entire update. Apply same validation in PUT /workspaces/{workspace_id} for base_config updates.

**Checkpoint**: Backend now accepts seed configs in config_overrides and resolves the full merge chain. Validation rejects invalid seed configs atomically.

---

## Phase 3: User Story 1 — Unified Save Experience (Priority: P1) MVP

**Goal**: Single "Save Changes" button persists all config types (main + promotion hazard + bands) atomically. Dirty tracking covers all config sections.

**Independent Test**: Edit simulation params, promotion hazard base_rate, and age band boundaries. Click "Save Changes". Reload page. All three categories of changes are retained.

### Implementation for User Story 1

- [x] T005 [US1] Integrate promotion hazard and band state into formData in planalign_studio/components/ConfigStudio.tsx — Add promotionHazard (base_rate, level_dampener_factor, age_multipliers, tenure_multipliers) and ageBands, tenureBands fields to the formData state object. On scenario/workspace load, populate these fields from the merged config response (GET /scenarios/{id}/config). Remove the separate useState hooks for promotionHazardConfig, bandConfig, and their associated loading/error/saveStatus states. Update savedFormData to include these new fields so isDirty and dirtySections calculations cover seed configs (FR-012).
- [x] T006 [US1] Update handleSaveConfig in planalign_studio/components/ConfigStudio.tsx to include seed configs in the config_overrides payload — When building the configPayload for updateScenario(), add promotion_hazard, age_bands, and tenure_bands from formData. Remove the separate promotion hazard save call that currently exists inside handleSaveConfig (lines ~1378-1396). Remove the separate handleSaveBands handler. Remove the separate handleSavePromotionHazard handler. All saves now go through the single updateScenario/updateWorkspace call (FR-004).
- [x] T007 [US1] Remove separate save buttons from ConfigStudio.tsx — Delete the "Save Band Configurations" button (around line 2997) and the "Save Promotion Hazard" button. Remove associated save status indicators (bandSaveStatus, promotionHazardSaveStatus). The main "Save Changes" button at the top is now the only save action (FR-005). Keep the band editing UI and promotion hazard editing UI intact — only the separate save buttons are removed.
- [x] T008 [US1] Remove savePromotionHazardConfig() and saveBandConfigs() from planalign_studio/services/api.ts — These functions call the PUT endpoints that are being deprecated. Remove them. Keep getPromotionHazardConfig(), getBandConfigs(), analyzeAgeBands(), analyzeTenureBands() (they are still used for reading global defaults and census analysis).
- [x] T009 [US1] Remove PUT endpoints from promotion hazard and band routers — In planalign_api/routers/promotion_hazard.py, remove the PUT /config/promotion-hazards endpoint (keep GET). In planalign_api/routers/bands.py (find actual router file), remove the PUT /config/bands endpoint (keep GET). Update planalign_api/routers/__init__.py if needed.
- [x] T010 [US1] Add client-side validation for seed configs in ConfigStudio.tsx — Before calling the save API, validate promotion_hazard and band configs client-side using the existing validatePromotionHazardConfig() and validateBandsClient() functions. If validation fails, show error indicators on the relevant sections and block the save. Display validation errors inline (same UX as current band validation). This provides immediate feedback before the server-side atomic validation (FR-010, FR-011).

**Checkpoint**: US1 complete — single save button persists all config types. Dirty tracking covers seed configs. Separate save buttons removed.

---

## Phase 4: User Story 2 — Per-Scenario Seed Config Isolation (Priority: P1)

**Goal**: Each scenario stores its own promotion hazard rates and band definitions. At simulation time, the orchestrator writes scenario-specific CSVs so dbt uses per-scenario values.

**Independent Test**: Create two scenarios with different promotion hazard base_rates. Run simulations for both. Verify each simulation produces different promotion event counts.

### Implementation for User Story 2

- [x] T011 [US2] Wire orchestrator to write seed CSVs from merged config before dbt seed in planalign_orchestrator/pipeline_orchestrator.py — In the simulation initialization flow (around lines 588-605, where `dbt seed` runs), add a call to write_all_seed_csvs() (from T002) before running dbt seed. The orchestrator should call get_merged_config(workspace_id, scenario_id) to get the fully resolved config (including CSV fallback from T003), then pass it to the seed writer. Log which seed config source was used (scenario override, workspace default, or global CSV) for audit transparency (FR-009, Principle IV).
- [x] T012 [US2] Update frontend to load seed configs from merged scenario config instead of global endpoints in planalign_studio/components/ConfigStudio.tsx — Currently, promotion hazard and band configs load via useEffect hooks that call getPromotionHazardConfig(workspaceId) and getBandConfigs(workspaceId) on workspace change. Change these to load from the merged scenario config response (GET /scenarios/{id}/config which now includes seed config sections from T003). When viewing workspace base config (no scenario selected), load from GET /workspaces/{id}/config or fall back to the global GET endpoints. This ensures each scenario shows its own seed config values.
- [x] T013 [US2] Add dirtySections tracking for seed config tabs in planalign_studio/components/ConfigStudio.tsx — In the dirtySections useMemo, add checks for the promotionHazard, ageBands, and tenureBands fields. Map these to sidebar tab identifiers so the amber dot indicators appear on the correct tabs when seed configs have unsaved changes. Add "promotionhazard" and "bands" (or appropriate section names) to the dirty set when values differ from savedFormData.

**Checkpoint**: US2 complete — scenarios have isolated seed configs. Simulations use per-scenario values via orchestrator CSV injection.

---

## Phase 5: User Story 3 — Copy Seed Configs Between Scenarios (Priority: P2)

**Goal**: "Copy from Scenario" includes promotion hazard rates and band definitions alongside YAML config values.

**Independent Test**: Configure custom promotion hazards and bands on Scenario A. Use "Copy from Scenario" into Scenario B. Verify all seed config values match in Scenario B's form.

### Implementation for User Story 3

- [x] T014 [US3] Extend Copy from Scenario handler in planalign_studio/components/ConfigStudio.tsx — In the copy handler (around lines 3684-3844), after copying all existing config_overrides fields into formData, also copy promotion_hazard, age_bands, and tenure_bands from the source scenario's config_overrides. If the source scenario has no seed config overrides (keys absent), do not set them in the target either (inherit workspace/global defaults). This ensures the dirty indicator reflects the copied seed config changes (FR-006).

**Checkpoint**: US3 complete — Copy from Scenario transfers 100% of configurable settings including seed configs.

---

## Phase 6: User Story 4 — Workspace Default Seed Config (Priority: P3)

**Goal**: Workspace-level default seed configs that new scenarios inherit. Editable in the workspace base config editor.

**Independent Test**: Set custom promotion hazard rates at workspace level. Create a new scenario. Verify it inherits the workspace defaults.

### Implementation for User Story 4

- [x] T015 [US4] Ensure workspace base_config editor shows seed config sections in planalign_studio/components/ConfigStudio.tsx — When editing workspace base config (no scenario selected), the promotion hazard and band editing UI should be visible and functional. The formData for workspace mode should include promotionHazard, ageBands, tenureBands. On save, these are included in the base_config payload to PUT /workspaces/{id}. The validation added in T004 already handles workspace updates. Verify that the merged config fallback (T003) resolves workspace defaults correctly when a scenario has no overrides.
- [x] T016 [US4] Verify new scenario inherits workspace seed config defaults — When a new scenario is created (no config_overrides), the GET /scenarios/{id}/config endpoint should return the workspace base_config values for promotion_hazard, age_bands, and tenure_bands (via the merge chain in T003). Verify this works end-to-end: create workspace with custom seed defaults → create scenario → load scenario config → see workspace defaults. No new code may be needed if T003 and T012 are correct — this task is a verification/fix pass.

**Checkpoint**: US4 complete — workspace defaults flow through the merge chain to new scenarios.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, backward compatibility verification, and cleanup.

- [x] T017 [P] Verify backward compatibility — existing scenarios with no seed config overrides in planalign_api/storage/workspace_storage.py — Test that get_merged_config() for an existing scenario (empty config_overrides or config_overrides without promotion_hazard/age_bands/tenure_bands) correctly falls back to global CSV values. Verify no data migration is needed (FR-014).
- [x] T018 [P] Update Match Census band suggestion to target scenario form state in planalign_studio/components/ConfigStudio.tsx — Verify that the analyze-age-bands and analyze-tenure-bands endpoints still work and that their results are applied to formData.ageBands / formData.tenureBands (not saved directly to global CSVs). The API endpoints are unchanged (T009 kept GETs and POSTs), but the frontend handlers may need updating to write to formData instead of bandConfig state (FR-013).
- [x] T019 [P] Handle section-level replacement in _deep_merge() if needed in planalign_api/storage/workspace_storage.py — Verify that _deep_merge() handles promotion_hazard correctly. Since promotion_hazard contains nested objects (age_multipliers list), _deep_merge() may recursively merge instead of replace. If so, adjust the merge logic to treat promotion_hazard, age_bands, and tenure_bands as atomic sections that replace entirely (FR-015). Test: scenario overrides promotion_hazard with different base_rate and multipliers → merged config should use 100% of scenario's promotion_hazard, not a mix.
- [x] T020 Run existing test suite to verify no regressions — Run pytest -m fast and check that existing tests pass. Particular attention to test_deferral_orphaned_states and test_deferral_state_continuity which have known expectation mismatches. Verify promotion hazard and band-related tests still pass with the refactored API layer.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — T001 and T002 can start immediately and run in parallel
- **Phase 2 (Foundational)**: Depends on T001 (validator) and T002 (seed writer)
- **Phase 3 (US1)**: Depends on Phase 2 completion (T003, T004)
- **Phase 4 (US2)**: Depends on Phase 2 completion; can run in parallel with US1 if desired, but US1 is recommended first since it establishes the unified state model
- **Phase 5 (US3)**: Depends on US1 (T005 — formData restructure must be done first)
- **Phase 6 (US4)**: Depends on US2 (T012 — merged config loading must work for scenarios before workspace defaults can be tested)
- **Phase 7 (Polish)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (Unified Save)**: Depends on Phase 2 only. MVP — delivers unified save experience.
- **US2 (Per-Scenario Isolation)**: Depends on Phase 2. Can technically start in parallel with US1, but US1's formData restructure (T005) simplifies US2 work.
- **US3 (Copy Scenario)**: Depends on US1 (needs the unified formData structure from T005).
- **US4 (Workspace Defaults)**: Depends on US2 (needs merged config loading from T012). Lightest story — mostly verification.

### Recommended Execution Order

```
T001 ─┐
      ├─→ T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 (US1 MVP)
T002 ─┘                    ↓
                     T011 → T012 → T013 (US2)
                              ↓
                         T014 (US3)
                              ↓
                     T015 → T016 (US4)
                              ↓
                     T017, T018, T019, T020 (Polish — parallel)
```

### Parallel Opportunities

**Phase 1**: T001 and T002 are independent (different packages, no shared code)
**Phase 7**: T017, T018, T019, T020 are all independent verification/fix tasks

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: T001 + T002 (parallel, ~30 min)
2. Complete Phase 2: T003 + T004 (sequential, ~45 min)
3. Complete Phase 3: T005-T010 (US1, ~2 hours)
4. **STOP and VALIDATE**: Edit all config types → Save → Reload → Verify all persisted
5. This delivers the unified save experience without per-scenario isolation

### Full Delivery

1. MVP (US1) → validates unified save works
2. US2 (T011-T013) → per-scenario isolation via orchestrator
3. US3 (T014) → copy from scenario includes seed configs
4. US4 (T015-T016) → workspace defaults (mostly verification)
5. Polish (T017-T020) → edge cases and backward compatibility

---

## Notes

- No dbt model SQL changes required — orchestrator writes CSVs that dbt reads via existing {{ ref() }} mechanism
- Global CSV files in dbt/seeds/ remain as fallback defaults — they are never deleted
- Atomic save: if any config section fails validation, the entire save is rejected (422)
- Section-level replacement: promotion_hazard, age_bands, tenure_bands each replace as whole units (no field-level merge)
- ConfigStudio.tsx is a large component (~4000 lines) — task descriptions include approximate line numbers where relevant
