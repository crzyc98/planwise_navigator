# Quickstart: Validate the Dark Mode Token Layer

This guide validates the completed feature. It does not run dbt, mutate a
simulation, or use the shared `dbt/simulation.duckdb`.

## Prerequisites

- Repository virtual environment already installed.
- Existing `planalign_studio/node_modules` dependency set available; do not add
  or fetch packages solely to run this guide.
- A modern browser that can emulate `prefers-color-scheme` and inspect local
  storage.
- Optional existing Studio workspace/scenario results for chart-rich routes.
  If new simulation data is required, create it only in a disposable isolated
  database under `/tmp` according to repository policy.

From the repository root:

```bash
source .venv/bin/activate
```

## 1. Run the fast palette and source contracts

```bash
pytest -m fast \
  tests/unit/test_studio_palette.py \
  tests/unit/test_studio_theme_contract.py -v
```

Expected outcomes:

- The reconstructed #497/#503 validator reproduces the retired-ramp failure,
  accepted light-ramp passes/warnings, and documented dark-surface failure.
- The runtime light and dark ramps each contain six unique, stable slots and
  report zero hard failures for their own surface.
- All current Studio components use semantic layout/status roles; no targeted
  `bg-white`, `text-gray-*`, or `border-gray/slate-*` form remains.
- Every Recharts importer consumes `useChartTheme()` and explicitly themes the
  primitives it uses.
- Bootstrap, provider, storage key, Settings control, and system media-query
  behavior satisfy [validation-contract.md](./contracts/validation-contract.md).

Run the validator directly when reviewing a palette change:

```bash
python scripts/validate_studio_palette.py
```

Expected outcome: the report identifies both surfaces and all six slots,
records hard checks and warnings, and exits successfully only when both runtime
ramps are acceptable. A warning must name its secondary-encoding requirement.

## 2. Run a direct legacy-color audit

The contract test is authoritative; these searches provide a review-friendly
second view:

```bash
rg -n 'bg-white|text-gray-|border-(gray|slate)-' \
  planalign_studio/components planalign_studio/App.tsx

rg -n '#[0-9A-Fa-f]{3,8}' \
  planalign_studio/components \
  --glob '*.tsx'
```

Expected outcome: the first command returns no match. Review every result from
the second command; acceptable results are limited to non-color syntax or a
narrowly documented data-driven case. Chart and layout colors must originate
from the shared theme source.

## 3. Type-check and build Studio

```bash
cd planalign_studio
./node_modules/.bin/tsc --noEmit
npm run build
cd ..
```

Expected outcome: TypeScript reports no errors and Vite produces the production
bundle without fetching a dependency. This gate catches hook/type drift but is
not a substitute for the browser matrix.

## 4. Start Studio for browser validation

```bash
planalign studio --no-browser --verbose
```

Open the locally reported Studio URL. Use browser developer tools to inspect
`document.documentElement.dataset.theme`, the root `color-scheme`, local
storage, and emulated OS color preference.

## 5. Verify preference transitions

Use the Settings menu's System/Light/Dark control.

1. Remove the theme storage key and emulate OS light before a fresh load.
   Studio must first-paint light with preference System.
2. Emulate OS dark and fresh-load again. Studio must first-paint dark without a
   visible light flash.
3. While preference remains System, change the emulated OS preference. The
   current page and charts must update live.
4. Choose Light, then emulate OS dark. Studio must remain light and store only
   the explicit Light value.
5. Reload. Light must remain active.
6. Choose Dark, reload, and confirm Dark remains active.
7. Choose System. The storage key must be removed and the current OS theme must
   apply immediately.
8. Put an invalid value in the key and reload; then simulate storage access
   failure if the browser supports it. Studio must remain usable and fall back
   to System.

Expected outcome: provider preference, resolved root attribute, native
`color-scheme`, semantic layout, and chart theme remain synchronized throughout.

