# Research: Studio Two-Scenario Diff View

**Feature**: 110-scenario-diff-view | **Date**: 2026-07-12

No `NEEDS CLARIFICATION` markers remain. These decisions record the existing codebase patterns and resolve integration details before design.

## D1: Reuse the existing comparison response for metric data

**Decision**: Call the existing workspace comparison with scenario A as `baseline` and add `avg_compensation` to `WorkforceMetrics`, `_query_workforce()`, baseline values, scenario values, and deltas. The new Studio page consumes `workforce_comparison` and `dc_plan_comparison` directly.

**Rationale**: `ComparisonService` already reads each isolated database in read-only mode and returns annual values plus baseline deltas for all other required metrics. An additive field preserves existing consumers and avoids the client-side aggregation that this feature is intended to eliminate.

**Alternatives considered**:
- Add a second metric endpoint: rejected because it would duplicate scenario validation, database resolution, annual alignment, and delta logic.
- Continue using per-scenario result summaries in Studio: rejected because those summaries do not carry the richer annual comparison contract and reproduce calculation logic in the browser.

## D2: Define average compensation from active snapshot rows

**Decision**: For each simulation year, calculate `AVG(prorated_annual_compensation)` only where `employment_status` is active (case-insensitive), returning `0.0` when no active rows exist. Represent values and deltas as floats.

**Rationale**: This is the definition in issue 426 and uses the same `fct_workforce_snapshot` already queried for workforce/DC-plan aggregates. Filtering inside the aggregate prevents terminated employees' partial-year compensation from changing the active-workforce measure.

**Alternatives considered**:
- Average all snapshot rows: rejected because terminated rows would make the measure inconsistent with the requested active-employee metric.
- Read `fct_compensation_growth`: rejected because the comparison service is already rooted in the snapshot, and introducing another mart creates unnecessary availability/build-order assumptions.

## D3: Resolve effective configurations through workspace storage

**Decision**: `ConfigDiffService` calls `WorkspaceStorage.get_merged_config(workspace_id, scenario_id)` for both scenarios. It does not implement merge rules itself.

**Rationale**: The storage method is the Studio simulation path's source of truth. It performs base-plus-override merging, atomic replacement for seed-driven sections, match-template reconciliation, and legacy defaults. Diffing raw override files would report source-file differences rather than the effective settings that governed the run.

**Alternatives considered**:
- Copy `ScenarioBatchRunner._deep_merge()`: rejected because it would diverge from Studio-specific reconciliation/default behavior.
- Diff only `config_overrides`: rejected because inherited base changes and equivalent override shapes would be misreported.

## D4: Deep-diff mappings; treat sequences as leaf values

**Decision**: Recursively compare mapping keys. Emit scalar or sequence differences at a deterministic dotted path, sort results lexically, and use status `changed`, `only_a`, or `only_b`. Lists/tuples are compared atomically rather than by numeric index. Count equal non-cosmetic leaves as `unchanged_count` but do not return them.

**Rationale**: Mapping recursion produces useful paths such as `employer_match.active_formula`. Treating tier arrays or band lists atomically avoids unstable index paths and noisy cascades when items are inserted or reordered. Status distinguishes a missing key from a present JSON null.

**Alternatives considered**:
- Flatten every list index: rejected because index shifts produce many false-looking changes and dotted numeric paths are not stable business identifiers.
- Return nested diff objects: rejected because the headline UI requires a sortable flat table and friendly label lookup by path.

## D5: Centralize cosmetic exclusions and friendly labels

**Decision**: The service owns one explicit cosmetic-key predicate (scenario/workspace names, descriptions, creation/update/run timestamps) applied before counting or emitting leaves. The API always returns the exact dotted path; the Studio page maps a curated set of known paths/prefixes to friendly labels and falls back to a title-cased final path segment.

**Rationale**: Exclusion must be consistent across clients, while presentation labels are UI copy and can evolve without changing the data contract. Exact paths preserve auditability even when a friendly label is used.

