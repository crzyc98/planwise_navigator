# UI Contract: Cohort Selector on Cost Comparison

**Feature**: 134-new-hire-cohort
**Component**: `planalign_studio/components/ScenarioCostComparison.tsx`
**Date**: 2026-08-06

## Cohort Segmented Control

**Location**: "Employer Cost Trends" chart header, in the same row as the existing Annual/Cumulative toggle (`ScenarioCostComparison.tsx:927-941`), positioned before or after it — same `bg-gray-100 p-1 rounded-lg` segmented-control styling, not a new visual pattern.

**Options**:

| Value | Label | Notes |
|---|---|---|
| `all` | "All employees" | Default. |
| `new_hires` | "New hires" | Segmented-control label stays short; the full "Hired during the simulation ({year}+)" text is reserved for the badge/methodology copy, not the toggle itself. |
| `baseline` | "Starting census" | |

**Behavior**: Selecting a value updates `cohort` state, which is a dependency of `fetchComparison` — selection triggers a full re-fetch and replace of `comparisonData` for every currently-selected scenario (FR-014). No partial/stale mixing across scenarios.

## Cohort Badge

**Shown**: Only when `cohort !== 'all'`.

**Placement**: Next to the chart title on both "Employer Cost Trends" and "Incremental Costs vs. {anchor}" (`ScenarioCostComparison.tsx:923`, `:1018-1020`), and next to the "Multi-Year Cost Matrix" header (`:1083`).

**Text**: `Hired during the simulation ({resolved_first_simulation_year}+)` for `new_hires`, `Starting census` for `baseline`. `{resolved_first_simulation_year}` comes from the anchor scenario's `DCPlanAnalytics.resolved_first_simulation_year` (all selected scenarios are expected to share a comparable horizon per the spec's Assumptions; if they don't, the badge uses the anchor's value — reconciling divergent horizons across scenarios is out of scope).

**Visual**: A small pill/chip, visually distinct from the existing anchor/baseline chips already used elsewhere in the view (`ScenarioCostComparison.tsx:900-905` shows the existing chip style to match) — not a bare inline text change, so it reads as a filter indicator, not part of the chart title (per spec FR-009 / "misread risk" concern).

## Empty State

**Trigger**: A scenario/year cell where the cohort-filtered `total_eligible_count === 0` (no employees at all in that cohort for that year) — e.g. `baseline` on a fully-turned-over population.

**Rendering**: The cost matrix cell and any corresponding chart data point MUST render an explicit "—" / "No employees in cohort" indicator, distinguishable from a computed `$0` (which means employees exist but contributed nothing).

## Methodology Panel

**Location**: "How these figures are measured" panel (`ScenarioCostComparison.tsx:1276-1297`).

**Change**: When `cohort !== 'all'`, insert one additional sentence naming the active cohort and its definition, e.g.:
> Figures reflect only the **{cohort label}** cohort: employees hired on or after {resolved_first_simulation_year} (or, for Starting census, everyone else).

## TSV Export

**Change**: `tableToTSV()` (`ScenarioCostComparison.tsx:598`) and `compensationTableToTSV()` (`:644`) prepend a single comment-style line when `cohort !== 'all'`:
```
# Cohort: Hired during the simulation (2025+)
```
before the existing header row, so pasted output still identifies the active cohort out of UI context.

## Persistence

**Storage key**: unchanged, `planalign_comparison_{workspaceId}`.

**Shape addition**: `cohort?: 'all' | 'new_hires' | 'baseline'`, written by the existing `saveComparisonPrefs` effect (`:532-541`) whenever cohort changes, alongside `selectedIds`/`anchorId`.

**Load-time validation**: `loadComparisonPrefs` (`:73`) — if the stored `cohort` value is present but not one of the three recognized strings, treat it as absent and default to `'all'`. This must not throw or block restoring `selectedIds`/`anchorId`.
