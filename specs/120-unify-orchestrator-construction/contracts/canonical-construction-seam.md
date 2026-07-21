# Contract: Canonical Construction Seam

The single public interface every entry point uses to construct a run. Internal library contract (this is a CLI/library feature, not a network API).

## Interface

```
build_orchestrator(spec: ConstructionSpec) -> ConstructionResult
```

- **Input**: a Pydantic-v2 `ConstructionSpec` (see data-model §1) carrying a *validated* `SimulationConfig`, an isolated database, thread policy, optional dbt project overlay, an `InitializationPolicy`, a Pydantic-v2-validated `ExecutionEngineOption`, an `entry_point`, a `validation_mode` flag, and testability overrides (injected runner / db manager / extra validation rules). Configuration-facing values use Pydantic v2 (constitution V); internal observability values may be dataclasses.
- **Output**: a `ConstructionResult` = the wired `PipelineOrchestrator` **plus** its `ConstructionSignature` (data-model §4).

## Guarantees (MUST)

1. **Determinism of construction**: for two `ConstructionSpec`s with the same validated config + database + threads + project dir + initialization + engine, the resulting `ConstructionSignature.signature_hash` is identical (FR-003, SC-002).
2. **Production-equivalence**: the default spec (initialization `NONE`, standard engine) reproduces exactly the orchestrator `OrchestratorWrapper.create_orchestrator` builds today — same `DbtRunner` wiring (`db_manager`, `database_path`, `project_dir`, threading), forced `event_generation.mode="sql"`, same threading/eligibility validations, same registries + validator rules (FR-001, FR-004).
3. **Isolation preserved**: honors the provided database and dbt project overlay. The shared dev DB (`dbt/simulation.duckdb`) is refused **only when the spec sets `validation_mode=True`** — never unconditionally, since normal dev/production runs legitimately target it (FR-011, FR-012).
4. **No hidden work**: installs no self-healing initializer unless `initialization == SELF_HEALING`; installs no engine other than the resolved `ExecutionEngineOption`.
5. **Observability**: emits the `ConstructionSignature` and makes it retrievable in-process (for harness/parity) and persistable (run_metadata) (FR-005).
6. **Testability**: accepts injected overrides (mock runner, in-memory db, extra rules) so tests use the seam rather than reproducing construction (FR-002 test-adapter clause).

## Caller adapters (MUST all delegate here)

| Caller | Delegation |
|---|---|
| `OrchestratorWrapper.create_orchestrator` | thin adapter → `build_orchestrator` (initialization `NONE`) |
| `scenario_batch_runner` | → `build_orchestrator` (initialization `NONE`; repair canonical fresh-DB setup if parity exposes a gap) |
| `factory.create_orchestrator` | thin adapter → `build_orchestrator` (initialization `SELF_HEALING`, fail-loud) — retained for migration, removed when unused |
| `planalign_orchestrator/cli.py` | migrate to `build_orchestrator` or delete if unused |
| `scripts/perf_profile/*` | → `build_orchestrator`; report the emitted signature |
| tests (all sites found by repository audit) | → `build_orchestrator` with injected overrides |

## Non-goals

- No change to `execute_multi_year_simulation` semantics.
- No dbt/SQL model changes.
- No in-process execution model for Studio (it stays a `planalign simulate` subprocess); the API propagates only a trusted Studio-origin marker for provenance.
