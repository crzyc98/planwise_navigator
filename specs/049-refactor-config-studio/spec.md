# Feature Specification: Refactor ConfigStudio into Modular Section Components

**Feature Branch**: `049-refactor-config-studio`
**Created**: 2026-02-12
**Status**: Draft
**Input**: User description: "Refactor ConfigStudio.tsx from 4,342-line monolith into modular section components with shared state management"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Navigates to a Specific Section's Code (Priority: P1)

A developer working on the DC Plan configuration needs to find and modify the DC Plan section UI. Currently, they must scroll through a 4,342-line file to locate the relevant code. After refactoring, they open the DC Plan section file directly and find all DC Plan UI logic in a focused, self-contained file.

**Why this priority**: This is the core value proposition of the refactoring — developer productivity and maintainability. Every other benefit flows from having properly isolated section components.

**Independent Test**: Can be verified by confirming each section file exists, renders its expected UI, and contains only code relevant to that section.

**Acceptance Scenarios**:

1. **Given** the refactored codebase, **When** a developer opens the DC Plan section file, **Then** they find all DC Plan configuration UI in that single file (approximately 640 lines of JSX and handlers)
2. **Given** the refactored codebase, **When** a developer needs to modify the compensation section, **Then** they open the Compensation section file and make changes without touching any other section file
3. **Given** the refactored codebase, **When** a developer opens ConfigStudio.tsx, **Then** it contains fewer than 300 lines — only sidebar navigation, section routing, save/load actions, and state provider setup

---

### User Story 2 - User Interacts with Configuration UI Without Regressions (Priority: P1)

An end user opens PlanAlign Studio, navigates to any configuration section (Simulation, Data Sources, Compensation, New Hire, Segmentation, Turnover, DC Plan, Advanced), edits fields, and sees the exact same behavior as before: dirty indicators appear for modified sections, save persists all changes, and all validation and feedback works identically.

**Why this priority**: Zero functional regression is a hard requirement — the refactoring must be invisible to end users.

**Independent Test**: Can be tested by performing the same user flows before and after refactoring and verifying identical behavior.

**Acceptance Scenarios**:

1. **Given** any configuration section, **When** a user modifies a field, **Then** the sidebar shows a dirty indicator (amber dot) on that section's nav item
2. **Given** unsaved changes across multiple sections, **When** the user clicks Save, **Then** all changes are persisted and dirty indicators clear for all sections
3. **Given** a saved configuration, **When** the user reloads the page, **Then** all previously saved values are correctly restored in every section
4. **Given** the DC Plan section with match tier editing, **When** the user adds/removes tiers and changes match templates, **Then** the match cap auto-calculates and tiers save correctly (same as current behavior)

---

### User Story 3 - Developer Adds a New Configuration Section (Priority: P2)

A developer needs to add a new "Compliance" configuration section. With the refactored architecture, they create a new section file following the established pattern, register it in the section list and dirty-tracking configuration, and the new section integrates seamlessly without modifying any existing section components.

**Why this priority**: Future extensibility is a key benefit of modularization, but it's a secondary outcome after the immediate maintainability improvement.

**Independent Test**: Can be tested by verifying that adding a new section file with the correct interface works without modifying existing section components.

**Acceptance Scenarios**:

1. **Given** the refactored architecture, **When** a developer creates a new section component following the established pattern, **Then** they only need to: (a) create the section file, (b) add it to the section registry in ConfigStudio, and (c) define its dirty-tracking fields
2. **Given** the shared state mechanism, **When** a new section needs access to form data and handlers, **Then** it receives them through the same mechanism as all other sections without deep prop drilling

---

### Edge Cases

- What happens when the user navigates rapidly between sections while data is loading from the API? The loading states and async operations must remain stable across section switches.
- What happens when the dirty-tracking logic compares state across sections that have not yet been rendered? The dirty computation must work on the full form state regardless of which section is currently visible.
- What happens when the copy-from-scenario modal loads config that spans multiple sections? The form data update must propagate correctly to all section components.
- What happens when a save fails partway through? Error feedback must still appear correctly in the header area, not within a specific section.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extract each of the 8 configuration sections (Data Sources, Simulation, Compensation, New Hire, Segmentation, Turnover, DC Plan, Advanced) into separate component files
- **FR-002**: System MUST extract InputField and CompensationInput into reusable component files
- **FR-003**: System MUST extract shared configuration state (formData, savedFormData, handlers, dirty-tracking) into a shared state mechanism to avoid deep prop drilling
- **FR-004**: System MUST reduce ConfigStudio.tsx to fewer than 300 lines, containing only: sidebar navigation, section routing (conditional rendering), save/load actions, and state provider setup
- **FR-005**: System MUST preserve all existing dirty-tracking behavior — each section's amber dot indicator MUST appear when any field in that section differs from the last saved state
- **FR-006**: System MUST preserve the exact same visual layout, styling, and interaction behavior for all 8 configuration sections
- **FR-007**: System MUST preserve the save handler that serializes all form data into the API config payload format, including all unit conversions (percentage to decimal, etc.)
- **FR-008**: System MUST preserve all modal behaviors: template selection, copy-from-scenario, census file upload, and compensation solver
- **FR-009**: System MUST preserve all section-specific state and effects: band configuration loading/analysis, promotion hazard config loading, census file validation, and scenario-level config loading
- **FR-010**: System MUST maintain existing type safety — all extracted components must use proper typed interfaces for their props and state
- **FR-011**: System MUST preserve the MatchTier, MatchTemplate interfaces and MATCH_TEMPLATES constant, co-located with the DC Plan section or in a shared types/constants file
- **FR-012**: System MUST preserve all existing API integrations and their error handling across sections

### Key Entities

- **ConfigStudio**: The parent shell component — sidebar nav, section routing, save/load orchestration
- **Section Components**: 8 standalone components (DataSourcesSection, SimulationSection, CompensationSection, NewHireSection, SegmentationSection, TurnoverSection, DCPlanSection, AdvancedSection) each rendering one configuration tab
- **Shared State**: The shared state mechanism providing formData, savedFormData, update handlers, dirty-tracking, and save function to all sections
- **Reusable UI Components**: InputField and CompensationInput used across multiple sections

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: ConfigStudio.tsx is reduced from 4,342 lines to fewer than 300 lines
- **SC-002**: Each of the 8 section components is a standalone file containing only the UI and logic for its specific section
- **SC-003**: All existing user-facing functionality works identically — a user cannot distinguish the refactored UI from the original
- **SC-004**: Dirty-tracking indicators correctly appear and clear for all 8 sections after the refactoring
- **SC-005**: Save and load operations correctly persist and restore all configuration fields across all sections
- **SC-006**: No new compilation errors are introduced by the refactoring
- **SC-007**: The shared state mechanism allows any section to read and update form data without receiving more than 2 levels of props

## Assumptions

- The refactoring is purely structural — no new features, UI changes, or behavior modifications are included
- The existing API service layer remains unchanged; only the component layer is refactored
- Section-specific modals (template picker, copy-from-scenario, census upload) will be co-located with their parent section component or extracted into their own files as needed for clarity
- The formData state shape remains unchanged — field names, types, and default values are preserved exactly
- The dirty-tracking logic can be centralized in the shared state mechanism rather than duplicated across sections
- No frontend test framework exists in this project; verification relies on TypeScript compilation (`tsc --noEmit`) and manual visual testing, consistent with all prior frontend work in PlanAlign Studio
