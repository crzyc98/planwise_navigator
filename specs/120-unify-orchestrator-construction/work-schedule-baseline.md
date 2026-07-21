# Authoritative product work-schedule baseline

## Evidence

Two isolated, five-year runs used the same 60,040-employee Studio census and
`--threads 1`. The reference run used `config/simulation_config.yaml`; the
Studio run used the exact scenario configuration at
`workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/scenarios/dc111f09-b27b-4406-8e6f-03eee015e123/config.yaml`.

| Configuration | Wall time | Peak RSS | Timed wrapper calls | Product schedule | Persisted terminal steps |
|---|---:|---:|---:|---:|---:|
| Reference | 134.1s | 1,313 MiB | 38 | 38 | 38 |
| Studio | 131.0s | 1,258 MiB | 38 | 38 | 38 |

Both runs emitted semantic signature
`1fae4ffd6bf74cd5d0b9f7afc503eddbedaaee6af9f294b7f657e027a06ac5bc`
with `entry_point=perf_harness`. Both campaigns verified that the shared
development database SHA-256 was unchanged.

## Canonical five-year schedule

The ordered command lists were byte-equivalent after excluding run-specific
paths. The 38 commands break down as follows:

| Scope | Commands |
|---|---:|
| First-year preparation (`seed`, staging, effective parameters, five hazard-cache builds) | 8 |
| 2025 workflow (initialization, foundation, event generation, three state-accumulation calls) | 6 |
| Each later year, 2026–2029 (initialization, foundation, event generation, three state-accumulation calls) | 6 × 4 |
| Total | 38 |

Each step records its one-based sequence, exact command/selector, workflow
stage, simulation year, and `runner_kind=dbt`. The complete ordered schedule is
also stored on each isolated run's append-only `run_execution_metadata` record.

## Reconciliation of 38 versus 62

The product recorder is installed at `DbtRunner.execute_command`, immediately
before command execution. Its 38-step terminal schedule exactly matches the
independent timing wrapper's 38 calls for both configurations. Therefore the
retained Studio log count of 62 was not a count of 62 separately issued dbt
commands on this canonical path; it counted log/subprocess-related records with
different semantics. It remains useful historical evidence but is not an
invocation baseline or an optimization gate.

The feature-enabled Studio configuration changes SQL work within selected
models, not the orchestration schedule. Further run-cost optimization should
use per-model execution timing inside this 38-command schedule.
