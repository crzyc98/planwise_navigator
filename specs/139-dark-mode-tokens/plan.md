# Implementation Plan: Dark Mode Token Layer

**Branch**: `139-dark-mode-tokens` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/139-dark-mode-tokens/spec.md`

## Summary

Replace PlanAlign Studio's literal light-only neutral colors with a compact
semantic CSS token layer, then make all 30 Recharts declarations consume one
typed `useChartTheme()` source. A root theme provider will distinguish the
stored `system | light | dark` preference from the resolved theme, apply it
without remounting routes, follow live operating-system changes in system mode,
and wire the existing Settings control. Before accepting a dark six-color
categorical ramp, reconstruct the manual #497/#503 palette audit as an
executable dependency-free validator and prove parity against its published
light fixtures. The feature remains client-side: no API, database,
configuration, result, or export contract changes.

## Technical Context

**Language/Version**: TypeScript 5.8; CSS/Tailwind CSS 4.2; HTML; Python 3.11 for dependency-free contract/palette tests
**Primary Dependencies**: Existing React 19.2, React Router 7.9, Recharts 3.5, Tailwind CSS 4.2 through `@tailwindcss/vite`, Lucide React, Vite 6, pytest 7.4; no new runtime or test dependency
**Storage**: Browser `localStorage` for one non-sensitive explicit theme value (`light` or `dark`); missing/invalid means `system`; no DuckDB, workspace, API, or server persistence change
**Testing**: pytest fast source-contract and palette-validation tests, `npx tsc --noEmit`, Vite production build, and manual in-browser two-theme/OS-preference route-and-chart matrix
**Target Platform**: PlanAlign Studio in modern desktop browsers on supported macOS and Linux workstations
**Project Type**: Client-side React single-page application within the existing Python/Studio monorepo
**Performance Goals**: Theme changes complete in the current frame without reload or route remount; no repeated computed-style/layout reads per chart; no visible persisted-theme flash before React mount
**Constraints**: Preserve unsaved UI state; follow OS changes only in system mode; guard unavailable storage/media APIs; bundled local code only; keep categorical slot identity and modulo overflow behavior; zero dark-palette lightness/contrast hard failures; no chart/export or backend scope expansion
**Scale/Scope**: 53 components containing specified legacy neutral utilities, 54 component TSX files to audit, 12 direct Recharts consumers, 30 chart declarations, six categorical slots, and all routes currently registered in `App.tsx`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Plan evidence |
|---|---|---|
| I. Event Sourcing & Immutability | PASS | The feature reads no simulation state and creates or mutates no events, database rows, run archives, or exports. Theme preference is non-domain browser UI state only. |
| II. Modular Architecture | PASS | CSS owns semantic layout values; a root provider owns preference resolution; a typed chart-theme module owns Recharts values; consumers remain presentation components. No package, dbt, API, or dependency-direction cycle is introduced. |
| III. Test-First Development | PASS | Implementation begins with failing palette parity and source-contract tests, followed by tokens/provider/chart hook and staged migrations. TypeScript and production-build gates plus a documented visual matrix cover browser-only behavior. |
| IV. Enterprise Transparency | PASS | The reconstructed palette validator records thresholds, fixtures, warnings, and provenance from #497/#503; no audit or simulation logging semantics change. Theme selection is explicit and inspectable at the document root. |
| V. Type-Safe Configuration | PASS | Theme preference, resolved theme, token maps, chart roles, and the six-slot ramp have closed TypeScript types. No application/Pydantic configuration or raw SQL is added. |
| VI. Performance & Scalability | PASS | Theme changes update one root attribute/context value and chart map. The design avoids per-chart `getComputedStyle`, network calls, reloads, remounts, and database work. |

**Pre-design gate result**: PASS. No constitutional exception is required.

**Post-Phase-1 re-check**: PASS. The data model contains browser-only value
objects and deterministic state transitions; the contracts keep one theme
authority and one chart source; the quickstart performs no shared-database
writes. No complexity exception is required.

## Project Structure

### Documentation (this feature)

```text
specs/139-dark-mode-tokens/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── theme-contract.ts
│   └── validation-contract.md
└── tasks.md                     # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
planalign_studio/
├── index.html                   # MODIFY: pre-paint theme bootstrap/color-scheme metadata
├── index.css                    # MODIFY: light/dark raw values and semantic Tailwind tokens
├── index.tsx                    # MODIFY: mount root ThemeProvider
├── App.tsx                      # MODIFY: migrate error/placeholder surfaces
├── constants.ts                # MODIFY: remove chart color authorities superseded by theme
├── tsconfig.json                # MODIFY only if JSON palette import requires resolveJsonModule
├── theme/
│   ├── ThemeProvider.tsx        # NEW: preference resolution, persistence, media subscription
│   ├── theme.ts                 # NEW: closed types, storage/media helpers, context contract
│   ├── chartTheme.ts            # NEW: immutable role maps and modulo color selection
│   └── chart-palettes.json      # NEW: single machine-readable validated light/dark ramps
├── hooks/
│   ├── useTheme.ts              # NEW: root preference/resolved-theme access
│   └── useChartTheme.ts         # NEW: resolved typed Recharts values
└── components/
    ├── Layout.tsx               # MODIFY: accessible System/Light/Dark control and shell tokens
    ├── *.tsx                    # MODIFY: semantic surface/status tokens and chart roles
    ├── config/*.tsx             # MODIFY: semantic inputs, panels, disabled/status states
    ├── imports/*.tsx            # MODIFY: semantic upload/mapping/preview surfaces
    ├── simulation/*.tsx         # MODIFY: semantic live-run/log/chart surfaces
    └── timeline/*.tsx           # MODIFY: semantic search/timeline surfaces

scripts/
└── validate_studio_palette.py   # NEW: reconstructed #497/#503 color audit

tests/unit/
├── test_studio_palette.py       # NEW: published fixture parity and dark-ramp acceptance
└── test_studio_theme_contract.py # NEW: dynamic migration/theme/chart source contract
```

**Structure Decision**: Keep selector-switched layout values in the existing
global CSS because Tailwind utilities already form the component styling API.
Place browser preference state and chart maps in a small dedicated frontend
theme directory so `Layout` and chart pages are consumers, not authorities.
Use one palette JSON file for both TypeScript and the Python validator. The
validator lives under `scripts/` so it is runnable independently, while fast
pytest tests lock the published fixtures and runtime palette source. The broad
component edits are migrations only; no new component hierarchy or backend
adapter is introduced.

## Design Decisions

### Semantic token contract

Raw per-theme CSS custom properties are private implementation values. Public
component styling uses semantic Tailwind roles:

| Family | Required roles | Typical consumers |
|---|---|---|
| Surface | `surface`, `surface-raised`, `surface-subtle`, `surface-input`, `surface-disabled`, `overlay` | body, shell, panels, rows, inputs, modals |
| Text | `ink`, `ink-muted`, `ink-subtle`, `ink-inverse`, `ink-disabled` | headings, body copy, metadata, icons, button text |
| Border/focus | `border`, `border-strong`, `focus` | panels, inputs, separators, focus rings |
| Status | paired success/warning/danger/info surface, ink, border roles | alerts, badges, progress states, validation feedback |
| Chart | grid, axis, tooltip, cursor, reference, legend, six categorical slots, fixed semantic series | all Recharts primitives and custom tooltip/legend content |

Components choose the role that describes the element. They do not choose a
gray step or theme-specific value. Brand utilities remain for intentional
Fidelity identity and primary actions, but their contrast is checked in both
themes.

### Theme preference state machine

The provider initializes from a valid stored explicit preference; otherwise it
uses `system`. System resolution reads the current media query and subscribes to
changes. Explicit Light/Dark writes the storage key and changes the document
immediately. System removes the key and resumes media tracking. Invalid values
and storage exceptions degrade safely to system. The provider updates the
existing document root and never keys, replaces, or reloads the router tree.

The pre-paint bootstrap uses the same key and accepted values before application
mount. A source contract prevents the bootstrap and provider from silently
diverging. The Settings button gains an accessible name and the menu exposes a
three-option radio group so users can both override and resume system behavior.

### Chart theme and stable series identity

`useChartTheme()` returns the contract in
[theme-contract.ts](./contracts/theme-contract.ts). Every direct Recharts
consumer calls it once and passes explicit values to grids, axes, tooltips,
cursors, legends/labels, and series/reference primitives. Custom tooltip
content uses semantic layout tokens as well. Default Recharts colors are not
accepted as “themed,” because their browser/library defaults may remain light.

Categorical ramps contain exactly six unique slots in stable order. Existing
consumers keep their established entity/index mapping and `index % 6` overflow
behavior; the hook centralizes the normalized modulo helper. Fixed roles such
as winner/loser/neutral, contributions, anchor, and frontier outline are named
separately and validated against both surfaces. Legend text stays neutral while
swatches and secondary labels/tables carry identity, preserving #497's
contrast mitigation.

### Palette validator reconstruction

The first implementation slice recreates the documented manual audit as code.
It must reproduce the retired-ramp failure, the accepted light-ramp hard passes
and warnings, and the current ramp's published dark-surface failure before a
new dark candidate can be accepted. The script records the exact conversions,
theme-specific lightness bands, chroma floor, normal/CVD separation bands, and
surface contrast dispositions used to reproduce those fixtures.

Dark colors preserve the six existing hue identities and order but are chosen
individually. Automatic inversion and per-view ramps are forbidden. A candidate
cannot enter `chart-palettes.json` until the validator reports no dark
lightness/contrast hard failure and no other hard failure. Warnings are allowed
only where every consumer supplies the documented secondary encoding.

### Migration and release sequencing

1. Add failing palette/source contracts and reconstruct validator parity.
2. Add light semantic tokens, provider/bootstrap, and theme contracts while the
   UI still renders equivalently in light mode.
3. Migrate Layout and all component surfaces by role; keep the dark control
   unavailable until the literal-color scan passes.
4. Add the chart hook and migrate all 12 Recharts files/30 declarations,
   including implicit defaults and custom content.
5. Select/validate the dark ramp, define dark values for every semantic/status
   role, expose the Settings control, and complete the two-theme visual matrix.

This ordering keeps each internal layer independently testable while preventing
users from reaching a known partially migrated dark theme.

## Validation Strategy

1. Palette tests first: reproduce #497/#503 published fixtures, then require the
   runtime light/dark ramps to contain six unique colors, preserve slot order,
   pass every hard gate, and retain documented warnings/secondary encodings.
2. Theme source contracts: verify one storage key and closed preference values,
   bootstrap-before-mount behavior, provider wrapping, document theme/color-
   scheme synchronization, live system subscription, Settings radio semantics,
   and guarded storage access.
3. Migration contracts: dynamically scan all current component TSX files and
   shared frontend files; reject targeted gray/white utilities, literal neutral
   hex layout styles, local categorical ramps, and unthemed status surfaces.
4. Chart contracts: inventory every `recharts` importer; require
   `useChartTheme()` and explicit shared values for grid/axis/tooltip/cursor/
   legend/series roles. Exercise six slots and overflow modulo semantics.
5. Compile/bundle gates: run `npx tsc --noEmit` and `npm run build` from
   `planalign_studio` using existing installed dependencies.
6. Browser matrix: validate first visit and live OS changes, explicit persistence
   and system reset, storage failure fallback, every route/shell fallback/modal,
   all chart types at normal and six/overflow series counts, and a toggle while
   an unsaved Configure field is populated. Confirm no reload, route change,
   value loss, console error, or light-only surface.
7. Database isolation: no simulation/dbt validation is necessary or authorized
   because the feature has no behavioral data path. Validation must not run dbt
   or write `dbt/simulation.duckdb`.

## Complexity Tracking

No constitution violations; table intentionally omitted.
