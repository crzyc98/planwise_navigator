# Research: Dark Mode Token Layer

## D1: Use selector-switched semantic CSS tokens

**Decision**: Define raw light values on `:root` and dark values on
`:root[data-theme='dark']` in `planalign_studio/index.css`. Expose those values
to Tailwind v4 through `@theme inline`, producing role-based utilities such as
`bg-surface`, `bg-surface-raised`, `text-ink`, `text-ink-muted`, and
`border-border`. Keep Fidelity brand colors separate from neutral and status
roles.

The minimum product vocabulary is expanded just enough to preserve the current
visual hierarchy:

- canvas, raised/panel, and subtle/hover surfaces;
- primary, muted, and subtle text;
- normal and strong borders;
- input, overlay, inverse, focus, and disabled roles;
- paired success, warning, danger, and information surfaces/text/borders; and
- chart grid, axis, tooltip, cursor, reference, legend, and series roles.

**Rationale**: Tailwind v4's `@theme inline` pattern lets semantic utilities
resolve through selector-switched CSS variables without duplicating `dark:`
classes in every component. More than the five required base tokens are needed
because the existing gray scale encodes panels, hover states, inputs, disabled
states, and status feedback as distinct roles. A deliberately small role set
preserves those distinctions while satisfying the single-change theme goal.

**Alternatives considered**: Globally remap Tailwind's gray scale (rejected
because literal gray class names would remain and missed migrations would be
hidden); add `dark:` variants beside every existing utility (rejected because
it duplicates theme decisions across 53 files); introduce a component library
(rejected as a broad dependency and refactor outside this feature).

## D2: Model preference separately from the resolved theme

**Decision**: Add a root `ThemeProvider` above `App` with
`ThemePreference = 'system' | 'light' | 'dark'` and
`ResolvedTheme = 'light' | 'dark'`. `useTheme()` exposes the preference,
resolved theme, an explicit setter, a convenience toggle, and a reset to
system. The Settings dropdown's dormant boolean row becomes an accessible
System/Light/Dark radio group.

Only explicit `light` or `dark` values are stored under one versioned,
per-origin local-storage key. Missing, invalid, or unreadable storage means
`system`. In system mode a single `matchMedia('(prefers-color-scheme: dark)')`
subscription follows operating-system changes live; an explicit preference
ignores those changes. Every storage access is guarded, listeners are safe
under React Strict Mode, and the provider sets both the root `data-theme`
attribute and `color-scheme`.

**Rationale**: A boolean cannot represent “follow system” or let a user clear
an override. One root authority keeps layout and charts synchronized and
avoids route remounts, so changing the theme cannot discard unsaved form state.
The existing global Settings menu is already visible on every normal route and
is therefore the correct control location.

**Alternatives considered**: Keep `isDarkMode` inside `Layout` (rejected
because loading/error/empty states render before the normal shell and chart
consumers would gain a second authority); persist the resolved system theme
(rejected because the app would stop following later OS changes); store the
preference in workspace/API configuration (rejected because the requirement is
per browser and no cross-device sync is requested).

## D3: Apply the initial theme before React mounts

**Decision**: Put a small local bootstrap in the document head that safely
reads the same storage key, falls back to `matchMedia`, and assigns
`document.documentElement.dataset.theme` and `style.colorScheme` before the
application module executes. Add a `color-scheme` meta declaration and keep the
provider's initialization contract synchronized with the bootstrap.

**Rationale**: A React effect runs after the first paint and would flash the
wrong theme when a persisted preference differs from the operating system.
CSS media queries alone solve first-time/system visits but cannot honor a
stored override before paint. The bootstrap is local, dependency-free, and
does not weaken API authentication or network bindings.

**Alternatives considered**: Provider effect only (rejected because of the
first-paint flash); CSS `prefers-color-scheme` only (rejected because explicit
preferences cannot override it); a remote theme script (rejected by Studio's
bundled-asset security rule). A future strict Studio CSP would require a hash,
nonce, or blocking same-origin bootstrap asset; no such CSP is currently
defined for the Vite HTML.

## D4: Expose one typed chart theme selected by resolved theme

**Decision**: Create immutable light and dark `ChartTheme` maps and a
`useChartTheme()` hook that selects one from `useTheme().resolvedTheme`. The
contract includes grid/cursor/reference colors, axis/tick/label colors,
ready-to-spread tooltip styles, neutral legend text, the six-slot categorical
ramp, stable semantic roles (primary, positive, negative, neutral, warning,
anchor, frontier outline, and contribution roles), and a modulo `colorAt`
helper.

All 12 files importing Recharts and all 30 chart declarations must consume the
hook. This includes charts currently relying on Recharts defaults, custom
tooltips and legends, local palette arrays, fixed comparison/vesting/status
colors, pie labels, and reference/frontier strokes. Entity-to-slot assignment
semantics stay unchanged; only the color resolved for each slot changes with
the theme. More than six series continue to wrap with modulo indexing, matching
current behavior rather than adding a new error or silently extending the
validated ramp.

**Rationale**: Recharts grid, axis, tooltip, cursor, legend, and series props
cannot be migrated with Tailwind classes alone. Selecting a complete typed map
from the resolved theme produces an immediate React update and provides a
single reviewable source for every chart role. Keeping semantic series roles
separate from categorical identity prevents “positive” or “anchor” from being
accidentally reassigned as palettes evolve.

