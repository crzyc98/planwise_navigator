# All-marts parity gate

- Result: **PASS**
- Mart set source: `dbt ls --select marts --resource-type model --output name`
- Enumerated marts: 9
- Census rows: 60,040
- Horizon: 5 years
- Excluded tables: `run_metadata`, `run_execution_metadata`

| Mart | Baseline − candidate | Candidate − baseline | Candidate − rerun | Rerun − candidate | Excluded columns |
|---|---:|---:|---:|---:|---|
| `dim_hazard_table` | absent | absent | absent | absent | — |
| `dim_payroll_calendar` | absent | absent | absent | absent | — |
| `fct_compensation_growth` | absent | absent | absent | absent | — |
| `fct_employer_match_events` | 0 | 0 | 0 | 0 | `created_at` |
| `fct_payroll_ledger` | absent | absent | absent | absent | — |
| `fct_policy_optimization` | absent | absent | absent | absent | — |
| `fct_workforce_snapshot` | 0 | 0 | 0 | 0 | `snapshot_created_at` |
| `fct_workforce_snapshot_gate_c` | absent | absent | absent | absent | — |
| `fct_yearly_events` | 0 | 0 | 0 | 0 | `created_at` |

Compared mart set exactly equals the runtime-enumerated mart set.
Audit exclusions are shown per mart; no other columns were omitted.
