# Implementation Plan: Unify Orchestrator Construction Across Entry Points

**Branch**: `120-unify-orchestrator-construction` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/120-unify-orchestrator-construction/spec.md`

## Summary

Collapse the 3+ divergent orchestrator-construction paths (`OrchestratorWrapper` used by `planalign simulate`; `factory.create_orchestrator`/`OrchestratorBuilder` used by batch and the profiling harness — with an implicit self-healing initializer; and the direct `PipelineOrchestrator(...)` in `planalign_orchestrator/cli.py`) into **one canonical builder** in `planalign_orchestrator`. The canonical builder encodes the current production (`OrchestratorWrapper`) behavior — forces SQL event generation, validates threading/eligibility, wires `DbtRunner`/`RegistryManager`/`DataValidator`, honors an isolated database + scenario project overlay — and exposes a typed **initialization policy** (default: no implicit self-healing) and an observable **construction signature**. Every entry point (CLI, batch, Studio-via-CLI, parity tooling, invariant tests, perf harness) delegates to it. The self-healing initializer becomes an explicit opt-in with a **fail-loud** contract (resolving #467, whose root cause is `HookManager.execute_hooks` swallowing the init hook's `InitializationError`). Construction signature + executed work schedule are recorded via the existing `run_metadata` provenance table. No dbt/SQL model changes; behavioral outputs stay byte-identical.

## Technical Context

**Language/Version**: Python 3.11 (orchestrator, CLI, API). No SQL/dbt model changes.
**Primary Dependencies**: Pydantic v2 (typed construction spec + config validation); existing `planalign_orchestrator` internals — `DbtRunner`, `PipelineOrchestrator`, `RegistryManager`, `DataValidator`, `HookManager`, `AutoInitializer`, `DatabaseConnectionManager`, `run_metadata`; Typer/Rich (CLI); the existing FastAPI Studio subprocess launcher gains only a trusted origin marker.
**Storage**: DuckDB. **No new fct/int tables.** The construction **signature** is recorded at run start on the existing `run_metadata` provenance row; the **executed** work schedule + final invocation count extend Feature 119's append-only `run_execution_metadata` terminal record. Both tables use idempotent schema evolution (`ADD COLUMN IF NOT EXISTS`) so pre-existing scenario databases upgrade in place without losing Feature 119 fields or historical rows. All validation runs in isolated per-run DBs; the shared `dbt/simulation.duckdb` is refused only by an explicit **validation-mode guard**, never unconditionally (normal dev runs legitimately target it).
**Testing**: pytest (`-m fast` unit; integration for cross-entry-point equivalence); the corrected #455 wrapper harness + `planalign parity`-style `EXCEPT ALL` multiset comparison for byte-identical equivalence across entry points.
**Target Platform**: macOS/Linux dev + on-prem analytics servers (work-laptop constraints).
**Project Type**: Single Python monorepo (orchestrator + cli + api + studio + dbt) — Option 1 (single project).
**Performance Goals**: No regression; the construction/telemetry changes are behavior- and cost-neutral by design. Baselines are **provisional** — the corrected #455 wrapper campaign measured ~132s / 38 *wrapped* invocations at 60,040/5yr, while a retained Studio dbt log showed ~174s / 62 *subprocess* invocations; the authoritative production schedule is established by the US2 work-schedule capture (which reconciles 38 vs 62), not asserted as a gate here. A dedicated **100K-employee** isolated regression validates completion + peak RSS at `--threads 1` (constitution VI).
**Constraints**: Single-threaded default preserved; 100K+ employee capacity unaffected (construction-only change); byte-identical authoritative outputs (events + snapshots, incl. behavioral dates); shared dev DB byte-identical during validation.
**Scale/Scope**: All product/tooling construction call sites plus every test-discovered direct construction site; completion is determined by a repository-wide zero-match audit rather than a fixed file-count estimate. One new canonical builder module remains <600 lines and exposes no more than eight public methods.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Event Sourcing & Immutability** | ✅ Construction-only change; FR-004/SC-003 require byte-identical `fct_yearly_events`/`fct_workforce_snapshot` across entry points. Reproducibility (same seed+config) is strengthened, not weakened. |
| **II. Modular Architecture** | ✅ New canonical builder is a single-responsibility module kept <600 lines / ≤8 public methods; the change **removes** duplicate construction, reducing divergence. Dependency direction stays correct (CLI/API/harness → orchestrator; never reverse). No new circular deps. |
| **III. Test-First Development** | ✅ Plan sequences tests before implementation: cross-entry-point parity test, construction-signature test, fail-loud init-contract test, engine-option validation test — all before/with the migration. Fast suite stays <10s; parity/integration run in isolated DBs. |
| **IV. Enterprise Transparency** | ✅ **Advances it** — construction signature + executed work schedule become observable in run provenance with context; init failures gain a correlation-carrying, fail-loud contract. |
| **V. Type-Safe Configuration** | ✅ **Config-facing models MUST use Pydantic v2** (the `ExecutionEngineOption` validation and any config additions); initialization policy is an explicit enum; unsupported `execution_engine` values are rejected at Pydantic/CLI validation (FR-008). Internal, non-configuration observability values (`ConstructionSignature`, `WorkSchedule`) may be plain dataclasses — they are not configuration. |
| **VI. Performance & Scalability** | ✅ No regression permitted; single-threaded default preserved; **a dedicated 100K-employee isolated regression task validates completion + peak RSS** (not just asserted); self-healing removal drops redundant fresh-DB work rather than adding any. |

**Result: PASS — no violations.** Complexity Tracking table intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/120-unify-orchestrator-construction/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal interface + observable-signature contracts)
│   ├── canonical-construction-seam.md
│   ├── construction-signature.md
│   ├── initialization-contract.md
│   └── execution-engine-option.md
├── checklists/
│   └── requirements.md  # from /speckit.specify
└── tasks.md             # /speckit.tasks output (NOT created here)
```

