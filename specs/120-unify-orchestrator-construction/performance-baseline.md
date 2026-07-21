# Feature 120 Performance Baseline

## Pre-change measurement

- Date: 2026-07-20
- Campaign: `u120-prechange-100k-elevated`
- Construction path: production `OrchestratorWrapper`
- Configuration: Studio-realistic DC-plan configuration
- Census: deterministic exact-size 100,000-employee Parquet generated in `/tmp`
- Horizon: 2025–2029
- Threads: 1
- Repetitions: 3

| Repetition | Wall time (s) | Peak RSS (MiB) | Wrapped invocations | Completed |
|---:|---:|---:|---:|---|
| 1 | 141.03 | 1,611.72 | 38 | yes |
| 2 | 138.67 | 1,574.67 | 38 | yes |
| 3 | 139.02 | 1,536.75 | 38 | yes |
| **Median** | **139.02** | **1,574.67** | **38** | **yes** |

The raw, gitignored samples are under
`var/perf_profile/u120-prechange-100k-elevated/`.

## Regression limits

The post-change three-repetition medians must not exceed:

- Wall time: **152.92 seconds** (pre-change median +10%)
- Peak RSS: **1,732.14 MiB** (pre-change median +10%)

The wrapped invocation count is diagnostic rather than an acceptance threshold;
Feature 120 reconciles it with all dbt subprocess calls before issue #478 uses
the schedule as an optimization baseline.

## Shared development database guard

- SHA-256 before: `46ef47d6c8b46142d2cb0863d19ba8ba19e2bd6c3fcab2e846cbaacc4bfa5683`
- SHA-256 after: `46ef47d6c8b46142d2cb0863d19ba8ba19e2bd6c3fcab2e846cbaacc4bfa5683`
- Result: unchanged

## Post-change regression

- Campaign: `u120-postchange-100k`
- Configuration/census/horizon/threads: identical to the pre-change campaign

| Repetition | Wall time (s) | Peak RSS (MiB) | Timed calls | Product schedule | Completed |
|---:|---:|---:|---:|---:|---|
| 1 | 136.11 | 1,573.19 | 38 | 38 | yes |
| 2 | 137.70 | 1,552.22 | 38 | 38 | yes |
| 3 | 138.06 | 1,531.08 | 38 | 38 | yes |
| **Median** | **137.70** | **1,552.22** | **38** | **38** | **yes** |

Relative to the pre-change medians, wall time changed by **−0.95%** and peak
RSS by **−1.43%**. Both are below the allowed +10% limits. The campaign again
verified the shared development database SHA-256 was unchanged.
