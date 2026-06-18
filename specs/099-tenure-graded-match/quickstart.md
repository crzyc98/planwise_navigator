# Quickstart: Tenure-Graded Multi-Tier Employer Match Formula

## Goal

Verify that a plan analyst can configure the example two-band design and that the system calculates match amounts correctly for employees in each band.

## Via Studio UI

1. Launch `planalign studio`.
2. Open a workspace's DC Plan configuration → Employer Match section.
3. Set match mode to **Tenure-Graded (multi-tier by years of service)**.
4. Add band 1: years 0–10, tiers: 100% on first 2% deferred, 50% on next 6% deferred.
5. Add band 2: years 10+ (unbounded), tiers: 100% on first 2% deferred, 50% on next 8% deferred.
6. Confirm the config summary shows: band 1 max effective match = 5%, band 2 max effective match = 6%, with no gap/overlap warnings.
7. Save the configuration.

## Via config + dbt directly (developer verification)

1. In `config/simulation_config.yaml`, set:
   ```yaml
   employer_match:
     employer_match_status: 'tenure_graded'
     tenure_graded_bands:
       - min_years: 0
         max_years: 10
         tiers:
           - { employee_min: 0.00, employee_max: 0.02, match_rate: 1.00 }
           - { employee_min: 0.02, employee_max: 0.08, match_rate: 0.50 }
       - min_years: 10
         max_years: null
         tiers:
           - { employee_min: 0.00, employee_max: 0.02, match_rate: 1.00 }
           - { employee_min: 0.02, employee_max: 0.10, match_rate: 0.50 }
   ```
2. Run a single-year simulation: `planalign simulate 2025 --verbose`.
3. Query results:
   ```bash
   duckdb dbt/simulation.duckdb "
   SELECT employee_id, years_of_service, deferral_rate, match_amount, formula_type
   FROM fct_employer_match_events
   WHERE simulation_year = 2025 AND formula_type = 'tenure_graded'
   ORDER BY years_of_service LIMIT 20"
   ```
4. Spot-check expected values:
   - Employee with 5 years tenure, 8% deferral → match = `1.00*0.02 + 0.50*0.06 = 0.05` of eligible compensation.
   - Employee with 12 years tenure, 10% deferral → match = `1.00*0.02 + 0.50*0.08 = 0.06` of eligible compensation.
   - Employee with 5 years tenure, 10% deferral (above their 8% band cap) → match still = 0.05 (capped, no match on the 8–10% portion).

## Negative-path verification (gap/overlap)

1. Misconfigure band 2 to start at `min_years: 12` (leaving a gap between 10 and 12).
2. Confirm the Studio UI shows a non-blocking gap warning on save.
3. Attempt `planalign simulate 2025` — confirm it fails fast with a clear validation error (Pydantic `ValueError`) before any dbt run starts, per FR-008's hard-block requirement.

## Automated test entry points

- `tests/test_match_modes.py` — new test classes for `TenureGradedMatchBand`/`TenureBandMatchTier` validation and `_export_employer_match_vars()` round-trip.
- `dbt/tests/data_quality/test_tenure_graded_tier_no_gaps_overlaps.sql` — fails the dbt build if a malformed `tenure_graded_bands` var ever reaches dbt directly.
