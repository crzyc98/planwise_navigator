# Tasks: Fix DC Plan Match UI for Tenure-Based and Points-Based Modes

**Input**: Design documents from `/specs/083-fix-dc-match-ui/`
**Branch**: `083-fix-dc-match-ui`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: Not requested. Manual browser verification via `planalign studio`.

**Organization**: 2 user stories, both P1. Changes touch different files so all implementation tasks are parallelizable.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

**Purpose**: Confirm understanding of current code before making changes

- [x] T001 Read `planalign_studio/components/config/ConfigContext.tsx` lines 140–167 to confirm the load path bug (convertRateToPercent on match_rate for tenure/points tiers)
- [x] T002 [P] Read `planalign_studio/components/config/buildConfigPayload.ts` lines 95–115 to confirm the save path is already correct (divides matchRate by 100)
- [x] T003 [P] Read `planalign_studio/components/config/DCPlanSection.tsx` lines 204–296 (tenure editor) and lines 299–393 (points editor) to understand the current row layout

**Checkpoint**: Both files read and understood — confirms fix scope is exactly 2 files

---

## Phase 2: Foundational (Blocking Prerequisites)

No foundational blocking tasks. Both user stories are independent and can start immediately after Phase 1.

---

## Phase 3: User Story 2 - Match Rate Accepts Values Greater Than 100% (Priority: P1) 🎯 MVP

**Goal**: Fix the load deserialization bug so entering 200% match rate in a tenure or points tier persists as 200%, not 2%.

**Independent Test**: Launch `planalign studio` → open a scenario → DC Plan config → switch to Tenure-Based → add a tier → enter `200` in the match rate field → save → reopen scenario → confirm match rate shows `200`, not `2`.

### Implementation for User Story 2

- [x] T004 [US2] In `planalign_studio/components/config/ConfigContext.tsx` line 149, replace `matchRate: convertRateToPercent(t.match_rate, 0),` with `matchRate: (t.match_rate ?? 0) * 100,` inside the `dcTenureMatchTiers` map
- [x] T005 [US2] In `planalign_studio/components/config/ConfigContext.tsx` line 156, replace `matchRate: convertRateToPercent(t.match_rate, 0),` with `matchRate: (t.match_rate ?? 0) * 100,` inside the `dcPointsMatchTiers` map

**Checkpoint**: Save a tenure tier with match rate 200, reload the page — the field must show 200, not 2

---

## Phase 4: User Story 1 - Deferral Range Format in Tenure/Points Tier Rows (Priority: P1)

**Goal**: Reorder the tenure-based and points-based tier row fields so the deferral range (`0% to X% deferrals → Y% match`) appears in the same format as deferral-based tiers.

**Independent Test**: Launch `planalign studio` → open a scenario → DC Plan config → switch to Tenure-Based → confirm each tier row reads `[minYears] to [maxYears] yrs | 0% to [maxDeferralPct]% deferrals → [matchRate]% match`. Repeat for Points-Based.

### Implementation for User Story 1

- [x] T006 [US1] In `planalign_studio/components/config/DCPlanSection.tsx` tenure tier editor (lines ~210–257), reorder the inline elements within each tier row:
  - Keep the `minYears` and `maxYears` inputs and their `to` / `yrs` labels on the left as the tier identifier
  - Add a `|` or short separator label after the years range
  - Change the static label from `yrs →` to `yrs |`
  - Add a static `0% to` text label
  - Move the `maxDeferralPct` input immediately after `0% to`
  - Change the label after `maxDeferralPct` to `% deferrals →`
  - Move the `matchRate` input immediately after `% deferrals →`
  - Change the label after `matchRate` to `% match`
  - Remove the old `% match, max` and `% def` labels entirely
