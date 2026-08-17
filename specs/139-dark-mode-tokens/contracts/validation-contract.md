# Validation Contract: Studio Theme and Chart Palette

## Automated gates

### Palette parity and acceptance

The checked-in validator must run without a network call or new package and
must read the same light/dark six-slot source imported by Studio.

Before validating the dark ramp, it must reproduce the published #497/#503
fixtures:

1. The retired palette fails the recorded lightness and adjacent normal-vision
   checks.
2. The accepted light Okabe-Ito ramp has all six slots within the published
   `0.43–0.77` lightness band, chroma at least `0.1`, and worst adjacent normal
   Delta E at least `15`.
3. The accepted light ramp retains its documented CVD and sub-`3:1` contrast
   warnings; warnings are not rewritten as passes.
4. The light ramp fails the published dark-surface lightness fixture against
   `#1a1a19` for the documented bright slots.

The runtime dark ramp is accepted only when:

- it has exactly six unique colors;
- slot order and hue identities match the light ramp;
- the reconstructed validator reports zero hard failures;
- its dark-surface lightness and contrast checks have zero failures; and
- every warning names a required legend plus table/direct-label mitigation that
  is present in every consumer.

### Source migration scan

The fast source-contract test scans the current frontend tree dynamically. It
fails if a migrated component contains:

- `bg-white`;
- `text-gray-*`;
- `border-gray-*` or `border-slate-*`;
- literal neutral gray/white layout colors in JSX style objects; or
- a local categorical chart array or direct literal chart grid/axis/tooltip/
  series color.

Narrow allowlists may cover syntax that is not a color (for example numeric
HTML entities) and values that are genuinely data supplied at runtime. An
allowlist must identify the exact file/pattern and rationale; broad directory
or hex allowlists are prohibited.

### Recharts contract

Every file importing from `recharts` must:

- call the shared `useChartTheme()` hook;
- give Cartesian grids, axes, tooltips/cursors, and legends/custom labels an
  explicit shared theme value where those primitives are present;
- source categorical and semantic series roles from the hook;
- retain a non-color identity cue for categorical warnings; and
- avoid relying on Recharts' light/default styling.

The inventory is dynamic, while the initial baseline is 12 importing files and
30 chart declarations.

### Preference/bootstrap contract

Automated source checks require:

- one accepted preference enum and one versioned storage key;
- guarded storage reads/writes/removal;
- a root provider above `App`;
- a pre-mount document theme bootstrap;
- root `data-theme` and `color-scheme` synchronization;
- a cleaned-up `matchMedia` change subscription active for system behavior;
- an accessible System/Light/Dark Settings control; and
- no `window.location.reload()` or theme-dependent key on the router/app tree.

## Compile and bundle gates

Run from `planalign_studio/`:

```bash
npx tsc --noEmit
npm run build
```

Both commands must succeed using the existing installed dependency set.

## Manual browser acceptance matrix

Validate at minimum:

- no stored value with OS light and OS dark;
- a live OS change while preference is System;
- explicit Light/Dark persistence across reload and precedence over OS changes;
- return to System and invalid/unavailable storage fallback;
- every route in `App.tsx`, Layout loading/error/no-workspace states, menus,
  modals, inputs, tables, logs, tooltips, and status panels;
- all 12 Recharts consumers and all chart types in both themes;
- six simultaneous categorical slots and an existing over-capacity modulo case;
- theme change while an unsaved Configure input is populated; and
- desktop and approximately 900px viewport widths.

Expected result: theme changes cause no reload, route change, state loss,
console error, unthemed default, illegible status, or literal light-only panel.

## Database boundary

This feature has no simulation behavior. Validation must not execute dbt or
write `dbt/simulation.duckdb`. Any optional Studio data setup must use an
existing scenario or a disposable isolated database as required by repository
policy.
