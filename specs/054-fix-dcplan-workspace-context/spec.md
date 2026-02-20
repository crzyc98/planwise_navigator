# Feature Specification: Fix DC Plan Workspace Context Persistence

**Feature Branch**: `054-fix-dcplan-workspace-context`
**Created**: 2026-02-19
**Status**: Draft
**Input**: User description: "Fix workspace selection lost when navigating to DC Plan analytics page"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Workspace persists when navigating to DC Plan (Priority: P1)

A user selects a workspace from the header dropdown on any page (e.g., Analysis, Configuration) and then navigates to the DC Plan analytics page. The previously selected workspace remains active, and the DC Plan page immediately loads data for that workspace without requiring re-selection.

**Why this priority**: This is the core bug. Users currently lose their workspace context every time they navigate to DC Plan, forcing a redundant re-selection that breaks workflow continuity.

**Independent Test**: Can be fully tested by selecting a workspace on the Analysis page, navigating to DC Plan, and verifying the workspace remains selected and data loads automatically.

**Acceptance Scenarios**:

1. **Given** a user has selected workspace "Acme Corp" on the Analysis page, **When** they navigate to the DC Plan page via the sidebar, **Then** the DC Plan page shows "Acme Corp" as the active workspace and loads its scenarios automatically.
2. **Given** a user has selected workspace "Beta Inc" on the Configuration page, **When** they navigate to the DC Plan page, **Then** the DC Plan page uses "Beta Inc" as the active workspace without displaying a separate workspace selector.
3. **Given** a user is on the DC Plan page with workspace "Acme Corp" active, **When** they switch the workspace to "Beta Inc" via the header dropdown, **Then** the DC Plan page reloads scenarios and data for "Beta Inc" automatically.

---

### User Story 2 - Consistent workspace behavior across all pages (Priority: P2)

The DC Plan page behaves identically to other pages (Analysis, Configuration) with respect to workspace context. There is a single source of truth for the active workspace, and all pages react to workspace changes made anywhere in the application.

**Why this priority**: Ensures architectural consistency. Without this, future pages could repeat the same pattern of isolated workspace state.

**Independent Test**: Can be tested by rapidly switching between Analysis, Configuration, and DC Plan pages while changing workspaces, verifying the active workspace is always consistent.

**Acceptance Scenarios**:

1. **Given** a user switches workspaces via the header dropdown while on the DC Plan page, **When** the workspace changes, **Then** the DC Plan page reloads its scenario list and clears any previously selected scenarios.
2. **Given** no workspace has been selected yet (fresh session), **When** the user navigates directly to the DC Plan page, **Then** the page behaves the same as other pages (prompts for workspace selection or uses the default).

---

### Edge Cases

- What happens when the active workspace is deleted while the user is on the DC Plan page? The page should gracefully handle the missing workspace, matching the behavior of other pages.
- What happens when the user navigates to DC Plan before any workspace exists? The page should show the same empty/create-workspace state as other pages.
- What happens when the active workspace has no completed scenarios? The DC Plan page should show an appropriate "no data available" message rather than a broken state.
- What happens when a workspace switch occurs while DC Plan data is still loading? Any in-flight requests for the previous workspace should be superseded by the new workspace's data load.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The DC Plan page MUST read the active workspace from the shared application-level workspace context, not from its own independent state.
- **FR-002**: The DC Plan page MUST NOT maintain a separate workspace selector or workspace list that duplicates the header-level workspace selection.
- **FR-003**: When the active workspace changes (via the header dropdown from any page), the DC Plan page MUST automatically reload its scenario list for the newly selected workspace.
- **FR-004**: When the active workspace changes, the DC Plan page MUST clear any previously selected scenario data and reset its local UI state (selected scenarios, comparison data, etc.).
- **FR-005**: The DC Plan page MUST load scenario data for the active workspace immediately on mount, without requiring user interaction to select a workspace.

### Key Entities

- **Workspace**: The top-level organizational unit containing scenarios. Identified by a unique ID. Shared across the entire application via a single context provider.
- **Scenario**: A simulation configuration within a workspace. The DC Plan page displays analytics for one or more completed scenarios within the active workspace.
- **Active Workspace State**: The currently selected workspace, managed at the application layout level and shared to all child pages.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can navigate from any page to the DC Plan page and see the correct workspace active, with zero additional clicks required to select a workspace.
- **SC-002**: Workspace selection is consistent across all pages at all times -- changing the workspace on one page is immediately reflected on all other pages, including DC Plan.
- **SC-003**: The DC Plan page loads scenario data within the same timeframe as other pages (Analysis, Configuration) when navigating with an active workspace.
- **SC-004**: No duplicate workspace dropdowns or selectors appear on the DC Plan page that are redundant with the header-level workspace selector.

## Assumptions

- The existing application layout's outlet context pattern is the correct and established pattern for sharing workspace state. This is confirmed by its successful use in the Analysis page and other pages.
- The DC Plan page's scenario-fetching logic (calls for scenarios and analytics data) does not need to change -- only the source of the workspace ID needs to change from local state to shared context.
- The header workspace dropdown already handles workspace CRUD operations and will continue to do so. The DC Plan page only needs to consume the active workspace, not manage it.
- Removing the redundant workspace selector from DC Plan will not break any other functionality, as the header dropdown provides the same capability globally.
