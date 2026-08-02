# Step 00 — pre-change baseline

## Workload

- Census: 60,040 rows, SHA-256
  `285fbfe1b476cae634a3960c865c1891d2c155e691744fdf7ee192eba193c2a4`
- Horizon: 2025–2029
- Construction: production `wrapper` seam
- dbt threads: 1
- Databases: three fresh isolated files under
  `var/perf_profile/f132-baseline/db/`
- Shared development database: SHA-256 unchanged

## Samples

| Repetition | Commands | Wall (s) | Startup (s) | Execution (s) | Orchestration (s) |
|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 105.033 | 67.782 | 18.828 | 18.423 |
| 2 | 20 | 103.498 | 66.752 | 18.425 | 18.321 |
| 3 | 20 | 103.576 | 66.845 | 18.409 | 18.322 |
| **Median** | **20** | **103.576** | **66.845** | **18.425** | **18.322** |

Startup is dbt invocation wall time minus summed model execution time.
Orchestration is total wall time minus dbt invocation wall time. Component
medians are calculated independently, so rounding does not necessarily sum to
the wall-time median.

## Baseline reconciliation

- Command shape: **PASS** — all three runs recorded 20 commands.
- Workload shape: **PASS** — all runs used 60,040 rows and five years.
- Starting wall time: **PASS** — the measured 103.576s median corroborates the
  102.720s median across 18 prior 20-command runs.

The originating issue's 91.5s figure is rejected: no recorded 20-command run
approaches it (the fastest is 97.138s), and its named components sum to 87.0s.
Historical 38 → 30 and 30 → 20 command reductions value a removed command at
1.46–1.75s, so Story 1's bar is 3s and Story 2's bar is 6s.
