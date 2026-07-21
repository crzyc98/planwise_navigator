# Contract: Construction Signature & Work Schedule

## Construction signature

Every constructed run emits a `ConstructionSignature` (data-model §4). It is the comparable proof of identical construction across entry points.

**Fields**: `entry_point`, `runner_kind`, `database_path`, `dbt_project_dir`, `thread_count`, `initialization_policy`, `installed_hook_names`, `execution_engine`, `signature_hash`.

**Rules (MUST)**:
- `signature_hash` is a stable hash over all fields **except** `entry_point` and the run-specific `database_path` (paths differ per isolated run; the *policy* not the literal path is what must match). The hash covers: `runner_kind`, `dbt_project_dir` relationship (shared vs overlay), `thread_count`, `initialization_policy`, `installed_hook_names` (order-normalized), `execution_engine`.
- For a fixed validated config, `signature_hash` is byte-identical across `cli.simulate`, `batch`, `studio`, `parity`, `invariant_test`, `perf_harness` (SC-002).
- The signal shares its shape with the `#455` harness `construction` field so the harness reports the same signature as the product.

**Run-start persistence**: record `construction_signature_hash`, `initialization_policy`, `entry_point`, and `runner_kind` on the existing `run_metadata` row. These values are known before execution. Schema evolution MUST be idempotent for databases carrying the old row shape and MUST fail loudly if required provenance columns cannot be added.

## Work schedule

Each run records its ordered `WorkSchedule` (data-model §6): the sequence of dbt invocations (command/selector, stage, year).

**Rules (MUST)**:
- Retrievable in-process and persisted at run completion in an append-only terminal execution record containing `invocation_count` and the complete ordered step list.
- The production-path integration test (FR-014) asserts the captured schedule matches the observed canonical schedule for the reference configuration. No invocation count is an acceptance threshold until capture reconciles wrapped-runner calls with all dbt subprocess calls.
- Provides the measured baseline #478 will reduce.

## Acceptance checks

1. Construct the same config via two entry points into isolated DBs → equal `signature_hash`.
2. Read a completed run's provenance → start signature on `run_metadata`; finalized count and ordered schedule on its terminal execution record.
3. Harness-reported signature == product signature for the same config.
4. Open a database with the pre-feature `run_metadata` schema → idempotent evolution succeeds and both new record types remain queryable.
