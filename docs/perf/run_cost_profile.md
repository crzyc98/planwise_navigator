# Run-Cost Profile: dbt Orchestration Overhead vs DuckDB Compute

_Feature 116 (issue #455). Gates roadmap issue #456._

## 1. Decision criteria

Confirmed criteria (spec FR-007, Session 2026-07-17), stated before any result:

- **GO** if orchestration overhead >= 60% of wall time AND the direct-execution
  probe demonstrates >= 3x on its stage.
- **NO-GO** (redirect to computation-level optimization) if overhead <= 40%.
- Between 40-60%, the recommendation must weigh the probe result and say
  which way and why (judgment band).

The overhead share is evaluated at the **large client-representative census**
(the size roadmap workloads will actually run); shares at other sizes are
context. If the recommendation differs by census size, this report says so
explicitly and recommends per scale. Deviating from these thresholds requires
written justification in this report.

## 2. Environment

- Machine: arm64 cpus=12
- OS: macOS-26.5.2-arm64-arm-64bit
- Python 3.12.11, dbt-core 1.8.8, dbt-duckdb 1.8.1, duckdb 1.0.0
- Git SHA: a67429fdd1492cc27df501a2be37ad739f4f4652
- Projections transfer to other hardware only directionally (the decision metric is a ratio).

## 3. Wall-time by census size

| Size | Employees | Warm reps | Min | Median | Max |
|---|---|---|---|---|---|
| tiny | 150 | 3 | 85.4s | 86.9s | 87.1s |
| dev | 7,505 | 3 | 98.5s | 98.5s | 99.5s |
| large | 60,040 | 3 | 558.3s | 559.9s | 560.3s |

## 4. Decomposition (medians per size)

| Size | Total | Computation (model execute) | Overhead (per-invocation) | Residue (orchestrator) |
|---|---|---|---|---|
| tiny | 86.9s | 5.5s (6%) | 71.9s (83%) | 9.4s (11%) |
| dev | 98.5s | 16.9s (17%) | 73.0s (74%) | 8.8s (9%) |
| large | 559.9s | 471.9s (84%) | 78.4s (14%) | 9.2s (2%) |

FR-003 unattributed residue per size: 'tiny' 10.9% — over the 10% target; 'dev' 8.9%; 'large' 1.6%.
The residue is a near-constant ~9s of orchestrator Python (registries, enrollment projection, validation queries) per run; where it exceeds 10% that is the small total, not unexplained growth, and the decision-size residue is well under target.

## 5. Overhead share vs census size (decision table)

| Size | Employees | Overhead share of wall time |
|---|---|---|
| tiny | 150 | 83% |
| dev | 7,505 | 74% |
| large | 60,040 | 14% **<- decision row** |

## 6. Fixed-cost cross-check (FR-004)

- Minimal invocation (`dbt run --select stg_config_age_bands`, model execute subtracted): median floor **1.8s** over 5 reps (walls: 4.1s, 1.8s, 1.8s, 1.8s, 1.8s)
- Invocations per simulated year (median across samples): **9**
- Estimated fixed overhead per year: 1.8s x 9 = **16.0s/year**
- Measured overhead per year at 'large': **26.1s/year** -> ratio 1.63x (consistent)

## 7. Direct-execution probe (EVENT_GENERATION)

- Stage `event_generation`, year 2025, census 'dev', 16 nodes
- Standard path (dbt subprocesses): **2.7s**
- Direct path (same executed SQL via duckdb client): **0.2s**
- Speedup: **11.5x**
- Result equivalence: **EQUIVALENT**
- Method: per-table row count + order-insensitive row-hash checksum over all non-TIMESTAMP columns (TIMESTAMP columns are execution-time audit stamps like `created_at`; behavioral dates are DATE-typed and are included).

## 8. Projection

At 'large' (median run 559.9s): eliminating the per-invocation overhead entirely projects **1.2x**; eliminating 70% of it projects **1.1x**.

Assumptions:
- Compiled execution removes dbt subprocess startup/parse/compile per invocation but not model execute time or orchestrator Python (residue).
- The conservative bound keeps 30% of measured overhead for per-year compile/var substitution the compiled path still pays.
- Extrapolation from the probe stage to the full run assumes overhead is proportional to invocation count, not census size.

Top computation hotspots at the decision size (execute time summed over the full multi-year run; median across reps):

1. `model.fidelity_planalign_engine.fct_yearly_events` — 462.0s
2. `model.fidelity_planalign_engine.fct_workforce_snapshot` — 1.6s
3. `model.fidelity_planalign_engine.int_deferral_rate_state_accumulator` — 0.7s

## 9. Recommendation

**NO-GO**

- Overhead share 14% <= 40% at 'large': computation dominates; redirect to computation-level optimization.
- PER-SCALE DIVERGENCE: the verdict differs by census size. At 'dev' (74%), 'tiny' (83%) the overhead share meets the GO threshold and the probe gate holds — for workloads at those population sizes (small/sampled censuses, smoke sims), a compiled execution mode WOULD deliver a multiple-x win. The NO-GO above applies to client-representative scale, where SQL computation is the budget.

## 10. Reproduction

```bash
python -m scripts.perf_profile.make_large_census --factor 8
python -m scripts.perf_profile.run_matrix --sizes tiny,dev,large --reps 3 --measure-floor
python -m scripts.perf_profile.probe_direct_execution --year 2025
python -m scripts.perf_profile.build_report
```

Campaign: started 2026-07-17T21:48:29.729789+00:00, finished 2026-07-17T22:44:48.615149+00:00; shared dev DB unchanged: **True** (SC-007).

Samples consumed: dev-0.json, dev-1.json, dev-2.json, dev-3.json, large-0.json, large-1.json, large-2.json, large-3.json, tiny-0.json, tiny-1.json, tiny-2.json, tiny-3.json.
