# Data Model: Dark Mode Token Layer

This feature adds client-side value objects and state only. It creates no API,
Pydantic, DuckDB, dbt, workspace, or run-archive entity.

## 1. Theme Preference

The user's intent, independent of the theme currently rendered.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `preference` | `'system' \| 'light' \| 'dark'` | yes | Closed enum; invalid external values become `system` |
| `storageKey` | string constant | yes | One versioned, application-global per-origin key shared by bootstrap/provider |
| `storedValue` | `'light' \| 'dark' \| null` | derived | `system` is represented by absence, not by persisting a resolved value |

### Validation rules

- Only exact lowercase `light` and `dark` storage values are accepted.
- Missing, malformed, or inaccessible storage resolves to `system` without
  preventing application mount.
- Setting `system` removes the key.
- Preference is browser/origin scoped, not workspace, scenario, user-account,
  server, or device scoped.

## 2. Resolved Theme

The concrete theme rendered at a point in time.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `mode` | `'light' \| 'dark'` | yes | Explicit preference wins; otherwise current OS media query decides |
| `source` | `'explicit' \| 'system'` | yes | Indicates whether media-query changes may alter `mode` |
| `documentTheme` | string | derived | Exact `mode` written to `document.documentElement.dataset.theme` |
| `colorScheme` | string | derived | Exact `mode` written to the document's CSS `color-scheme` |

### Invariants

- `preference = light` implies `mode = light` regardless of OS changes.
- `preference = dark` implies `mode = dark` regardless of OS changes.
- `preference = system` implies `mode` equals the current
  `(prefers-color-scheme: dark)` result and updates when it changes.
- Document theme and provider context describe the same resolved mode after
  each transition.
- Changing mode does not replace or key the React router/component tree.

## 3. Semantic Color Token

A named UI role whose value depends on the resolved theme.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `name` | semantic token identifier | yes | Stable across themes and meaningful by UI role |
| `lightValue` | CSS color | yes | Valid concrete color with required contrast |
| `darkValue` | CSS color | yes | Independently selected, not automatically inverted |
| `family` | surface/text/border/status/chart/brand | yes | Determines intended consumers and validation |
| `tailwindUtility` | generated utility name or null | conditional | Layout/status roles expose a semantic Tailwind class |

### Required relationships

- Each public semantic name has exactly one light and one dark value.
- Components depend on semantic names, never on a theme-specific value.
- Status feedback uses a coordinated surface/text/border triple.
- Chart surface roles correspond to the same surrounding surface hierarchy.
- Brand tokens may remain brand-specific but must pass contrast in both modes.

### Validation rules

- No required token may be missing in either theme.
- Foreground/background pairs must pass their documented contrast gate.
- Token names describe roles (`ink-muted`) rather than physical colors
  (`gray-500`).
- Private raw variables may differ from public Tailwind token names, but the
  mapping is one-to-one and selector switched.

## 4. Categorical Ramp

The theme-specific ordered colors used for categorical identity.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `mode` | `'light' \| 'dark'` | yes | One ramp per resolved theme |
| `surface` | CSS color | yes | Raised chart surface used by validation |
| `slots` | readonly six-color tuple | yes | Exactly six unique colors in stable identity order |
| `hueIdentity` | readonly six-role tuple | yes | Same hue family/order in both modes |
| `validation` | PaletteValidationResult | yes | No hard failure before runtime use |

### Invariants

- Light and dark ramps have equal length and slot semantics.
- Dark slots are selected individually from the light slot's hue identity; no
  inversion or per-view override is permitted.
- `colorAt(index)` returns `slots[normalizedModulo(index, 6)]` and preserves the
  current overflow behavior.
- Filtering/reordering semantics remain owned by each existing consumer; this
  feature does not introduce a new identity-ranking policy.

## 5. Chart Theme

The complete set of values that a Recharts consumer receives from the active
resolved theme.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `mode` | ResolvedTheme | yes | Equals provider mode |
| `grid` | line/cursor/reference colors | yes | Used explicitly by grid/cursor/reference primitives |
| `axis` | line/tick/label colors | yes | Used explicitly by both axes and labels |
| `tooltip` | background/border/text/muted/cursor style | yes | Ready to spread into default/custom tooltips |
| `legendText` | color | yes | Neutral readable ink; series swatches retain identity |
| `categorical` | CategoricalRamp slots | yes | Six validated slots for current mode |
| `semantic` | named series-role map | yes | Primary, positive, negative, neutral, warning, anchor, frontier, contributions |
| `colorAt` | `(index: number) => string` | yes | Stable normalized modulo lookup |

### Relationships

- `ThemePreference` resolves to one `ResolvedTheme`.
- One `ResolvedTheme` selects one complete `ChartTheme`.
- Every direct Recharts consumer reads that `ChartTheme` through
  `useChartTheme()`; no consumer selects its own theme or palette.
- Categorical and semantic series values are distinct even when a semantic role
  intentionally points to a categorical slot.

## 6. Palette Validation Result

The deterministic result of the reconstructed #497/#503 audit.

| Field | Type | Required | Rules |
|---|---|---:|---|
| `palette` | ramp identifier | yes | Retired fixture, light runtime, or dark runtime |
| `surface` | CSS color | yes | Exact validation background |
| `lightness` | check result | yes | Theme-specific usable band and offending slots |
| `chroma` | check result | yes | Published minimum floor |
| `normalSeparation` | check result | yes | Adjacent pair and Delta E versus hard floor |
| `cvdSeparation` | check result(s) | yes | Adjacent simulated-vision pair disposition |
| `surfaceContrast` | check result | yes | Per-slot ratio and pass/warn/fail disposition |
| `hardFailures` | integer | yes | Must be zero for runtime ramps |
| `warnings` | ordered list | yes | Must name required secondary encoding |

### Validation rules

- The retired and accepted light fixtures must reproduce their published
  outcomes before the dark runtime ramp is evaluated.
- Runtime ramps require `hardFailures = 0`.
- A warning is not silently promoted to pass; its mitigation is documented and
  verified across every consuming view.
- Results are deterministic and independent of locale, browser, and rendering
  order.

## State Transitions

```text
startup
  ├─ valid stored light ───────────────> explicit/light
  ├─ valid stored dark ────────────────> explicit/dark
  └─ missing/invalid/unreadable storage
       ├─ OS prefers dark ─────────────> system/dark
       └─ OS prefers light ────────────> system/light

system/light <──── OS media change ────> system/dark

any state ── choose Light ─────────────> explicit/light + store light
any state ── choose Dark ──────────────> explicit/dark + store dark
explicit/* ─ choose System ────────────> system/current-OS + remove key
```

Every successful transition updates provider state, root `data-theme`, and
`color-scheme` together. OS events received in an explicit state cause no
transition. Theme transitions never reset route, form, simulation, or workspace
state.
