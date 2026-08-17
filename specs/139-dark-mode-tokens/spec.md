# Feature Specification: Dark Mode Token Layer

**Feature Branch**: `139-dark-mode-tokens`
**Created**: 2026-08-17
**Status**: Draft
**Input**: User description: "Split out of #497 / #503, where the acceptance criteria asked for a visual check \"light and dark\" and it turned out there is no dark mode to check. Introduce a semantic color token layer, a useChartTheme hook for Recharts, a validated dark chart palette ramp, and a theme toggle for PlanAlign Studio."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Semantic surface tokens power every screen (Priority: P1)

As a Studio maintainer, I want every layout surface (page background, panels, borders, primary/secondary text) driven by a small set of named color tokens instead of literal Tailwind gray/white classes, so that a single token change can restyle the whole app and no view is one-off styled.

**Why this priority**: This is the prerequisite for everything else — the toggle and the chart hook both read from these tokens. It is also valuable independent of dark mode: today there is no single place to change a surface color across the ~1,850 literal usages spread over 53 components.

**Independent Test**: With no toggle and no dark theme shipped yet, change one semantic token value in the theme definition and confirm every migrated component's rendered color updates app-wide, with zero remaining literal `bg-white`, `text-gray-*`, or `border-gray/slate-*` usages in migrated components.

**Acceptance Scenarios**:

1. **Given** the Studio theme defines semantic tokens for surface, raised surface, primary text, muted text, and border, **When** a component is migrated, **Then** it references only the semantic tokens and contains no literal gray/white/hex color class or style.
2. **Given** all 53 identified components are migrated, **When** a token's underlying value is changed, **Then** every migrated surface reflects the new value without any component-level code changes.

---

### User Story 2 - Charts read color from a theme-aware source (Priority: P2)

As a Studio user viewing any chart (bar, line, area, pie, etc.), I want chart grid lines, axes, tooltips, and data series colors to come from a single theme-aware source rather than hardcoded hex values passed as component props, so charts are never mismatched with the surrounding UI theme.

**Why this priority**: Charts are the largest and most expensive migration surface (grid/axis/tooltip literals cannot be reached by a CSS class — only a JS-side theme source works) and they are what #497/#503's original "check light and dark" acceptance criteria actually meant to verify. This depends on User Story 1's tokens existing, but is independently verifiable once available.

**Independent Test**: Render each chart type used in Studio through the shared chart-theme source and confirm none of them pass a literal hex value for grid lines, axis strokes, or tooltip backgrounds — all such values originate from the shared source.

**Acceptance Scenarios**:

1. **Given** a chart component previously hardcoded `stroke="#E5E7EB"` on its grid, **When** migrated, **Then** the grid color is supplied by the shared chart-theme source instead.
2. **Given** a tooltip previously hardcoded `backgroundColor: '#fff'`, **When** migrated, **Then** the tooltip panel color is supplied by the shared chart-theme source instead.
3. **Given** the shared chart-theme source is asked for the current theme's values, **When** the active theme changes, **Then** it returns a different, theme-appropriate set of values without requiring each chart component to know how the theme changed.

---

### User Story 3 - Users can switch between light and dark themes (Priority: P3)

As a Studio user, I want to toggle between a light and a dark theme and have the entire interface — layout chrome and every chart — render legibly and consistently in the theme I chose, so I can work comfortably in low-light conditions or match my system preference.

**Why this priority**: This is the user-facing payoff, but it is only safe to ship once User Stories 1 and 2 exist — otherwise toggling reveals the ~190 remaining hardcoded surfaces as visual regressions. Ships last by design.

**Independent Test**: With the token layer and chart-theme source in place, add a dark palette and a toggle control; switch themes on every major Studio screen and confirm no screen shows an unstyled ("light-mode-only") element.

**Acceptance Scenarios**:

