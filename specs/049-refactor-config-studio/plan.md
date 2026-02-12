# Implementation Plan: Refactor ConfigStudio into Modular Section Components

**Branch**: `049-refactor-config-studio` | **Date**: 2026-02-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/049-refactor-config-studio/spec.md`

## Summary

Decompose the 4,342-line `ConfigStudio.tsx` monolith into ~17 focused files: a React Context provider for shared state (formData, dirty-tracking, save/load), 8 section components, 1 sub-section component (PromotionHazardEditor), 2 modal components, 2 reusable UI components, a types file, a constants file, and a payload builder utility. ConfigStudio.tsx becomes a thin shell (under 300 lines) with sidebar navigation, section routing, and modal orchestration.

## Technical Context

**Language/Version**: TypeScript 5.x (React 18 frontend)
**Primary Dependencies**: React 18, react-router-dom, Lucide-react (icons), Tailwind CSS
**Storage**: N/A (frontend reads/writes via API service layer)
**Testing**: Manual visual regression testing (no frontend test framework currently in project)
**Target Platform**: Web browser (Vite dev server at localhost:5173)
**Project Type**: Web application (frontend component refactoring only)
**Performance Goals**: No render degradation — conditional rendering ensures only active section mounts
**Constraints**: ConfigStudio.tsx must be < 300 lines; zero visual/functional regression
**Scale/Scope**: 1 monolith file → ~15 focused files; ~4,342 lines reorganized

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only refactoring, no event store changes |
| II. Modular Architecture | **PASS** | This refactoring directly implements this principle — splitting a 4,342-line monolith into focused modules |
| III. Test-First Development | **ADVISORY** | No frontend test framework exists in project. Verification is through TypeScript compilation (`tsc --noEmit`) + manual visual testing. Documented in spec Assumptions. Constitution test targets specify "Python code" for coverage metrics. |
| IV. Enterprise Transparency | N/A | No logging or audit trail changes |
| V. Type-Safe Configuration | **PASS** | All extracted components use TypeScript interfaces; formData shape preserved |
| VI. Performance & Scalability | **PASS** | Conditional rendering (`activeSection === 'xxx'`) ensures only one section mounts at a time, preventing unnecessary re-renders |

**Gate result**: PASS (no violations)

## Project Structure

### Documentation (this feature)

```text
specs/049-refactor-config-studio/
├── plan.md              # This file
├── research.md          # Phase 0: Architecture decisions
├── data-model.md        # Phase 1: Component interfaces and state contracts
├── quickstart.md        # Phase 1: Developer guide
├── contracts/           # Phase 1: TypeScript interface definitions
│   └── ConfigContext.ts # Context type contract
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_studio/components/
├── ConfigStudio.tsx                  # Thin shell (~200 lines): sidebar, routing, modals
└── config/                           # NEW directory
    ├── ConfigContext.tsx              # React Context + Provider (~450 lines)
    │                                 #   formData, savedFormData, dirty-tracking,
    │                                 #   handleChange, handleSaveConfig, useEffects
    ├── buildConfigPayload.ts         # Pure function: formData → API payload (~120 lines)
    ├── types.ts                      # MatchTier, MatchTemplate, FormData type, etc. (~80 lines)
    ├── constants.ts                  # MATCH_TEMPLATES, calculateMatchCap (~50 lines)
    ├── InputField.tsx                # Reusable input component (~50 lines)
    ├── CompensationInput.tsx         # Reusable salary input with onBlur commit (~40 lines)
    ├── DataSourcesSection.tsx        # Census upload/validation (~230 lines)
    ├── SimulationSection.tsx         # Year range, seed, growth (~60 lines)
    ├── CompensationSection.tsx       # Merit, COLA, promo + solver (~230 lines)
    ├── NewHireSection.tsx            # Demographics, levels, comp ranges (~550 lines)
    ├── PromotionHazardEditor.tsx     # Promotion hazard config sub-section (~170 lines)
    ├── SegmentationSection.tsx       # Age/tenure band editor (~330 lines)
    ├── TurnoverSection.tsx           # Termination rates (~70 lines)
    ├── DCPlanSection.tsx             # DC plan config (~650 lines)
    ├── AdvancedSection.tsx           # System resources, logging, danger zone (~170 lines)
    ├── TemplateModal.tsx             # Template selection modal (~100 lines)
    └── CopyScenarioModal.tsx         # Copy-from-scenario modal (~250 lines)