**Alternatives considered**:
- Exclude every key named `name`: rejected because nested formula names may be meaningful context; exclusions should be explicit and scoped.
- Return only friendly labels: rejected because labels are not stable identifiers and would make troubleshooting ambiguous.

## D6: Surface latest provenance and derive warnings without writes

**Decision**: Open each resolved scenario database with `read_only=True`. If `run_metadata` exists, return the latest row's 12-character fingerprint, seed, and timestamp. Also inspect the preceding row to flag unsuppressed mixed-generation risk (fingerprint/seed changed and latest run was neither a full reset nor calibration), and compare the latest fingerprint/seed with the scenario's currently resolved effective configuration where validation permits. Return per-scenario `drift_warning` plus reason codes; return top-level `seeds_match` as `true`, `false`, or `null` when either seed is unavailable, and top-level `drift_warning` as the OR of per-scenario warnings.

**Rationale**: The latest row says what generated the displayed results. The preceding row can reveal a mixed-generation rerun, while current-vs-recorded comparison reveals configuration edited after the last completed run—the two cases that make the phrase "config deltas that caused them" unsafe. The existing `compute_config_fingerprint()` remains the only fingerprint algorithm. Missing table/columns or invalid legacy config returns unavailable provenance instead of failing the comparison.

**Alternatives considered**:
- Compare fingerprints between A and B and call any difference drift: rejected because different scenario configurations are intentional and are the purpose of the feature.
- Read only the latest row with no history/current check: rejected because it cannot identify mixed-generation or post-run configuration edits.
- Persist a new drift flag: rejected because the feature is strictly read-only and issue 426 forbids new tables.

## D7: Keep configuration diff separate from the 667-line comparison service

**Decision**: Add `ConfigDiffService` as a small single-responsibility service and inject it into the existing comparison router. `ComparisonService` changes only for the additive workforce field.

**Rationale**: Configuration resolution, structural diffing, fingerprint validation, and provenance history are cohesive with one another but distinct from metric aggregation. This prevents an existing module already above the constitution's preferred size from growing substantially.

**Alternatives considered**:
- Add all methods to `ComparisonService`: rejected on modularity and test-isolation grounds.
- Put deep-diff logic in the router: rejected because routers should validate/translate HTTP inputs, not own business rules or database access.

## D8: Use one focused route and typed frontend models

**Decision**: Add `GET /api/workspaces/{workspace_id}/comparison/config-diff?scenario_a=...&scenario_b=...`. Preserve existing 404 behavior for missing workspace/scenario and 400 behavior for incomplete scenarios; add 400 for duplicate IDs. Define explicit TypeScript types for the full comparison response, including DC-plan fields, and the config-diff response. Add `/analytics/diff?a=...&b=...` in Studio.

**Rationale**: The route remains workspace-scoped and follows the existing comparison router. Separate metric/config calls allow the mature comparison payload to remain N-scenario capable while the config-diff contract stays explicitly two-scenario.

**Alternatives considered**:
- Embed config diff into every comparison response: rejected because N-way consumers do not need a pairwise configuration model and it would expand an established endpoint's work.
- Add a new combined UI-specific endpoint: rejected because it would duplicate the existing comparison contract and couple backend design to one screen.

## D9: Validation uses fixtures first, then two clean isolated scenarios

**Decision**: Unit tests create temporary DuckDB files with only the required snapshot, event, and run-metadata columns. Router tests override storage/services. End-to-end validation builds deliberate A/B scenario databases with matching seeds via `planalign batch --scenarios a b --clean`, then confirms the match lever is the only effective delta and that headcount/average compensation remain flat.

**Rationale**: Fixture tests are deterministic and fast; the isolated batch run proves real pipeline wiring and honors the repository rule never to validate behavioral changes in `dbt/simulation.duckdb`.

**Alternatives considered**:
- Validate against the shared development database: rejected by repository policy and because its mixed local state is not ground truth.
- Rely only on mocked service tests: rejected because they cannot prove the aggregate SQL, read-only database access, or real scenario merge behavior.