1. **Given** a user has not made an explicit theme choice, **When** they open Studio for the first time, **Then** it renders using the theme that matches their operating system's color-scheme preference.
2. **Given** a user clicks the theme toggle, **When** the theme changes, **Then** every visible surface and chart on the current screen updates to the new theme without a full page reload or loss of in-progress work.
3. **Given** a user has explicitly chosen a theme, **When** they close and reopen Studio, **Then** their chosen theme is remembered and applied, overriding the OS preference.
4. **Given** the dark chart palette is active, **When** any categorical chart renders, **Then** every series color passes the same lightness/contrast validation used for the light palette (#497), rather than being an automatic inversion of the light colors.

---

### Edge Cases

- What happens if a component is missed during migration and still contains a literal white/gray/hex color? It should be visually obvious (a light-colored box on a dark screen) and treated as a bug, not silently ignored.
- How does the system handle a user whose OS theme preference changes while Studio is open (e.g., system auto-switches at sunset) but who has not made an explicit in-app choice? Studio should follow the OS change live.
- How does the system handle a user who explicitly chose a theme and then changes their OS preference? The explicit in-app choice takes precedence until the user clears or changes it.
- What happens to a chart with more data series than the validated dark palette has distinct colors? Same fallback behavior as the existing light palette (#497) — no new failure mode should be introduced.
- How is the theme toggle itself styled before/while migrating other components (bootstrapping problem)? The toggle control must be one of the first elements migrated to semantic tokens so it is visible in both themes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Studio MUST define a semantic color token layer (at minimum: base surface, raised/panel surface, primary text/"ink", muted/secondary text, and border) in the shared theme configuration.
- **FR-002**: Every Studio component MUST reference layout colors through the semantic tokens rather than literal Tailwind gray/white utility classes or inline hex values, once migrated.
- **FR-003**: Studio MUST provide a single shared, theme-aware source of chart styling values (grid line color, axis color, tooltip background/text color, and data-series colors) that all chart components consume instead of hardcoding hex values as component props.
- **FR-004**: Studio MUST define a dark-mode categorical chart palette derived from the same hues as the existing light palette (#497), with each color independently selected and validated for legibility against the dark surface color — not produced by automatically inverting the light palette.
- **FR-005**: The dark chart palette MUST pass the same lightness/contrast validation check used to accept the light palette in #497 before it can be used.
- **FR-006**: Studio MUST provide a visible, user-accessible control to switch between light and dark themes.
- **FR-007**: On first visit with no stored preference, Studio MUST render using the theme matching the operating system's color-scheme setting.
- **FR-008**: Once a user makes an explicit theme choice, Studio MUST remember that choice and apply it on subsequent visits, taking precedence over the OS-level preference.
- **FR-009**: Switching themes MUST update all visible layout surfaces and charts on the current screen without a full page reload or loss of unsaved in-progress state.
- **FR-010**: When the dark theme is active, no screen in Studio may display a literal, unmigrated light-only surface (e.g., a plain white panel or unreadable gray-on-dark text).

### Key Entities

- **Semantic Color Token**: A named design value (e.g., surface, raised surface, ink, muted text, border) that resolves to a concrete color per active theme; consumed by components in place of literal color classes.
- **Chart Theme**: The current theme's resolved set of chart-specific values (grid, axis, tooltip, categorical series colors) exposed to chart components through a single shared source.
- **Theme Preference**: The user's active theme setting — either "follow system" (default) or an explicit "light"/"dark" choice — persisted across sessions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero literal `bg-white`, `text-gray-*`, `border-gray/slate-*`, or inline hex color usages remain in the 53 components identified as needing migration, verified by a repository-wide search.
- **SC-002**: 100% of chart components in Studio source grid, axis, tooltip, and series colors from the shared chart-theme mechanism rather than hardcoded hex literals.
- **SC-003**: The dark categorical chart palette passes the existing palette validator (from #497) with zero lightness/contrast band failures, matching the pass rate already achieved by the light palette.
- **SC-004**: A user can switch themes and see 100% of surfaces and charts on the current screen update correctly, with no visual regression reported across the views previously flagged in #497/#503.
- **SC-005**: On first visit, Studio matches the visiting browser's OS-level color-scheme preference with no manual action required; an explicit in-app choice persists across 100% of subsequent sessions until changed.

## Assumptions

- The theme toggle is a client-side, per-browser preference (e.g., stored in local storage); no server-side or cross-device account sync is required.
- Chart/report export surfaces (image or document export) are out of scope for this feature — only the interactive Studio UI (layout chrome and on-screen charts) is covered. Any future export feature should reuse these tokens but is tracked separately.
- "Every Studio screen" refers to the current set of views reachable from the Studio navigation as of this feature's implementation; views added after this feature ships are expected to use the token layer from the start but are not retroactively covered by this feature's acceptance criteria.
- The existing #497 palette validator (lightness/contrast band checks) is reused as-is for validating the dark ramp; no new validation methodology is introduced.
