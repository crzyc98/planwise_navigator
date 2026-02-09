# Tasks: Promotion Hazard Configuration UI

**Input**: Design documents from `/specs/038-promotion-probability-ui/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: No automated test tasks generated — the spec does not explicitly request automated tests. Backend service unit tests are recommended but not tracked here.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Phase 1: Setup (Backend Models & Service Infrastructure)

**Purpose**: Create the backend Pydantic models and CSV service that both user stories depend on. These are new files that don't exist yet.

- [x] T001 [P] Create Pydantic models (`PromotionHazardBase`, `PromotionHazardAgeMultiplier`, `PromotionHazardTenureMultiplier`, `PromotionHazardConfig`, `PromotionHazardSaveResponse`) in `planalign_api/models/promotion_hazard.py` per contracts/promotion-hazard-api.md
- [x] T002 Create promotion hazard service with CSV read methods (`read_base_config`, `read_age_multipliers`, `read_tenure_multipliers`, `read_all`) following `planalign_api/services/band_service.py` pattern in `planalign_api/services/promotion_hazard_service.py`. Default seeds dir: `Path(__file__).parent.parent.parent / "dbt" / "seeds"`. Use `csv.DictReader` for reads.
- [x] T003 Add `validate` method to service that checks: base_rate 0–1, level_dampener_factor 0–1, all multipliers >= 0, correct row counts (6 age, 5 tenure). Returns `List[str]` of error messages. In `planalign_api/services/promotion_hazard_service.py`
- [x] T004 Add `save_all` method to service that validates config then writes all 3 CSVs using `csv.DictWriter`. Returns `PromotionHazardSaveResponse`. In `planalign_api/services/promotion_hazard_service.py`

**Checkpoint**: Backend models and service exist. Can be tested by importing and calling `service.read_all()` from Python.

---

## Phase 2: Foundational (Backend Router & Registration)

**Purpose**: Wire the service to HTTP endpoints so the frontend can call it. MUST be complete before any frontend work.

**CRITICAL**: No frontend user story work can begin until this phase is complete.

- [x] T005 Create router with `GET /{workspace_id}/config/promotion-hazards` and `PUT /{workspace_id}/config/promotion-hazards` endpoints in `planalign_api/routers/promotion_hazard.py`. Follow `planalign_api/routers/bands.py` pattern — use `get_promotion_hazard_service()` helper (not FastAPI Depends).
- [x] T006 [P] Export `promotion_hazard_router` from `planalign_api/routers/__init__.py` — add `from .promotion_hazard import router as promotion_hazard_router`
- [x] T007 Register promotion hazard router in `planalign_api/main.py` — add `app.include_router(promotion_hazard_router, prefix="/api/workspaces", tags=["Promotion Hazard"])`

**Checkpoint**: API endpoints functional. Can be tested with `curl http://localhost:8000/api/workspaces/test/config/promotion-hazards`.

---

## Phase 3: User Story 1 — View Promotion Hazard Parameters (Priority: P1) MVP

**Goal**: Display the "Promotion Hazard" section on the Configuration page showing base parameters, age multipliers, and tenure multipliers loaded from seed CSVs.

**Independent Test**: Load the Configuration page in PlanAlign Studio, scroll to the Promotion Hazard section (after Market Positioning), and verify the base rate (2%), level dampener (15%), and all 11 multiplier values match the seed CSV data.

### Implementation for User Story 1

