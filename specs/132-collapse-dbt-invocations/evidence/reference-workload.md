# Reference workload

- Census: `var/perf_profile/census_60k.parquet`
- Rows: 60,040
- Unique employee IDs: 60,040
- SHA-256: `285fbfe1b476cae634a3960c865c1891d2c155e691744fdf7ee192eba193c2a4`
- Horizon: 2025–2029
- Random seed: 42
- dbt threads: 1
- Configuration: `var/perf_profile/studio_shape.yaml`

The census was generated once with an 8× scale factor and is reused unchanged
for baseline, candidate, and determinism runs within every parity gate.
