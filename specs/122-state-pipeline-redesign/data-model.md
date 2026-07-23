# Phase 1 Data Model: State Pipeline Redesign

This feature adds internal execution/state relations and filesystem control records. It does not change public mart schemas or existing API response bodies.

## 1. Simulation Run

Represents one immutable Studio/API-managed attempt.

| Field | Type | Rules |
|---|---|---|
| `run_id` | UUID string | Canonical lowercase UUID; unique inside the scenario; used to derive, never escape, the run directory. |
| `workspace_id` | string | Existing validated workspace identifier. |
| `scenario_id` | string | Existing validated scenario identifier. |
| `status` | enum | `queued`, `running`, `completed`, `failed`, or `cancelled`. Terminal states do not transition again. |
| `started_at` | UTC datetime | Set once. |
| `completed_at` | UTC datetime/null | Required for terminal metadata. |
| `database_path` | derived path | Exactly `runs/<run_id>/simulation.duckdb`; not serialized into the publication pointer. |
| `config/provenance fingerprints` | strings | Existing provenance contract; no raw census records. |

Owned artifacts: `simulation.duckdb` and any live WAL, `config.yaml`, `simulation.log`, `run_metadata.json`, `provenance.json`, and optional exports.

Validation rules:

- The run directory and database destination must not exist before allocation.
- All writes for an attempt remain inside that run directory.
- A terminal run's database and authoritative metadata are immutable.
- Failed/cancelled runs may contain partial database state but cannot become current.
- Automatic completion-time pruning does not mutate older runs.

State transitions:

```text
allocated -> queued -> running -> completed -> published
                         |  \
                         |   -> cancelled
                         -> failed
```

`published` is a relationship recorded by the current-result pointer, not another mutable status inside the run.

## 2. Current Result Pointer

A private, atomic sidecar at `scenarios/<scenario>/current_result.json`.

| Field | Type | Rules |
|---|---|---|
| `schema_version` | integer | Starts at `1`; unsupported versions fail closed. |
| `run_id` | UUID string | Must identify a completed run under the same scenario. |
| `promoted_at` | UTC datetime | Written at atomic publication. |

Validation and publication:

- Validate UUID and containment before deriving the path.
- Require completed run metadata and a readable run DB.
- Serialize to a same-directory temporary file, flush/fsync, and replace atomically.
- Never update on failure or cancellation.
- If a pointer exists but is invalid or its target is missing, return an integrity error rather than silently selecting another result.
- If no pointer exists, the resolver may use the documented legacy lookup order.

Relationships:

- One scenario has zero or one current-result pointer.
- One pointer selects exactly one successful Simulation Run.
- Many historical/failed runs remain unselected and immutable.

## 3. Resolved Scenario Read Context

An internal typed value shared by DB-backed services and response-header handling.

| Field | Type | Rules |
|---|---|---|
| `database_path` | path | Selected successful run DB or documented legacy fallback. |
| `result_run_id` | UUID/null | Selected published run; null only for legacy data with no recoverable run ID. |
| `source` | existing enum/string | Retains compatible `scenario`/workspace/project semantics. |
| `active_run_id` | UUID/null | Newest queued/running attempt, if any. |
| `warning_code` | enum/null | `run_in_progress` when an active attempt differs from the served result. |

The context does not mutate scenario status. The selected run's archived config/DB determines reported years and result metadata.

## 4. Current-Year Event Assembly

Internal dbt relation `int_current_year_events`.

| Property | Contract |
|---|---|
| Grain | Same row grain as the existing `fct_yearly_events` publication input. |
| Scope | One runtime `simulation_year`, `scenario_id`, and `plan_design_id`. |
| Inputs | Complete active SQL event-candidate set through declared `ref` edges. |
| Responsibilities | Union compatible candidate schemas; retain deterministic event IDs; assign/preserve accepted event sequence and ordering; expose the exact public fact projection. |
| Exclusions | No read of current-year `fct_yearly_events`; no workforce/domain state accumulation; no Polars execution path. |

`fct_yearly_events` becomes the sole publisher of this relation with the existing public columns and partition replacement semantics. The assembly relation is internal and non-authoritative.

## 5. Canonical Workforce-State Record

Internal dbt relation `int_workforce_state_accumulator`.

Primary/unique key:

```text
(scenario_id, plan_design_id, employee_id, simulation_year)
```

Required field groups:

| Group | Representative fields | Ownership |
|---|---|---|
| Scope/identity | `scenario_id`, `plan_design_id`, `employee_id`, employee SSN/synthetic identifier where already required | Workforce |
| Dates | birth, hire, termination/effective termination dates | Workforce |
| Status | employment status, detailed status code, termination reason | Workforce |
| Compensation | current compensation, full-year equivalent, prorated compensation | Workforce |
| Workforce classification | level, current age, tenure/years of service, age band, tenure band | Workforce |
| Carry-forward schedule | scheduled hours/week only if required to reproduce accepted state | Workforce |

Forbidden field groups: enrollment flags/dates, deferral rates, eligibility decisions, employee contributions, employer core/match, and account balances.

Transition rules:

- Initial year derives from census plus current-year immutable workforce events with no assumed prior relation.
- Year N reads only its own year N-1 accumulator rows and current-year published workforce events.
- Terminated employees obey the Feature 112 boundary.
- Scope values come from runtime/dbt variables and event/census inputs; no hard-coded scenario/plan values.
- Materialization is incremental `delete+insert` scoped to the four-key grain and current simulation year.

## 6. Workforce State Projection

A disposable orchestrator-built relation declared under an orchestrator source.

| Field/property | Rule |
|---|---|
| `decision_year` | Current orchestration year N. |
| Workforce columns | Compatible subset required by foundation/event candidate helpers. |
| Source | Canonical accumulator rows with `simulation_year < decision_year`; normally N-1. |
| Lifecycle | Rebuilt before foundation/event generation for each year; reconstructible and non-authoritative. |

It replaces dynamic prior-snapshot relation discovery. It must never include current-year canonical state or current-year event facts.

## 7. Existing Domain-State Records

`int_enrollment_state_accumulator` and `int_deferral_rate_state_accumulator` remain authoritative and separate. Their keys and public behavior are unchanged. The enrollment decision projection also remains a disposable earlier-year view rather than authoritative state.

Relationships after normalization:

```text
workforce state -----+
enrollment state ----+--> contribution/core/match state --> workforce snapshot
deferral state ------+
published events ----+--> domain accumulators / audit facts
```

Benefit models may consume published event-window dates where required, but must not independently replay workforce status/compensation/proration state.

## 8. Workforce Snapshot

`fct_workforce_snapshot` retains its exact public schema, grain, types, nullability behavior, ordering semantics, and duplicate multiplicity. Its implementation changes from event replay to composition of:

- canonical workforce state;
- enrollment state;
- deferral state;
- employee contribution calculations;
- employer core calculations;
- employer match calculations/events.

It is published once per scenario/plan/year and is not a prior-year source for current-year candidates after migration.

## 9. Parity Exclusion Rule

Versioned entries in `contracts/parity-exclusions.yaml`.

| Field | Type | Rules |
|---|---|---|
| `relation` | dbt model name | Exact, no wildcard; unique with column. |
| `column` | column name | Exact, no wildcard/type rules. |
| `reason` | string | Must explain why a nondeterministic audit value is non-semantic. |

Unknown/duplicate relation-column pairs fail validation. If the relation is built, the column must exist. If the relation is explicitly not built in both DBs, its exclusion remains documented but unused. No entry permits a schema omission or an unlisted value difference.

## 10. Baseline Characterization

Checked-in aggregate JSON with a versioned typed schema.

Required groups:

- baseline ID, authoritative code revision, and dirty-tree fingerprint;
- canonical config fingerprint (normalizing machine-specific paths), census/seed hashes, sizes, and row counts;
- construction signature, DuckDB fingerprint, workload and year horizon;
- invocation schedule and per-node execution counts;
- exact mart schemas in ordinal order;
- for every mart selected by `dbt ls --select marts`: `compared` or `not_built_in_either` status, row counts, distinct-row counts, duplicate groups, and extra duplicate rows;
- event counts by exact `(scenario_id, plan_design_id, simulation_year, event_type)`;
- aggregate workforce transition counts;
- representative transition expectations only from checked-in synthetic fixtures.

Absolute paths, real employee rows, census contents, and the golden DB are prohibited.

## 11. Phase Gate Record

Ignored JSON at `var/state_pipeline_validation/<phase>/gate.json`.

Required identity: phase ID, baseline ID, candidate revision/dirty fingerprint, input fingerprints, timestamps, and tool versions.

Required results: schema/parity matrix, event counts, duplicate metrics, invariant suite outcomes, invocation/node counts, wall/CPU/model/RSS measurements, shared DB before/after signature, and pre-existing run artifact before/after signatures.

Valid phase IDs in order:

1. `baseline_characterization`
2. `run_database_isolation`
3. `event_publication`
4. `shadow_workforce`
5. `consumers_migrated`
6. `snapshot_composed_legacy_removed`
7. `state_stage_consolidated`

A phase passes only if every required semantic guard passes. The next phase must reject a failed/missing predecessor record or a different baseline ID.
