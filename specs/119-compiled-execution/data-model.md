# Data Model: Compiled DAG Execution — #470 Hardening

Feature 119 adds runtime models and one internal append-only terminal metadata relation. It does not change public marts, event payloads, or simulation configuration beyond the existing engine selector. Normative interfaces are defined in `contracts/`.

## ExecutionEngine (configuration)

| Field | Type | Validation |
|---|---|---|
| `optimization.execution_engine` | `dbt \| compiled` | Pydantic enum; remains `dbt` until all gates pass |
| CLI override | `dbt \| compiled \| null` | When supplied, overrides config for that run only |

The engine selector is orchestration-only and remains excluded from result-affecting configuration fingerprints.

## RunArtifactWorkspace

| Field | Type | Validation |
|---|---|---|
| `run_id` | UUID string | Authoritative run ID when available; otherwise runner-local UUID |
| `root` | absolute `Path` | Must resolve under the configured runtime artifact root, never `dbt/target` |
| `database_path` | absolute `Path` | Must equal `db_manager.db_path`; cannot resolve to shared dev DB during validation |
| `profiles_dir` | `Path` | Contains generated explicit DuckDB profile |
| `staging_root` | `Path` | Unique mutable compile targets |
| `delegation_root` | `Path` | Unique mutable dbt delegation targets |
| `bundle_root` | `Path` | Published immutable bundles keyed by context digest |
| `log_root` | `Path` | Unique dbt logs per invocation |

**State transitions**: `CREATED → ACTIVE → CLOSED`; `ACTIVE → FAILED_RETAINED` when diagnostic artifacts are preserved. No dbt command may target `bundle_root`.

## StaticProjectContext

| Field | Type | Validation |
|---|---|---|
| `project_digest` | SHA-256 | Covers dbt project configuration, models, macros, selectors, package lock, and parse-relevant seeds/configuration |
| `dbt_version` | string | Exact installed version |
| `adapter_version` | string | Exact dbt DuckDB version |
| `adapter_type` | string | Must be `duckdb` for Feature 119 |
| `profile_digest` | SHA-256 | Secret-safe digest of selected explicit target settings |
| `manifest_digest` | SHA-256 | Hash of dbt-produced manifest bytes |

A parsed manifest may be reused only while every field matches.

## InvocationRequest

| Field | Type | Validation |
|---|---|---|
| `sequence` | non-negative integer | Unique and monotonic within a run |
| `command` | enum/string | `run` is eligible for direct execution; other valid commands may delegate |
| `select` | ordered list of strings | Preserves exact CLI token values |
| `exclude` | ordered list of strings | Preserves exact CLI token values |
| `options` | immutable map | Every option must be consumed or classified unsupported |
| `simulation_year` | integer or null | Required for supported simulation run invocations |
| `dbt_vars` | immutable canonical map | JSON-canonicalizable; includes effective simulation year |
| `stage` | string or null | Used for diagnostics and evidence |

## RelationState

| Field | Type | Validation |
|---|---|---|
| `database` / `schema` / `identifier` | strings | Derived only from manifest relation metadata |
| `relation_type` | `missing \| table \| view` | Read before transaction |
| `columns` | ordered list of `(name, type, nullable)` | Frozen during preflight |
| `state_digest` | SHA-256 | Canonical digest of the fields above |

## RenderContext

| Field | Type | Validation |
|---|---|---|
| `static_project_context` | `StaticProjectContext` | Must match current manifest |
| `database_path_digest` | SHA-256 | Derived from normalized absolute target path |
| `profile_target` / `schema` | strings | Must match workspace profile and manifest target |
| `command_semantics` | canonical structure | Command, selection, exclusion, full-refresh and render-affecting flags |
| `vars_digest` | SHA-256 | Canonical exact vars |
| `selected_unique_ids` | ordered tuple | dbt-resolved order |
| `relation_state_digest` | SHA-256 | Covers selected target relation states affecting render/materialization |
| `render_identity` | string | dbt volatile render identity used for this compilation |
| `context_digest` | SHA-256 | Digest of the complete canonical structure |

Raw sensitive values are not written to terminal provenance; only redacted metadata and digests are retained.

## CompiledBundle

| Field | Type | Validation |
|---|---|---|
| `context_digest` | SHA-256 | Directory key and identity |
| `manifest_path` / `manifest_digest` | relative path / SHA-256 | Must exist and match before publication/use |
| `nodes` | ordered tuple of `CompiledNode` | Exactly the dbt-selected executable/model resources |
| `project_hooks` | ordered tuple of `HookPlan` | Start/end lifecycle entries |
| `created_at` | timestamp | Artifact metadata only; excluded from semantic identity |
| `bundle_digest` | SHA-256 | Covers manifest, frozen metadata, and every compiled SQL hash |

**State transitions**: `STAGING → VALIDATED → PUBLISHED`; any validation failure becomes `REJECTED`. Published bundles are never mutated. An existing publication is accepted only after digest verification.

## CompiledNode

| Field | Type | Validation |
|---|---|---|
| `unique_id` / `name` | strings | From manifest |
| `relation` | typed relation | Database/schema/identifier from manifest |
| `resource_type` | enum | Supported direct path requires model or compile-time ephemeral dependency |
| `materialization` | enum | `view`, `table`, `incremental`, `ephemeral` supported initially |
| `incremental_strategy` | enum/null | `append` or `delete+insert` when incremental |
| `unique_key` | ordered tuple | Required where dbt semantics require it |
| `on_schema_change` | enum/null | Must be proven during preflight or delegate |
| `compiled_sql` | bytes/string | Loaded from published bundle, never mutable target |
| `sql_digest` | SHA-256 | Verified before plan publication |
| `pre_hooks` / `post_hooks` | ordered tuples | Frozen `HookPlan` values |
| `dependencies` | ordered tuple of IDs | Must be consistent with dbt graph order |

