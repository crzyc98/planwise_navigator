# Data Model: Fix Band Label Mismatches

**Date**: 2026-03-16 | **Branch**: `073-fix-band-label-mismatch`

## Entities (No Changes)

This bug fix does not introduce new entities or modify existing schemas. It corrects the string labels produced by band assignment logic in 19 dbt models to match the existing seed-defined values.

## Band Label Contract

All models that assign age or tenure bands MUST produce labels that exist in the corresponding seed table.

### Age Bands (source: `config_age_bands.csv`)

| band_id | band_label | min_value | max_value | Convention |
|---------|-----------|-----------|-----------|------------|
| 1       | < 25      | 0         | 25        | [0, 25)    |
| 2       | 25-34     | 25        | 35        | [25, 35)   |
| 3       | 35-44     | 35        | 45        | [35, 45)   |
| 4       | 45-54     | 45        | 55        | [45, 55)   |
| 5       | 55-64     | 55        | 65        | [55, 65)   |
| 6       | 65+       | 65        | 999       | [65, inf)  |

### Tenure Bands (source: `config_tenure_bands.csv`)

| band_id | band_label | min_value | max_value | Convention |
|---------|-----------|-----------|-----------|------------|
| 1       | < 2       | 0         | 2         | [0, 2)     |
| 2       | 2-4       | 2         | 5         | [2, 5)     |
| 3       | 5-9       | 5         | 10        | [5, 10)    |
| 4       | 10-19     | 10        | 20        | [10, 20)   |
| 5       | 20+       | 20        | 999       | [20, inf)  |

## Affected Join Relationships

Band labels serve as JOIN keys between:
- Employee band assignments (intermediate models) <-> Hazard rate lookup tables (dimensions/seeds)
- The JOIN contract requires exact string match on `age_band` and `tenure_band` columns.

## Validation Rule

For any table T containing an `age_band` column:
```
SELECT DISTINCT age_band FROM T
  EXCEPT
SELECT band_label FROM config_age_bands
```
Must return zero rows. Same for `tenure_band` / `config_tenure_bands`.