- [x] T008 [P] [US1] Add TypeScript interfaces (`PromotionHazardBase`, `PromotionHazardAgeMultiplier`, `PromotionHazardTenureMultiplier`, `PromotionHazardConfig`, `PromotionHazardSaveResponse`) and `getPromotionHazardConfig(workspaceId)` API function in `planalign_studio/services/api.ts`. Follow the band config interfaces pattern (~line 890).
- [x] T009 [US1] Add state variables to `ConfigStudio.tsx`: `promotionHazardConfig` (nullable `PromotionHazardConfig`), `promotionHazardLoading` (boolean), `promotionHazardError` (nullable string). Follow the band config state pattern (~line 143). In `planalign_studio/components/ConfigStudio.tsx`
- [x] T010 [US1] Add `useEffect` to load promotion hazard config when `activeWorkspace` changes — call `getPromotionHazardConfig(activeWorkspace.id)`, set loading/error/config states. Follow band config load pattern (~line 902). In `planalign_studio/components/ConfigStudio.tsx`
- [x] T011 [US1] Add read-only "Promotion Hazard" UI section after Market Positioning (~line 2395) in `planalign_studio/components/ConfigStudio.tsx` with: (a) section header "Promotion Hazard", (b) base parameters row — 2 inline inputs showing `base_rate * 100` (%) and `level_dampener_factor * 100` (%), (c) age multipliers table — 6 rows with read-only band label + multiplier value, (d) tenure multipliers table — 5 rows with read-only band label + multiplier value. Follow band table styling from (~line 2525).

**Checkpoint**: Promotion Hazard section is visible with all 13 values loaded from the API. Values are display-only at this point.

---

## Phase 4: User Story 2 — Edit and Save Promotion Hazard Parameters (Priority: P2)

**Goal**: Allow users to edit all 13 promotion hazard values and persist them to the seed CSVs on save.

**Independent Test**: Change the base rate from 2% to 5%, save, reload the page, and verify 5% persists. Change an age multiplier, save, reload, verify persistence. Enter a negative multiplier, attempt save, verify validation error.

### Implementation for User Story 2

- [x] T012 [P] [US2] Add `savePromotionHazardConfig(workspaceId, config)` API function in `planalign_studio/services/api.ts`. Follow the `saveBandConfigs` pattern.
- [x] T013 [US2] Convert read-only displays to editable inputs in `planalign_studio/components/ConfigStudio.tsx`: (a) base rate and level dampener become `<input type="number">` fields, (b) age multiplier values become editable inputs, (c) tenure multiplier values become editable inputs. Wire all to change handlers that update `promotionHazardConfig` state.
- [x] T014 [US2] Add change handlers for promotion hazard parameters in `planalign_studio/components/ConfigStudio.tsx`: `handlePromotionHazardBaseChange(field, value)` for base params, `handlePromotionHazardAgeMultiplierChange(index, value)` for age multipliers, `handlePromotionHazardTenureMultiplierChange(index, value)` for tenure multipliers. Follow `handleBandChange` pattern (~line 925).
- [x] T015 [US2] Add client-side validation function `validatePromotionHazardConfig(config)` in `planalign_studio/components/ConfigStudio.tsx`: base_rate 0–100%, level_dampener 0–100%, all multipliers >= 0. Returns list of error strings. Follow `validateBandsClient` pattern (~line 951).
- [x] T016 [US2] Add save handler `handleSavePromotionHazard()` in `planalign_studio/components/ConfigStudio.tsx`: runs client validation, converts percentages to decimals (display / 100 for base_rate and level_dampener), calls `savePromotionHazardConfig`, handles success/error states. Follow `handleSaveBands` pattern (~line 1016).
- [x] T017 [US2] Add save button with loading/success/error state display and validation error list below the promotion hazard section in `planalign_studio/components/ConfigStudio.tsx`. Add `promotionHazardSaveStatus` and `promotionHazardValidationErrors` state variables.

**Checkpoint**: Full edit/save/reload round-trip works. Validation prevents invalid values. Save button shows loading/success/error feedback.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, backward compatibility, and manual validation

