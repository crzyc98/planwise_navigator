# Corrected Production-Path Run-Cost Profile

_Issue #455 rework. Supersedes the factory-path baseline in [`run_cost_profile.md`](run_cost_profile.md) for the accepted run-cost number; that report remains the historical record of the compiled-engine (#456, now closed) GO/NO-GO measurement._

## What changed and why

The original Feature 116 campaign built the orchestrator through `planalign_orchestrator.create_orchestrator` (the **factory** seam). No real user reaches that seam: `planalign simulate` and Studio (via a CLI subprocess) build through `OrchestratorWrapper` (the **wrapper** seam). This report re-measures the accepted baseline through the wrapper seam, on both the minimal **reference** config and the Studio-realistic DC-plan config, and reconciles wrapper vs factory on an identical workload.

## Environment

- Machine: arm64 cpus=12
- OS: macOS-26.5.2-arm64-arm-64bit
- Python 3.12.11, dbt-core 1.8.8, dbt-duckdb 1.8.1, duckdb 1.0.0
- Git SHA: 3d169cc3a002dfd8f5d22f4923467faf917982b8
- Single unshared dev laptop; wall times carry run-to-run variance. The decision signals here are ratios and per-model shares, not absolute seconds.

## Method

- Census: 60,040 employees (Studio workspace census).
- Horizon: 2025–2029 (5 years), seed 42, target growth 3% — identical across configs.
- Seam: `OrchestratorWrapper.create_orchestrator` (real product construction), shared `dbt/` project dir (no `--dbt-project-dir`), as a bare-CLI run does.
- Each run in a fresh, isolated DuckDB under `var/perf_profile/<campaign>/db/` (never the shared dev DB).
- Decomposition per FR-003: **computation** = summed dbt model execute time (`run_results.json`); **overhead** = per-invocation wall not attributable to model execute (subprocess startup / parse / Jinja compile); **residue** = wall outside dbt invocations (orchestrator Python).

## 1. Accepted production-path baseline (wrapper seam)

Warm-rep medians (a cold rep 0 is discarded):

| Config | Warm reps | Events | Invocations | Wall median (min–max) | CPU | Peak RSS |
|---|---|---:|---:|---|---:|---:|
| reference | 3 | 759,974 | 38 | 132.1s (131.8s–135.0s) | 155.7s | 1296 MiB |
| studio | 3 | 645,130 | 38 | 132.0s (130.7s–133.7s) | 151.7s | 1284 MiB |

## 2. Where the time goes (decomposition, warm medians)

| Config | Total | Computation (model execute) | Overhead (per-invocation) | Residue (orchestrator) |
|---|---|---|---|---|
| reference | 132.1s | 21.2s (16%) | 98.2s (74%) | 13.0s (10%) |
| studio | 132.0s | 20.2s (15%) | 97.4s (74%) | 13.4s (10%) |

## 3. Second-bottleneck hunt: per-model execute time

Model execute time summed over the full multi-year run (median across warm reps) — the same `run_results.json` attribution that found the #465 `fct_yearly_events` quadratic. If a DC-plan model specific to the Studio feature set were a hidden second bottleneck, it would dominate this ranking for the studio config.

### reference config — top 12 models (computation total 21.2s)

| # | Model | Execute (summed) | Share of computation |
|---|---|---:|---:|
| 1 | `fct_yearly_events` | 5.1s | 24% |
| 2 | `fct_workforce_snapshot` | 2.8s | 13% |
| 3 | `int_deferral_rate_state_accumulator` | 1.3s | 6% |
| 4 | `int_employee_contributions` | 1.2s | 5% |
| 5 | `fct_employer_match_events` | 1.0s | 4% |
| 6 | `int_employee_state_by_year` | 0.9s | 4% |
| 7 | `int_deferral_escalation_state_accumulator` | 0.7s | 3% |
| 8 | `int_enrollment_events` | 0.6s | 3% |
| 9 | `int_employee_compensation_by_year` | 0.6s | 3% |
| 10 | `int_enrollment_state_accumulator` | 0.6s | 3% |
| 11 | `int_workforce_snapshot_optimized` | 0.6s | 3% |
| 12 | `int_workforce_needs_by_level` | 0.5s | 2% |

### studio config — top 12 models (computation total 20.2s)

| # | Model | Execute (summed) | Share of computation |
|---|---|---:|---:|
| 1 | `fct_yearly_events` | 4.4s | 22% |
| 2 | `fct_workforce_snapshot` | 2.8s | 14% |
| 3 | `int_deferral_rate_state_accumulator` | 1.2s | 6% |
| 4 | `int_employee_contributions` | 1.1s | 6% |
| 5 | `fct_employer_match_events` | 0.9s | 5% |
| 6 | `int_employee_state_by_year` | 0.8s | 4% |
| 7 | `int_deferral_escalation_state_accumulator` | 0.7s | 3% |
| 8 | `int_enrollment_events` | 0.6s | 3% |
| 9 | `int_employee_compensation_by_year` | 0.6s | 3% |
| 10 | `int_enrollment_state_accumulator` | 0.6s | 3% |
| 11 | `int_workforce_snapshot_optimized` | 0.6s | 3% |
| 12 | `int_workforce_needs_by_level` | 0.5s | 2% |

## 3a. Second-bottleneck verdict

