# Tasks: Fix DC Plan Workspace Context Persistence

**Input**: Design documents from `/specs/054-fix-dcplan-workspace-context/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: No automated tests — no frontend test framework in use. Manual verification via quickstart.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/` (existing React component directory)
- **Reference files** (read-only): `Layout.tsx`, `ScenarioCostComparison.tsx`, `App.tsx`
- **Modified file**: `DCPlanAnalytics.tsx`

---

## Phase 1: Setup

**Purpose**: Understand the existing patterns before making changes

- [x] T001 Read reference pattern in `planalign_studio/components/ScenarioCostComparison.tsx` — note the `useOutletContext<LayoutContextType>()` usage at line 156 and the `useEffect` watching `activeWorkspace?.id` at lines 469-477
- [x] T002 Read the `LayoutContextType` interface in `planalign_studio/components/Layout.tsx` lines 20-36 to confirm the shape of the outlet context

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational phase needed — all infrastructure (Layout context, outlet context pattern, react-router-dom) already exists

**Checkpoint**: Foundation already in place. User story implementation can begin.

---

## Phase 3: User Story 1 — Workspace persists when navigating to DC Plan (Priority: P1) MVP

**Goal**: Replace isolated workspace state in DCPlanAnalytics with shared outlet context so workspace selection persists across navigation

**Independent Test**: Select workspace on Analysis page, navigate to DC Plan, verify workspace is active and scenarios load automatically

### Implementation for User Story 1

- [x] T003 [US1] Add `useOutletContext` import from `react-router-dom` and `LayoutContextType` import from `./Layout` at top of `planalign_studio/components/DCPlanAnalytics.tsx`
- [x] T004 [US1] Add `const { activeWorkspace } = useOutletContext<LayoutContextType>()` inside the component function in `planalign_studio/components/DCPlanAnalytics.tsx`, replacing the isolated workspace state
- [x] T005 [US1] Remove `useState` declarations for `workspaces` and `selectedWorkspaceId` (lines ~91-93) in `planalign_studio/components/DCPlanAnalytics.tsx`
- [x] T006 [US1] Remove the `fetchWorkspaces` function (lines ~133-143) and its mount `useEffect` (lines ~107-109) in `planalign_studio/components/DCPlanAnalytics.tsx`
- [x] T007 [US1] Update the scenario-fetching `useEffect` to watch `activeWorkspace?.id` instead of `selectedWorkspaceId`, and call `fetchScenarios(activeWorkspace.id)` in `planalign_studio/components/DCPlanAnalytics.tsx`
- [x] T008 [US1] Replace all remaining references to `selectedWorkspaceId` with `activeWorkspace?.id` in `fetchAnalytics`, `fetchComparison`, and `handleRefresh` functions in `planalign_studio/components/DCPlanAnalytics.tsx`
- [x] T009 [US1] Remove the redundant workspace dropdown selector UI (lines ~252-268) in `planalign_studio/components/DCPlanAnalytics.tsx`
- [x] T010 [US1] Remove any now-unused imports (e.g., `listWorkspaces` if no longer called) in `planalign_studio/components/DCPlanAnalytics.tsx`

**Checkpoint**: DC Plan page reads workspace from shared context. Selecting workspace on any page persists when navigating to DC Plan. No duplicate workspace selector shown.

---

## Phase 4: User Story 2 — Consistent workspace behavior across all pages (Priority: P2)

**Goal**: Ensure DC Plan page reacts to workspace changes identically to other pages (reload scenarios, clear state)

**Independent Test**: Switch workspaces via header dropdown while on DC Plan page; verify scenarios reload and previous selections clear

### Implementation for User Story 2

- [x] T011 [US2] Ensure the workspace-change `useEffect` in `planalign_studio/components/DCPlanAnalytics.tsx` clears `selectedScenarioIds`, `analytics`, and `comparisonData` when `activeWorkspace?.id` changes (matching the state transition diagram in data-model.md)
- [x] T012 [US2] Handle the no-workspace edge case: when `activeWorkspace` is null/undefined, show an empty state or defer to the Layout's workspace selection prompt in `planalign_studio/components/DCPlanAnalytics.tsx`

**Checkpoint**: Workspace switching on DC Plan page behaves identically to Analysis page. State resets on workspace change. Fresh session with no workspace handled gracefully.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and cleanup

- [x] T013 Verify no TypeScript compilation errors by checking for lint/type issues in `planalign_studio/components/DCPlanAnalytics.tsx`
- [ ] T014 Run quickstart.md manual verification steps: launch studio, select workspace on Analysis, navigate to DC Plan, verify persistence, switch workspaces, verify reload

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — read-only reference tasks
- **User Story 1 (Phase 3)**: Depends on Setup (reading reference patterns)
- **User Story 2 (Phase 4)**: Depends on User Story 1 (shared context must be wired before testing workspace-change behavior)
- **Polish (Phase 5)**: Depends on User Stories 1 and 2

### Within User Story 1

Tasks T003-T010 are **sequential** — they all modify the same file (`DCPlanAnalytics.tsx`) and build on each other:
1. Add imports (T003) → Add context hook (T004) → Remove old state (T005) → Remove old fetching (T006) → Update effects (T007) → Update references (T008) → Remove UI (T009) → Clean imports (T010)

### Within User Story 2

Tasks T011-T012 are **sequential** — both modify the same file and T012 depends on the effect structure from T011.

### Parallel Opportunities

- T001 and T002 can run in parallel (reading different reference files)
- No parallel opportunities within US1 or US2 (single file modification)

---

## Parallel Example: Setup Phase

```bash
# Read both reference files simultaneously:
Task: "Read ScenarioCostComparison.tsx for useOutletContext pattern"
Task: "Read Layout.tsx for LayoutContextType interface"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (read reference files)
2. Complete Phase 3: User Story 1 (wire shared context, remove isolated state)
3. **STOP and VALIDATE**: Navigate between pages, verify workspace persists
4. This alone fixes the core bug reported by the user

### Incremental Delivery

1. Setup → Read reference patterns
2. User Story 1 → Wire shared context → Verify navigation persistence (MVP!)
3. User Story 2 → Ensure workspace-change reactivity → Verify state reset
4. Polish → Type-check, full manual verification

---

## Notes

- All implementation tasks modify a single file: `planalign_studio/components/DCPlanAnalytics.tsx`
- The pattern to follow is established in `ScenarioCostComparison.tsx` — this is a well-understood refactoring
- No new files created, no backend changes, no new dependencies
- Commit after completing User Story 1 for a clean, reviewable diff
- Out of scope: VestingAnalysis.tsx and AnalyticsDashboard.tsx have similar issues but are tracked separately