## HookPlan

| Field | Type | Validation |
|---|---|---|
| `scope` | `project_start \| node_pre \| node_post \| project_end` | Determines lifecycle order |
| `kind` | `connection_sql \| transactional_sql \| informational_log` | Only supported kinds enter a direct plan |
| `rendered_sql` | string or null | Null for informational logging |
| `message` | string or null | Bounded lifecycle message for informational logging |
| `source_digest` | SHA-256 | Detects hook mutation |

## InvocationPlan

| Field | Type | Validation |
|---|---|---|
| `request` | `InvocationRequest` | Fully consumed and canonicalized |
| `context_digest` / `bundle_digest` | SHA-256 values | Must match published bundle |
| `nodes` | ordered tuple of frozen node operations | Non-empty for direct success |
| `connection_hooks` | ordered tuple | Supported connection-local settings only |
| `transaction_operations` | ordered tuple | Complete executable sequence; no semantic discovery remains |
| `end_logs` | ordered tuple | Recorded only after successful commit |
| `target_database` | absolute path | Must equal runner/database-manager path |

The plan is frozen after preflight. A direct executor cannot add nodes, re-render hooks, or reload SQL.

## KnownUnsupportedSemantics

| Field | Type | Notes |
|---|---|---|
| `code` | stable enum | Examples: `command`, `option`, `selector_context`, `empty_selection`, `resource_type`, `materialization`, `incremental_strategy`, `hook`, `schema_change`, `full_refresh` |
| `phase` | `preflight \| execute` | `execute` is defensive and counts as unexpected |
| `detail` | bounded string | No SQL data or secrets |
| `affected_nodes` | ordered tuple | Empty if selection could not be established |

Only this typed result/exception authorizes dbt delegation. Generic exceptions never do.

## InvocationExecutionRecord

| Field | Type | Notes |
|---|---|---|
| `run_id`, `sequence`, `year`, `stage` | identity/context | Links to terminal run record |
| `mode` | `direct \| dbt_delegation` | No ambiguous fallback mode |
| `reason_code` | enum/null | Required for delegation |
| `context_digest`, `bundle_digest` | SHA-256/null | Present when planning reached that stage |
| `planned_nodes`, `attempted_nodes`, `completed_nodes` | ordered tuples | Supports partial-failure diagnosis |
| `target_database_digest` | SHA-256 | Confirms isolated target without exposing path in exported JSON |
| `started_at`, `finished_at`, `elapsed_seconds` | timing | Runtime evidence |
| `rollback_attempted`, `rollback_succeeded` | booleans | Required when execution fails after `BEGIN` |
| `outcome` | `success \| failed \| delegated` | Terminal per invocation |
| `error_context` | bounded structure/null | Error type, node, lifecycle phase, statement digest, resolution hint |

## RunExecutionMetadata (append-only internal relation)

One terminal row is appended for normal success or failure. The existing startup `run_metadata` row remains unchanged.

| Field | Type |
|---|---|
| `run_id` | VARCHAR |
| `recorded_at` | TIMESTAMP |
| `status` | VARCHAR |
| `execution_engine` | VARCHAR |
| `direct_invocation_count` | INTEGER |
| `delegated_invocation_count` | INTEGER |
| `unexpected_fallback_count` | INTEGER |
| `reason_counts_json` | VARCHAR |
| `render_context_digests_json` | VARCHAR |
| `parity_status` | VARCHAR (`not_run`, `identical`, `diverged`) |
| `peak_rss_mb` | DOUBLE/null |

The relation is internal provenance, not a public mart. Rows are inserted, never updated or deleted.

## ParityReport

| Field | Type | Validation |
|---|---|---|
| `input_fingerprint` | SHA-256 | Same config, census, seed, horizon for both engines |
| `baseline_database` / `candidate_database` | artifact identifiers | Both fresh and isolated |
| `tables` | tuple of `TableParity` | Authoritative tables only |
| `unexpected_fallback_count` | integer | Must be zero for `IDENTICAL` exit success |
| `verdict` | `IDENTICAL \| DIVERGED \| ERROR` | Derived, never caller supplied |

`TableParity` contains ordered schema comparisons, row counts, `a_only_all`, `b_only_all`, and bounded multiplicity diagnostics.

## GateEvidence

| Field | Type | Notes |
|---|---|---|
| `gate` | `tiny_parity \| determinism \| dev_60k_parity \| memory_100k \| performance \| zero_unexpected_fallbacks` | Ordered enum |
| `input_fingerprint` / `git_sha` / version tuple | identity | Prevents incomparable evidence |
| `status` | `pending \| passed \| failed` | Later gate cannot pass while an earlier one is not passed |
| `artifact_paths` | tuple | JSON/reports/databases under gitignored runtime roots |
| `metrics` | typed map | Counts, time, RSS, or fallback totals appropriate to gate |

## Relationships

```text
ExecutionEngine -> CompiledRunner -> RunArtifactWorkspace
RunArtifactWorkspace -> StaticProjectContext -> RenderContext
RenderContext -> CompiledBundle -> CompiledNode / HookPlan
InvocationRequest + CompiledBundle -> InvocationPlan
InvocationPlan -> InvocationExecutionRecord
KnownUnsupportedSemantics -> dbt delegation -> InvocationExecutionRecord
InvocationExecutionRecord* -> RunExecutionMetadata
two isolated runs -> ParityReport -> GateEvidence -> default eligibility
```