**No second bottleneck.** The studio config's largest single model is `fct_yearly_events` at 4.4s (22% of 20.2s total computation) — no DC-plan model exhibits the runaway single-model cost that `fct_yearly_events` did before #466. Total model-execute computation is a small fraction of wall time (Section 2); the remaining wall time is per-invocation tooling overhead and orchestrator residue, which are invocation-count-driven and shared by every config — addressed by invocation consolidation (#478), not by a DC-plan SQL fix.

Reference vs studio computation: 21.2s vs 20.2s. Any wall-time gap between the two configs at this census is dominated by variance and invocation/overhead differences, not by DC-plan model execute time.

## 4. Reconciliation: wrapper vs factory (reference config)

| Metric | wrapper (product) | factory (historical) | delta |
|---|---:|---:|---:|
| Invocations | 38 | 40 | +2 |
| Wall median | 132.1s | 140.8s | +8.7s |
| Overhead | 98.2s | 105.9s | +7.6s |
| Computation | 21.2s | 21.5s | +0.3s |

The factory seam runs **2 more dbt invocation(s)** than the product path over this horizon (its self-healing `AutoInitializer` re-seeds / rebuilds staging that the wrapper path never does — the dead-code half of #468). The historical factory-path overhead is therefore modestly **inflated** relative to the real product path: the corrected wrapper numbers above are the accepted baseline.

## 4a. Reconciliation with the historical factory-path report (the #466 effect)

The historical report's client-scale decision row (60,040 employees, 3-year, **factory** seam, **pre-#466**) read 559.9s wall with overhead only **14%** — computation dominated, which drove its NO-GO-at-scale conclusion. This corrected baseline reads overhead **74%**. The two are not in conflict; **#466 moved the line**:

- Pre-#466, `fct_yearly_events` alone was ~462s of model-execute time (its `delete+insert` unique_key was constant within a run, so dbt-duckdb rendered an O(events²) delete-by-join). That quadratic **computation** dwarfed the fixed tooling overhead, pinning the overhead share near 14%.
- Post-#466, that node is ~5s (Section 3) and total computation is ~21.2s. The fixed per-invocation overhead did not change — it is **2.6s/invocation** here vs ~2.8s/invocation implied by the historical numbers — but with the quadratic computation gone, that same overhead now **dominates** the run (74%), even at client scale.

So both reports measured the same fixed tooling cost; they disagree on the *share* only because #466 removed the computation that used to hide it. The practical consequence supersedes the historical roadmap note: the post-#466 run is overhead-dominated at every census size, but the compiled-execution engine (#476) already demonstrated it cannot beat post-#466 dbt (0.93x at 60K), so the live lever is **per-run invocation consolidation (#478)** — cutting the 38-invocation schedule — not SQL optimization and not a replacement engine.

## 5. Fixed-cost cross-check (FR-004)

- Minimal invocation (`dbt run --select stg_config_age_bands`, model execute subtracted): median floor **1.8s** over 5 reps.
- Invocations per simulated year (median): **8**.
- Estimated fixed per-invocation overhead per year: 1.8s x 8 = **14.6s/year** — consistent with the ~75s/run fixed dbt tooling cost the original profile identified. This is the real, removable cost; it is invocation-count-driven, not census-driven.

## 6. Appendix: DC-plan config delta (reference vs studio)

Both configs share census, seed, growth target, and horizon — the only differences are DC-plan features. Contrary to the initial assumption that Studio runs a *fuller* DC-plan feature set, the Studio scenario is **simpler** on the DC dimensions:

| DC-plan feature | reference | studio |
|---|---|---|
| auto-escalation (`deferral_auto_escalation.enabled`) | `True` | `None` |
| match-response modeling (`deferral_match_response.enabled`) | `True` | `False` |
| match eligibility gating (`employer_match.apply_eligibility`) | `True` | `False` |
| employer_match formulas defined | 6 | 1 |
| core contribution shape | graded schedule | flat |

So the studio config's wall time is not explained by richer DC-plan computation. Section 3's per-model ranking is the authoritative account of where its time actually goes.

## 7. Reproduction & provenance

```bash
python -m scripts.perf_profile.run_matrix --campaign-id prod-455 --construction wrapper --config config/simulation_config.yaml --config-label reference --census workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet --horizon 2025-2029 --reps 3 --measure-floor
python -m scripts.perf_profile.run_matrix --campaign-id prod-455 --construction wrapper --config <studio scenario config.yaml> --config-label studio --census workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet --horizon 2025-2029 --reps 3
python -m scripts.perf_profile.run_matrix --campaign-id prod-455 --construction factory --config config/simulation_config.yaml --config-label reference --census workspaces/1497b19c-b212-4c67-82d3-bc0455b637e0/data/census.parquet --horizon 2025-2029 --reps 3 --skip-cold
python -m scripts.perf_profile.build_production_report --campaign-id prod-455
```

Campaign `prod-455`: started 2026-07-20T17:29:48.072525+00:00, finished 2026-07-20T17:54:39.826986+00:00; shared dev DB unchanged: **True** (SC-007).

Warm samples consumed: reference-factory-custom-1.json, reference-factory-custom-2.json, reference-factory-custom-3.json, reference-wrapper-custom-1.json, reference-wrapper-custom-2.json, reference-wrapper-custom-3.json, studio-wrapper-custom-1.json, studio-wrapper-custom-2.json, studio-wrapper-custom-3.json.
