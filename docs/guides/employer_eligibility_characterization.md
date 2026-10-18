# Employer eligibility characterization reconciliation (#840)

## Cause

The expected 2026–2029 contribution totals used an older IRS-limit seed.
This was an input-version mismatch, not a change in eligibility service credit.
The 2025 totals and all recipient counts remain unchanged.

The previous fixture was recorded in `3d9a3a8c`. Commit `b57926cf` subsequently
updated the 2026 compensation cap from $350,000 to $360,000, along with the
deferral/catch-up limits. Commit `2911a028` rebased the projected 2027–2035 limits
on that 2026 anchor. Projected limits remain planning assumptions.

## Controlled reproduction

Using application source at `8e4723a66911b09fd3851cbcd3d0f9889333cc8b`, Python
3.12.11, DuckDB 1.5.6, dbt-core 1.9.11, and dbt-duckdb 1.9.6:

1. Run the existing zero-wait fixture through all five years, 2025–2029, with
   seed 136001 and the synthetic census produced by `prepare_census_parquet`.
2. Copy the current dbt project into a disposable directory, excluding databases,
   target artifacts, and logs. Replace only `seeds/config_irs_limits.csv` with
   `git show 3d9a3a8c:dbt/seeds/config_irs_limits.csv`.
3. Run the same fixture with `ConstructionSpec.dbt_project_dir` pointing to that
   copy, a fresh database, separate dbt artifacts, and the same census/config.
4. Compare annual aggregates and employee/year workforce inputs in both
   directions using `EXCEPT ALL`.

The historical-seed counterfactual reproduces **every previous annual aggregate
exactly**, including all core/match totals and recipient counts. Current seeds
reproduce the amounts in the original CI failure. No differences were found in
employee/year identities, current or prorated compensation, tenure, age,
employment status, or current deferral rates.

A second independent current-seed run also matches the first current run exactly
at annual and employee level, including employee contributions and employer
core/match amounts. This comparison used separate databases and dbt projects.

| Year | Current core | Current match | Core increase | Match increase | Changed core/match recipients |
|---|---:|---:|---:|---:|---:|
| 2025 | 800,365.86 | 822,949.90 | 0.00 | 0.00 | 0 / 0 |
| 2026 | 850,386.54 | 950,147.42 | 8,847.67 | 10,156.00 | 30 / 26 |
| 2027 | 900,459.08 | 1,039,606.14 | 9,070.53 | 10,753.64 | 32 / 28 |
| 2028 | 941,650.99 | 1,136,987.70 | 9,048.12 | 10,365.70 | 31 / 27 |
| 2029 | 988,279.14 | 1,205,015.43 | 8,611.07 | 10,581.42 | 30 / 28 |

The last column counts employees whose contribution **amount changed**, not a
change in the number receiving contributions. Core recipients remain
152/155/158/161/164; match recipients remain 116/128/137/147/151.

Independently recomputing each paid employee's 3% core contribution from
`int_employer_core_contributions.eligible_compensation`, once with each year's
old compensation cap and once with the current cap, accounts for the entire
core delta to the cent. Use that contribution-specific basis; the snapshot's
prorated compensation is not interchangeable for this reconciliation.

Seed SHA-256 fingerprints:

- Historical: `7040b164df66bdb924e4b8c080c192cbb4c49f7f543bd0382159cf90bc704980`.
- Current: `5ae9b81eaf9223384dc8fdf32e381f9187b531aefdf900185af2a93163acdd45`.

## Regression contract

The fixture now records its seed fingerprint and explanation. A later seed
change requires explicit reconciliation rather than an unexplained numeric
refresh. Recipient counts compare exactly; monetary totals retain absolute
$0.01 tolerance with no relative tolerance. Opening-year waits 1/2/3,
zero-wait years, below-threshold exclusions, workforce service reconciliation,
and termination-date rate qualification remain covered.

Run with the project's pinned dependencies, never against the shared database:

```bash
source .venv/bin/activate
DATABASE_PATH="$PWD/var/eligibility-check-sentinel.duckdb" \
  DBT_PARTIAL_PARSE=false \
  pytest tests/integration/test_employer_eligibility_tenure.py -q
```

The fixtures allocate disposable databases. Hosted full-CI coverage and shard
measurement acceptance are tracked separately in [ci_measurements.md](ci_measurements.md).