## 6. Verify no state loss on theme changes

1. Open Configure for a scenario.
2. Change a form value without saving.
3. Open Settings and switch to the opposite explicit theme.
4. Confirm the URL/route, selected workspace/scenario, expanded section, and
   unsaved form value remain unchanged.

Repeat while a dropdown or modal is open and on a live/completed simulation
detail view when available.

Expected outcome: the theme changes without page reload, route remount, lost
input, or interrupted application state.

## 7. Inspect every surface and chart type

Review every current route in `planalign_studio/App.tsx` in Light and Dark,
including:

- Dashboard, Import, Scenarios, Configure, Simulate/detail/provenance, Batch,
  Timeline, Calibration, Optimizer, Workspaces;
- Analytics Overview, DC Plan, Vesting, NDT, Winners & Losers, scenario
  comparison/diff, and Cost Comparison; and
- Layout loading, API error, no-workspace, modal, dropdown, notification,
  tooltip, table, form/input, log/code, disabled, focus, and status states.

For the 12 direct Recharts consumers, exercise line, bar, area, composed, pie,
and scatter charts. Confirm:

- grids, axes/ticks, labels, references, cursors, legends, and tooltip panels
  are readable and change with the theme;
- categorical identity stays in the same slot when switching themes;
- six simultaneous slots are distinguishable with the documented legend plus
  table/direct-label cue;
- an existing over-capacity optimizer/categorical case wraps with the same
  modulo behavior as light mode; and
- positive/negative/neutral, contribution, anchor, and frontier roles remain
  semantically correct.

Repeat the visual scan at a normal desktop width and approximately 900px. There
must be no literal white panel, unreadable gray text, clipped toggle, unexpected
default Recharts styling, or console error.

## 8. Final acceptance checklist

- [ ] System, Light, and Dark preference transitions match
      [data-model.md](./data-model.md).
- [ ] Explicit preference first-paints correctly and survives reload.
- [ ] Live OS changes affect only System preference.
- [ ] All current component files pass the semantic token scan.
- [ ] All 30 chart declarations use the shared chart theme.
- [ ] Both six-slot ramps pass the executable palette gate with zero hard
      failures; warnings have secondary encoding.
- [ ] Theme changes preserve current route and unsaved UI state.
- [ ] Every reachable screen and shell fallback state is legible in both modes.
- [ ] No command in this validation mutated the shared development database.

## 9. Implementation validation record (2026-08-17)

Completed from the repository virtual environment:

- `pytest -m fast tests/unit/test_studio_palette.py tests/unit/test_studio_theme_contract.py -v` — **12 passed**.
- `python scripts/validate_studio_palette.py` — **exit 0** for both six-slot runtime ramps. The published light contrast/CVD warnings and dark CVD warning remain documented mitigations requiring neutral legends plus tables or direct labels.
- Direct legacy-neutral and quoted component-hex searches — **no matches** across `components/**/*.tsx` and `App.tsx`.
- `ruff check` for the validator and theme test files — **passed**.
- `./node_modules/.bin/tsc --noEmit` — **passed**.
- `npm run build` — **passed**. Vite retained its existing dynamic/static import and large-chunk warnings; neither warning is theme-related.
- `git diff --check` — **passed**; the diff contains no `planalign_api/`, `dbt/`, database, or export-contract change.
- `planalign studio --no-browser --verbose` — API and frontend started successfully on loopback. Fetching the live frontend confirmed the color-scheme metadata and stored/system bootstrap precede the application module.

The interactive browser backend was unavailable in this session (browser
discovery returned no connected browser). Therefore the transition/state-loss
matrix in sections 5–6, the two-theme visual matrix in section 7, and
browser-observed keyboard/console checks remain deliberately unrecorded and
their tasks remain open. Resume with the running Studio URL and complete those
checks before final visual acceptance; no new simulation or shared-database
write is required when existing workspace results are available.