**Alternatives considered**: Return only CSS `var(...)` strings (rejected as
the sole mechanism because hook output would not itself vary and palette
validation would be less direct); read `getComputedStyle` in every chart
(rejected because it causes layout work and creates browser-only coupling);
wrap every Recharts primitive (rejected as an unnecessarily broad refactor,
though a small shared tooltip/legend helper is allowed).

## D5: Reconstruct and check in the #497 palette audit before selecting dark colors

**Decision**: Treat the missing validator as an explicit prerequisite. Add a
dependency-free palette validation module/test whose fixtures reproduce the
published #497/#503 outcomes before accepting new colors:

- the retired ramp fails its published lightness and normal-vision checks;
- the current Okabe-Ito light ramp passes the documented hard checks with
  lightness in `0.43–0.77`, chroma at least `0.1`, and adjacent normal-vision
  Delta E at least `15`;
- contrast below `3:1` and the published CVD close pair remain warnings only
  when every consumer also provides a legend plus table/direct labels; and
- the current light ramp reproduces the published dark-surface lightness
  failure against `#1a1a19`.

The dark ramp will use the same six hue identities, preserve slot order, and be
chosen by the reconstructed validator rather than inversion. Its exact values
are accepted only when every slot has zero dark-surface lightness/contrast-band
hard failures, all hard pairwise/chroma checks pass, and any documented warning
has secondary encoding in every consumer. Store light and dark ramps in one
machine-readable source consumed by both the validator and TypeScript so test
and runtime values cannot drift. The validator's reconstructed thresholds and
provenance must be documented in its source; it must not be described as a
previously checked-in tool.

**Rationale**: Issue #497 and PR #503 contain audit output but the repository
contains no validator script or test. Claiming to “reuse” it would create a
false quality gate. Reproducing the known pass/fail fixtures first makes the
methodology durable, then gives FR-004/FR-005 an executable acceptance rule.

**Alternatives considered**: Invert the light ramp (explicitly prohibited and
known to fail); choose colors by visual inspection alone (not reproducible);
copy separate arrays into CSS and TypeScript (rejected because they can drift);
add a color-science package (rejected because the required conversions and
checks can be implemented with the standard library and existing test stack).

## D6: Migrate by semantic role and gate the entire current tree

**Decision**: Migrate the shell/toggle first, then reusable form/config
subcomponents, then chart-heavy views, and finally run a dynamic source scan
over `planalign_studio/components/**/*.tsx` plus `App.tsx` and shared theme
files. Map each usage by role rather than applying a blind gray-to-token search
and replace. Do not expose the working dark control until layout and chart
scans pass.

The specification's 53-file count is confirmed for components containing the
targeted `bg-white`, `text-gray-*`, or `border-gray/slate-*` forms. The source
tree currently has 54 component TSX files total, and all must be audited because
one additional file contains other inline color literals. Status colors,
inputs, disabled states, placeholders, overlays, tables, code/log surfaces,
and custom SVG/Recharts defaults are included even when SC-001's example regex
does not catch them.

**Rationale**: Identical gray utilities play different semantic roles today.
Role-based migration preserves hierarchy and contrast. A dynamic scan avoids a
stale fixed inventory as files move or are added during implementation.

**Alternatives considered**: One mechanical replacement table (rejected
because it flattens hierarchy and misclassifies status states); allow legacy
classes behind dark overrides (rejected because SC-001 requires their removal);
ship the toggle before the migration finishes (rejected because it would expose
known light-only surfaces).

## D7: Use existing build tooling plus dependency-free contract gates

**Decision**: Add fast pytest source-contract and palette tests, then run an
explicit TypeScript check and Vite production build. Contract tests dynamically
inventory every Recharts importer, require the shared hook and explicit themed
grid/axis/tooltip/legend handling, reject local chart palettes and forbidden
layout/chart literals, and verify the bootstrap/provider use the same storage
contract. The palette test checks both ramps, duplicate/slot counts, stable
ordering, and modulo overflow semantics.

Manual browser validation remains required for runtime and visual behavior:
system light/dark first visit, live OS changes in system mode, explicit
override persistence, reset to system, invalid/unavailable storage fallback,
all reachable routes and shell fallback states, all chart types, six-series and
overflow cases, and theme changes while an unsaved form is populated.

**Rationale**: The frontend currently has no Vitest/Jest/RTL/browser runner and
CI does not install Node. Existing Studio features use Python source contracts
plus `tsc`/Vite builds. This design adds meaningful automated acceptance without
a new runtime or test dependency while being honest that source checks do not
replace a two-theme browser visual pass.

**Alternatives considered**: Add Vitest/jsdom/React Testing Library (stronger
runtime unit coverage but introduces several dependencies and CI setup for a
single cross-cutting feature); rely only on manual checks (rejected because the
constitution requires test-first development); validate against a simulation
database (rejected because this feature does not touch simulation behavior or
storage).

## D8: Keep the feature entirely client-side

**Decision**: Do not add an API endpoint, server configuration field, database
table, workspace preference, or export behavior. Local storage contains only
the non-sensitive per-browser theme choice. Existing interactive route state
and simulation data remain untouched.

**Rationale**: This matches the specification's persistence and export scope,
keeps the implementation reversible, and preserves all event-sourcing,
database, and API security boundaries.

**Alternatives considered**: Account/workspace theme sync (out of scope and no
account model exists); server-rendered theme negotiation (unnecessary for the
Vite client); themed report exports (explicitly out of scope).
