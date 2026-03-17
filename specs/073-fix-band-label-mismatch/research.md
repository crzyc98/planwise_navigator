# Research: Fix Band Label Mismatches

**Date**: 2026-03-16 | **Branch**: `073-fix-band-label-mismatch`

## R1: Band Assignment Macro Capabilities

**Decision**: Use `assign_age_band()` and `assign_tenure_band()` macros for all band assignments, including expressions like `current_age + 1`.

**Rationale**: CLAUDE.md Section 9.1 explicitly confirms macros work with expressions: `{{ assign_age_band('current_age + 1') }} AS age_band`. The macros use `run_query()` to load seed data at compile time and generate CASE expressions with the column/expression inserted into each WHEN clause. The generated SQL `WHEN current_age + 1 >= 25 AND current_age + 1 < 35` is valid DuckDB.

**Alternatives considered**:
- Hardcoded CASE with correct labels: Works but defeats the purpose of centralized band config.
- Wrapping expression in a CTE alias first: Unnecessary complexity since macros handle expressions directly.

## R2: dim_enrollment_hazards Tenure Band Strategy

**Decision**: Replace hardcoded tenure boundary values (`'0-1'`, `'1-3'`, `'3-5'`) with seed-aligned labels. This model defines hazard rate multipliers by tenure band, so it must use the same band labels that appear in the employee data.

**Rationale**: The `dim_enrollment_hazards` model is a lookup table that gets JOINed on `tenure_band`. If the labels don't match the employee band assignments, the JOIN produces zero matches. The current labels (`0-1`, `1-3`, `3-5`) don't match any seed-defined band (`< 2`, `2-4`, `5-9`, `10-19`, `20+`).

**Alternatives considered**:
- Using the macro: Not applicable here since this model defines hazard rates per band label rather than assigning bands to employees. It needs to reference band labels as string literals.
- Joining to seed table: Possible but over-engineered for a lookup table that just needs correct string constants.

## R3: int_enrollment_events_v2 Voluntary Enrollment Section

**Decision**: Replace the entirely different band scheme (age: `< 30, 30-39, 40-49, 50+`; tenure in months: `< 24, < 60, < 120`) with standard macro calls using the correct column/expression.

**Rationale**: This section uses a completely separate band scheme with different boundaries AND different units (months vs years for tenure). The tenure column `current_tenure` appears to be in months in this CTE, requiring conversion to years (`current_tenure / 12.0`) before passing to the macro.

**Alternatives considered**:
- Converting month boundaries to match seed bands: Fragile; still hardcoded.
- Adding a tenure-in-months macro variant: Over-engineered; just convert to years inline.

## R4: events_enrollment_sql Macro Tenure Band Split

**Decision**: Replace the split `10-14` / `15-19` bands with the single `10-19` band from the seed.

**Rationale**: The seed defines 5 tenure bands. The macro splits `10-19` into two sub-bands that don't exist in any hazard rate table, producing JOIN mismatches for employees with 10-19 years tenure. Use the `assign_tenure_band()` macro call instead.

**Alternatives considered**:
- Keeping the split and adding matching hazard rates: Contradicts the centralized band definition principle and would require changes across all other models.

## R5: Existing Band Validation Tests

**Decision**: Existing tests (`test_age_band_no_gaps.sql`, `test_age_band_no_overlaps.sql`, `test_tenure_band_no_gaps.sql`, `test_tenure_band_no_overlaps.sql`) validate seed configuration integrity only. A new cross-model consistency test is needed.

**Rationale**: Current tests validate that the seed CSVs have no gaps or overlaps. They do NOT validate that model outputs use labels from the seeds. The new test should query `fct_workforce_snapshot` and anti-join against the seed tables to find any band labels not in the configuration.

**Alternatives considered**:
- Adding accepted_values tests per model: Already partially done but doesn't catch new models; a cross-model test is more comprehensive.
- Python-based validation: Over-engineered; a dbt test is simpler and runs as part of `dbt test`.