- [x] T007 [US1] In `planalign_studio/components/config/DCPlanSection.tsx` points tier editor (lines ~305–354), apply the same row reorder pattern:
  - Keep `minPoints` and `maxPoints` inputs and labels on the left
  - Add separator: change `pts →` to `pts |`
  - Add static `0% to` label
  - Move `maxDeferralPct` input after `0% to`, label it `% deferrals →`
  - Move `matchRate` input after `% deferrals →`, label it `% match`
  - Remove `% match, max` and `% def` labels

**Checkpoint**: Both tenure and points tier rows should visually match the deferral-based row format — `X% to X% deferrals → matchRate% match` is the prominent reading

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Verify both stories together and confirm no regressions

- [ ] T008 Launch `planalign studio` and run the full manual test from `specs/083-fix-dc-match-ui/quickstart.md`: test tenure-based with 200% match rate (verifies US2 fix), confirm row display format (verifies US1 layout), then test points-based mode, then switch to deferral-based mode to confirm no regressions
- [ ] T009 [P] Verify the `Add Tier` button for both tenure and points modes still auto-populates new tiers correctly (minYears/maxPoints auto-set from previous tier)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001, T002, T003 are all parallelizable
- **Phase 3 (US2 bug fix)**: Depends on T001–T002 being read; T004 and T005 are both in `ConfigContext.tsx` but on different blocks — do T004 first then T005 (same file, sequential edits)
- **Phase 4 (US1 UI layout)**: Depends on T003 being read; T006 and T007 are in the same file (`DCPlanSection.tsx`) but in separate sections — do T006 then T007
- **Phase 3 and Phase 4 are fully independent** (different files) and can be worked in parallel
- **Polish (Phase 5)**: Depends on Phase 3 AND Phase 4 complete

### Parallel Opportunities

- T001, T002, T003 (Setup reads) — fully parallel
- Phase 3 (ConfigContext.tsx) and Phase 4 (DCPlanSection.tsx) — fully parallel (different files)
- T008, T009 (Polish) — parallel

---

## Parallel Example

```bash
# All setup reads in parallel:
Task: "Read ConfigContext.tsx lines 140-167"           # T001
Task: "Read buildConfigPayload.ts lines 95-115"        # T002
Task: "Read DCPlanSection.tsx lines 204-393"           # T003

# After setup, both stories in parallel (different files):
Task: "Fix ConfigContext.tsx load bug (US2)"           # T004, T005
Task: "Redesign DCPlanSection.tsx row layout (US1)"    # T006, T007
```

---

## Implementation Strategy

### MVP First (Either Story Independently)

Both stories are P1 and independent. The bug fix (US2, Phase 3) is the quickest win — 2 line changes, immediately verifiable. Recommend completing US2 first for a fast confidence check, then US1.

1. Complete Phase 1: Setup reads (parallel)
2. Complete Phase 3: US2 bug fix (T004, T005) — 2 line changes in ConfigContext.tsx
3. **VALIDATE**: Test 200% match rate roundtrip in studio
4. Complete Phase 4: US1 UI layout (T006, T007) — row reorder in DCPlanSection.tsx
5. **VALIDATE**: Confirm deferral-range format in tenure/points modes
6. Complete Phase 5: Full regression check

### Total Scope

| Phase | Tasks | Files |
|-------|-------|-------|
| Setup | T001–T003 | 3 reads |
| US2 Bug Fix | T004–T005 | ConfigContext.tsx (2 lines) |
| US1 UI Layout | T006–T007 | DCPlanSection.tsx (2 sections) |
| Polish | T008–T009 | Manual verification |
| **Total** | **9 tasks** | **2 source files** |

---

## Notes

- [P] tasks = different files or independent operations, no blocking dependencies
- [Story] label maps to user stories in spec.md
- No test files to write — manual browser verification per quickstart.md
- No backend, API, or dbt changes
- Existing `max={200}` on the matchRate HTML inputs is already correct — no input element changes needed for the bug fix
- The `convertRateToPercent` function is intentionally left unchanged (still correct for `maxDeferralPct` which is always stored as a decimal ≤ 1)