```

**Structure Decision**: Create a new `components/config/` subdirectory. This is the first component subdirectory in the project, establishing a pattern for future component grouping. The flat `components/` structure is preserved for top-level page components.

## Complexity Tracking

| Component | Lines | Limit | Justification |
|-----------|-------|-------|---------------|
| DCPlanSection.tsx | ~650 | ~600 | DC Plan has 30+ fields across 6 sub-sections (eligibility, auto-enroll, match tiers, match eligibility, core contribution, escalation) plus inline tier add/remove/edit handlers and gap/overlap validation. Splitting further would fragment a single cohesive form section. All logic is section-local — no cross-section coupling. |

## Architecture Decisions

### 1. State Sharing: React Context + Provider

**Decision**: Use React Context (`ConfigContext`) with a Provider component wrapping the section components.

**Rationale**:
- 8 section components + 2 modals all need access to `formData`, `setFormData`, `handleChange`, `dirtySections`
- Prop drilling 10+ values through ConfigStudio to each section creates maintenance burden
- Context is React's built-in solution for this pattern
- Only one section renders at a time (conditional rendering), so context re-renders are not a performance concern

**Rejected Alternative**: Custom hook without context — each component calling `useConfigState()` would create independent state instances, not shared state.

### 2. Save Handler: Context + Payload Builder

**Decision**: `handleSaveConfig` lives in the Context provider. The payload construction is extracted to a pure `buildConfigPayload()` function.

**Rationale**:
- Save needs access to all context state (formData, promotionHazardConfig, bandConfig, activeWorkspace, currentScenario)
- Payload builder is a pure function (formData → API shape) that's easy to test and maintain independently
- Validation (promotion hazard, bands) stays in the save handler since it gates the save operation

### 3. Section-Specific State: Local to Section Components

**Decision**: State that is only used within a single section stays local to that section component.

**Local state examples**:
- `uploadStatus`, `uploadMessage` → DataSourcesSection
- `solverStatus`, `solverResult`, `solverError`, `targetCompGrowth` → CompensationSection
- `matchCensusLoading`, `compensationAnalysis`, etc. → NewHireSection
- `ageBandAnalysis`, `bandValidationErrors`, etc. → SegmentationSection
- `dbDeleteStatus`, `dbDeleteMessage` → AdvancedSection

**Context state** (needed for dirty-tracking or save):
- `formData`, `savedFormData`, `setFormData`
- `promotionHazardConfig`, `savedPromotionHazardConfig`, `setPromotionHazardConfig`
- `bandConfig`, `savedBandConfig`, `setBandConfig`
- `dirtySections`, `isDirty`
- `handleChange`, `handleSaveConfig`
- `saveStatus`, `saveMessage`
- `activeWorkspace`, `currentScenario`, `scenarioId`

### 4. Promotion Hazard Editor: Separate Component

**Decision**: Extract the Promotion Hazard configuration (currently embedded in the NewHire section, ~153 lines) into its own `PromotionHazardEditor.tsx` component.

**Rationale**: It's a distinct feature (E038) with its own state (loading, errors, validation) and its own handlers. Extracting it keeps NewHireSection under 600 lines and improves discoverability.

### 5. Modals: Extracted but Rendered by ConfigStudio Shell

**Decision**: Template and Copy-from-Scenario modals are extracted to their own files but rendered by ConfigStudio (the shell), not by individual sections.

**Rationale**: Both modals modify cross-section state (formData, promotionHazardConfig, bandConfig) and are triggered from the header area, not from within any specific section.

## Implementation Order

1. **Create types.ts + constants.ts** — Define all shared types and constants first (no dependencies)
2. **Create InputField.tsx + CompensationInput.tsx** — Extract reusable UI components (no dependencies)
3. **Create buildConfigPayload.ts** — Extract pure payload builder (depends on types)
4. **Create ConfigContext.tsx** — Extract all shared state, effects, dirty-tracking, save handler (depends on types, constants, buildConfigPayload)
5. **Create section components** (all depend on ConfigContext) — in order of complexity:
   a. TurnoverSection (simplest, 53 lines)
   b. SimulationSection (44 lines)
   c. AdvancedSection (148 lines)
   d. CompensationSection (196 lines)
   e. DataSourcesSection (213 lines)
   f. SegmentationSection (297 lines)
   g. PromotionHazardEditor (153 lines, extracted from NewHire)
   h. NewHireSection (642 lines, uses PromotionHazardEditor)
   i. DCPlanSection (639 lines)
6. **Create TemplateModal.tsx + CopyScenarioModal.tsx** — Extract modals (depend on ConfigContext)
7. **Rewrite ConfigStudio.tsx** — Thin shell importing all above (final step)
8. **Verify** — TypeScript compilation, visual regression check
