# Research: Refactor ConfigStudio

**Feature**: 049-refactor-config-studio
**Date**: 2026-02-12

## Research Summary

All unknowns from the Technical Context have been resolved through codebase analysis. No external research was needed — this is an internal refactoring of a well-understood component.

---

## Decision 1: State Sharing Mechanism

**Decision**: React Context with a `ConfigProvider` component

**Rationale**:
- 8 section components + 2 modals consume the same shared state (formData, dirty-tracking, save handler)
- React Context is the idiomatic React solution for avoiding prop drilling across many siblings
- Only one section renders at a time (`activeSection === 'xxx'` conditional rendering), so context value changes don't cause unnecessary DOM work
- The project already uses a context-like pattern via `useOutletContext<LayoutContextType>()` from react-router-dom

**Alternatives considered**:
1. **Props-only**: Would require passing 15+ props to each of 8 section components. Maintenance burden too high.
2. **Custom hook alone (no context)**: `useConfigState()` called in each component would create independent state instances — not shared state. Would only work if combined with prop-lifting, negating the benefit.
3. **State management library (Zustand/Redux)**: Overkill for a single-page config form. Adds a dependency and pattern that doesn't exist elsewhere in the codebase.

---

## Decision 2: Context State Boundary

**Decision**: Context holds state needed by multiple sections or by dirty-tracking/save. Sections hold their own UI-local state.

**Rationale**: The dirty-tracking `useMemo` (lines 910-991) and save handler (lines 1327-1562) need access to:
- `formData` + `savedFormData` (all sections)
- `promotionHazardConfig` + `savedPromotionHazardConfig` (compensation dirty indicator)
- `bandConfig` + `savedBandConfig` (segmentation dirty indicator)

But section-specific UI state (loading spinners, error messages, solver results, analysis state) is only read/written within a single section and doesn't affect dirty-tracking or save.

**Alternatives considered**:
1. **All state in context**: Simpler to implement but makes the context unnecessarily large and couples all sections to all state.
2. **All state local + save prop**: Would require each section to expose its saveable state upward, inverting the data flow.

---

## Decision 3: Payload Builder Extraction

**Decision**: Extract the `handleSaveConfig` payload construction into a pure function `buildConfigPayload(formData, promotionHazardConfig, bandConfig)`.

**Rationale**:
- The payload construction (~100 lines) is a pure data transformation with no side effects
- It converts frontend types (percentages as numbers) to API types (decimals, different field names)
- As a pure function, it's independently testable if a test framework is added later
- The save handler retains the validation logic, API calls, and state updates

**Alternatives considered**:
1. **Keep everything inline in save handler**: Makes the handler 235 lines, harder to reason about.
2. **Move validation into payload builder**: Would mix concerns (data transformation vs business rules).

---

## Decision 4: Modal Placement

**Decision**: Modals (TemplateModal, CopyScenarioModal) are extracted to their own files and rendered by the ConfigStudio shell.

**Rationale**:
- Both modals are triggered from the header area (not within any section)
- Both modify cross-section state (formData, promotionHazardConfig, bandConfig)
- Keeping them at the shell level maintains the current trigger/render relationship
- Extracting to files prevents the shell from growing beyond 300 lines

**Alternatives considered**:
1. **Keep inline in ConfigStudio**: Would push ConfigStudio over the 300-line limit.
2. **Place in specific sections**: Wrong location — they're triggered from the header, not from sections.

---

## Decision 5: Promotion Hazard Extraction

**Decision**: Extract the Promotion Hazard editor (~153 lines) from NewHireSection into a standalone `PromotionHazardEditor.tsx`.

**Rationale**:
- The promotion hazard editor is a distinct feature (E038) with its own loading/error/validation state
- It modifies `promotionHazardConfig` (context state) independently from new hire form fields
- Extracting it keeps NewHireSection at ~550 lines instead of ~700
- Improves discoverability — developers looking for promotion hazard config find it by filename

**Alternatives considered**:
1. **Keep inline in NewHireSection**: Would make NewHireSection the largest file at ~700 lines.
2. **Move to CompensationSection**: Promotion hazard dirty-tracking already marks the compensation tab dirty, but the UI has always been rendered under the NewHire section. Moving it would be a functional change.

---

## Decision 6: File Organization

**Decision**: All new files go under `components/config/` — a new subdirectory.

**Rationale**:
- Currently all components are flat in `components/` (14 files)
- Adding 15+ new files directly to `components/` would make it unwieldy
- A `config/` subdirectory groups related components by feature
- This establishes a pattern for future component grouping

**Alternatives considered**:
1. **Flat in `components/`**: Would create a 29+ file flat directory, making navigation harder.
2. **Separate `hooks/` for context**: The project has `hooks/useCopyToClipboard.ts`, but `ConfigContext` is tightly coupled to ConfigStudio and belongs with it.
