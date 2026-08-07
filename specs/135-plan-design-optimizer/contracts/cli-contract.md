# Contract: `planalign optimize` CLI Command

Mirrors the existing `planalign fit`/`planalign backtest` command shape (a spec/data path plus a small set of explicit flags), added as `planalign_cli/commands/optimize.py`.

## Invocation

```bash
planalign optimize <spec.yaml> --max-runs N [OPTIONS]
```

| Argument/Flag | Required | Type | Notes |
|---|---|---|---|
| `<spec.yaml>` | Yes | path | The design-space + objective/constraint spec file (contracts/spec-schema.md). |
| `--max-runs N` | **Yes — no default** | int, ≥1 | Mandatory hard cap on evaluated candidates (FR-005; spec Clarifications: the command refuses to start without it). |
| `--seed N` | No | int | Search-path seed (FR-010). Defaults to a randomly chosen value that is echoed back so the run remains reproducible by re-supplying it. |
| `--baseline PATH` | No | path | Overrides the `baseline.config_path` in the spec file, matching the override precedence convention `planalign simulate --config` already uses. |
| `--database PATH` | No | path | Where per-candidate isolated `.duckdb` files are written; defaults to a fresh timestamped directory under `var/optimizer_runs/`, following `planalign batch`/ensemble conventions — **never** `dbt/simulation.duckdb`. |
| `--output PATH` | No | path | Export directory for the candidate table / report / frontier; defaults alongside `--database`. |
| `--parallel N` | No | int | Passed straight through to `resolve_worker_count` (same semantics as `planalign batch --parallel`). |
| `--dry-run` | No | flag | Validates the spec and prints the planned initial candidate set without evaluating anything — no scenario run, no budget consumed. |

## Behavior contract

1. **Validate before running anything** (FR-003, FR-004): spec parse/validation failures exit non-zero with the specific bad lever/metric named, before any `ScenarioJob` is submitted.
2. **Budget is authoritative** (FR-005, SC-004): the run never submits more than `--max-runs` distinct, non-duplicate candidates. Duplicate-reuse (FR-012) and failed candidates (FR-016) both interact with this count per data-model.md's `Candidate.is_duplicate_of`/`status` semantics — duplicates do not consume budget, failures do.
3. **Always terminates with a report** (FR-011): even a budget-exhausted, zero-feasible-candidate run prints a result — best-found-so-far, or the named binding constraint(s) when nothing is feasible (SC-006) — never a bare error with no summary.
4. **Console summary** (mirrors `planalign_ensemble` CLI conventions from `docs/guides/seed_ensembles.md`): resolved worker budget, run count executed vs. budget, and — for two-objective specs — the Pareto-frontier candidate count, printed before detailed export.
5. **Exit codes**: `0` success (regardless of whether any candidate was feasible — "zero feasible" is a valid, correctly reported outcome, not a command failure); non-zero only for spec validation failure, missing mandatory `--max-runs`, or an environment-level failure (e.g. no baseline DB reachable) — matching `planalign calibrate`'s fail-fast guard convention for a missing prerequisite.
6. **Every invocation is isolated** (FR-006): `--database` is always a fresh or explicitly isolated directory; the command must refuse (or clearly warn, matching `planalign batch`'s `--clean` semantics) rather than silently reuse another run's per-candidate databases.

## Output contract (files written)

```text
<--output>/
├── spec.yaml               # copy of the resolved input spec (baseline override applied)
├── candidates.csv          # every evaluated candidate — see data-model.md Candidate
├── report.md               # human-readable summary: ranking, frontier, binding constraints
├── optimizer_results.xlsx  # candidate table (+ Pareto sheet when applicable) — FR-013
└── candidates/
    ├── candidate-0000/scenario.duckdb
    ├── candidate-0001/scenario.duckdb
    └── ...                 # one retained .duckdb per non-duplicate candidate — FR-014
```
