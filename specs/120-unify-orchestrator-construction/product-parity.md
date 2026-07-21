# Product-entry parity evidence

## Automated contract tests

The following targeted suite passed after migration:

```text
pytest tests/unit/construction/test_builder_equivalence.py \
  tests/integration/test_batch_fresh_database_parity.py \
  tests/integration/test_product_entrypoint_parity.py \
  tests/test_progress_display.py -q

16 passed
```

This covers canonical wrapper delegation, progress wrapping, batch `NONE`
construction, semantic signature equality for CLI/batch/Studio, Studio origin
propagation, and the shared-development-database hash guard.

## Harness validation

| Configuration | Status | Wall time | Peak RSS | Wrapped invocations |
|---|---|---:|---:|---:|
| Reference | pass | 44.7s | 593 MiB | 14 |
| Studio-shaped | pass | 43.6s | 591 MiB | 14 |

The Studio-shaped campaign used the identifier-safe label `studio_shaped` and
completed through the product wrapper construction path. Together with the
targeted matrix, these runs establish equivalent canonical construction for the
reference and feature-enabled fixture configurations.

Both successful campaigns independently verified that `dbt/simulation.duckdb` retained
SHA-256 `46ef47d6c8b46142d2cb0863d19ba8ba19e2bd6c3fcab2e846cbaacc4bfa5683`.