- [x] T018 [P] Verify edge cases: base rate 0% (accepted — no promotions), multiplier 0 (accepted), level dampener 0% (accepted — no dampening), base rate 100% (accepted). Manual testing in browser.
- [x] T019 [P] Verify error handling: missing CSV file shows informational error (not crash), malformed CSV handled gracefully. Test by temporarily renaming a seed CSV and loading the page.
- [x] T020 Run quickstart.md full validation: start studio, open workspace, verify section displays, edit base rate 2% → 5% → save → reload → verify, edit age multiplier → save → reload → verify, test negative multiplier validation.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately. T001 is parallel (different file). T002–T004 are sequential (same file, building on each other).
- **Foundational (Phase 2)**: Depends on Phase 1 (T001–T004). T005 depends on T001+T002. T006 and T007 are parallel with each other but depend on T005.
- **User Story 1 (Phase 3)**: Depends on Phase 2 completion. T008 is parallel (different file — api.ts). T009–T011 are sequential (same file — ConfigStudio.tsx, building state then UI).
- **User Story 2 (Phase 4)**: Depends on Phase 3 completion (needs display section before editing). T012 is parallel (different file — api.ts). T013–T017 are sequential (same file — ConfigStudio.tsx).
- **Polish (Phase 5)**: Depends on Phase 4 completion. T018, T019, T020 can run in parallel (independent validation).

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependencies on US2
- **User Story 2 (P2)**: Depends on US1 being complete (editing requires the section to be visible and loading to work)

### Within Each User Story

- Models/interfaces before services/handlers
- Services before endpoints/UI
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- T001 (models) parallel with nothing in Phase 1 (but T002–T004 build sequentially)
- T006 and T007 parallel (different files: `__init__.py` and `main.py`)
- T008 (api.ts) parallel with T009–T011 (ConfigStudio.tsx) in US1
- T012 (api.ts) parallel with T013–T017 (ConfigStudio.tsx) in US2
- T018, T019, T020 all parallel (independent validation checks)

---

## Parallel Example: User Story 1

```
# These can run in parallel (different files):
T008: Add TS interfaces and getPromotionHazardConfig in api.ts
T009: Add state variables in ConfigStudio.tsx

# Then sequentially (same file, depends on T009):
T010: Add useEffect to load config
T011: Add UI section
```

## Parallel Example: User Story 2

```
# These can run in parallel (different files):
T012: Add savePromotionHazardConfig in api.ts
T013: Convert read-only to editable inputs in ConfigStudio.tsx

# Then sequentially (same file, depends on T013):
T014: Add change handlers
T015: Add client-side validation
T016: Add save handler
T017: Add save button with status display
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T004) — Backend models + service
2. Complete Phase 2: Foundational (T005–T007) — API endpoints
3. Complete Phase 3: User Story 1 (T008–T011) — Display section
4. **STOP and VALIDATE**: Load Configuration page, verify Promotion Hazard section appears with correct values from seed CSVs
5. This alone delivers visibility value (SC-001)

### Incremental Delivery

1. T001–T004 → Backend ready (models + service)
2. T005–T007 → API ready (GET/PUT endpoints)
3. T008–T011 → **User Story 1 complete** → Promotion Hazard section visible with correct values (MVP)
4. T012–T017 → **User Story 2 complete** → Edit, validate, and save works end-to-end
5. T018–T020 → **Polish complete** → Edge cases validated, error handling confirmed

---

## Notes

- Backend: 3 new files (`models/promotion_hazard.py`, `services/promotion_hazard_service.py`, `routers/promotion_hazard.py`) + 2 modifications (`routers/__init__.py`, `main.py`)
- Frontend: 2 modifications (`api.ts`, `ConfigStudio.tsx`)
- Uses **band config CSV-direct pattern** (not workspace YAML) — writes directly to seed CSVs
- Conversion: base_rate and level_dampener stored as decimal (0.02), displayed as percentage (2%). Multipliers displayed as-is (no conversion).
- All 13 editable values come from 3 seed CSVs consumed by `dim_promotion_hazards.sql`
- Band labels (age_band, tenure_band) are read-only — only multiplier values are editable