### Source Code (repository root)

```text
planalign_orchestrator/
├── construction/                 # NEW: the one canonical seam
│   ├── builder.py                #   canonical builder: config → PipelineOrchestrator (+ signature)
│   ├── spec.py                   #   typed ConstructionSpec + InitializationPolicy enum
│   └── signature.py              #   ConstructionSignature + WorkSchedule capture
├── factory.py                    # BECOMES thin adapter over construction/ (or deprecated shim)
├── scenario_batch_runner.py      # MIGRATE: build via canonical seam (explicit init policy)
├── cli.py                        # MIGRATE/REMOVE: legacy direct PipelineOrchestrator(...)
├── pipeline/hooks.py             # init hook path made fail-loud (critical hooks re-raise) — #467
├── self_healing/auto_initializer.py  # kept; invoked only via explicit opt-in policy
└── run_metadata.py               # EXTEND: persist construction signature + work schedule

planalign_cli/
├── integration/orchestrator_wrapper.py  # BECOMES thin adapter over canonical seam
└── commands/simulate.py                 # unchanged call shape; reaches canonical seam

planalign_api/services/simulation/service.py  # PROPAGATE: trusted Studio-origin marker to CLI subprocess

scripts/perf_profile/
├── run_matrix.py                 # MIGRATE: build via canonical seam; report canonical signature
└── build_production_report.py    # signature source becomes the product signature

tests/
├── integration/                  # NEW: cross-entry-point equivalence + signature + init-contract
└── unit/…                        # MIGRATE 12 files to construct via canonical seam + overrides
```

**Structure Decision**: Single project (Option 1). The canonical seam lives in `planalign_orchestrator/construction/` so every downstream package (`planalign_cli`, `planalign_api` via subprocess, `scripts/perf_profile`, `tests`) can depend on it without inverting the dependency graph. `OrchestratorWrapper` and `factory.create_orchestrator` are reduced to thin adapters (preserving their public call sites) so migration is incremental and each step stays independently reviewable and parity-verified.

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
