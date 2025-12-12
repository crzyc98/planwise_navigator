# Data Model: Centralize Age/Tenure Band Definitions

**Date**: 2025-12-12
**Feature**: 001-centralize-band-definitions

## Entity Relationship Diagram

```
┌─────────────────────────┐     ┌─────────────────────────┐
│   config_age_bands      │     │  config_tenure_bands    │
├─────────────────────────┤     ├─────────────────────────┤
│ band_id (PK)            │     │ band_id (PK)            │
│ band_label              │     │ band_label              │
│ min_value (inclusive)   │     │ min_value (inclusive)   │
│ max_value (exclusive)   │     │ max_value (exclusive)   │
│ display_order           │     │ display_order           │
└─────────────────────────┘     └─────────────────────────┘
           │                               │
           │ Referenced by                 │ Referenced by
           ▼                               ▼
┌─────────────────────────────────────────────────────────┐
│              Hazard Multiplier Seeds                     │
├─────────────────────────────────────────────────────────┤
│ config_termination_hazard_age_multipliers.csv           │
│ config_termination_hazard_tenure_multipliers.csv        │
│ config_promotion_hazard_age_multipliers.csv             │
│ config_promotion_hazard_tenure_multipliers.csv          │
└─────────────────────────────────────────────────────────┘
           │
           │ Joined via band_label
           ▼
┌─────────────────────────────────────────────────────────┐
│              Event Models (12 files)                     │
├─────────────────────────────────────────────────────────┤
│ Use {{ assign_age_band() }} and {{ assign_tenure_band() │
│ }} macros to derive age_band and tenure_band columns    │
└─────────────────────────────────────────────────────────┘
```

## Entity Definitions

### config_age_bands

**Purpose**: Single source of truth for age band definitions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `band_id` | INTEGER | PRIMARY KEY, NOT NULL | Unique identifier for the band |
| `band_label` | VARCHAR | NOT NULL, UNIQUE | Display label (e.g., "25-34") |
| `min_value` | INTEGER | NOT NULL, >= 0 | Lower bound (inclusive) |
| `max_value` | INTEGER | NOT NULL, > min_value | Upper bound (exclusive) |
| `display_order` | INTEGER | NOT NULL | Sort order for reporting |

**Initial Data**:

```csv
band_id,band_label,min_value,max_value,display_order
1,< 25,0,25,1
2,25-34,25,35,2
3,35-44,35,45,3
4,45-54,45,55,4
5,55-64,55,65,5
6,65+,65,999,6
```

**Validation Rules**:
- `min_value` must be >= 0 (no negative ages)
- `max_value` must be > `min_value`
- Bands must be contiguous (no gaps): `max_value[n] == min_value[n+1]`
- Bands must not overlap
- First band must start at 0
- Last band must have `max_value` of 999 (effectively unbounded)

### config_tenure_bands

**Purpose**: Single source of truth for tenure band definitions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `band_id` | INTEGER | PRIMARY KEY, NOT NULL | Unique identifier for the band |
| `band_label` | VARCHAR | NOT NULL, UNIQUE | Display label (e.g., "2-4") |
| `min_value` | INTEGER | NOT NULL, >= 0 | Lower bound (inclusive) in years |
| `max_value` | INTEGER | NOT NULL, > min_value | Upper bound (exclusive) in years |
| `display_order` | INTEGER | NOT NULL | Sort order for reporting |

**Initial Data**:

```csv
band_id,band_label,min_value,max_value,display_order
1,< 2,0,2,1
2,2-4,2,5,2
3,5-9,5,10,3
4,10-19,10,20,4
5,20+,20,999,5
```

**Validation Rules**:
- Same as age bands (contiguous, no overlaps, no gaps)
- `min_value` must be >= 0 (no negative tenure)

## Staging Models

### stg_config_age_bands

**Purpose**: Clean and validate age band seed data.

```sql
SELECT
    band_id,
    band_label,
    min_value,
    max_value,
    display_order
FROM {{ ref('config_age_bands') }}
ORDER BY display_order
```

### stg_config_tenure_bands

**Purpose**: Clean and validate tenure band seed data.

```sql
SELECT
    band_id,
    band_label,
    min_value,
    max_value,
    display_order
FROM {{ ref('config_tenure_bands') }}
ORDER BY display_order
```

## Macro Interfaces

### assign_age_band(column_name)

**Purpose**: Generate CASE expression for age band assignment.

**Input**: Column name containing age value (e.g., `'current_age'`)

**Output**: SQL CASE expression that returns band_label

**Usage**:
```sql
SELECT
    employee_id,
    current_age,
    {{ assign_age_band('current_age') }} AS age_band
FROM employees
```

**Generated SQL** (dynamically from seed):
```sql
CASE
    WHEN current_age < 25 THEN '< 25'
    WHEN current_age < 35 THEN '25-34'
    WHEN current_age < 45 THEN '35-44'
    WHEN current_age < 55 THEN '45-54'
    WHEN current_age < 65 THEN '55-64'
    ELSE '65+'
END
```

### assign_tenure_band(column_name)

**Purpose**: Generate CASE expression for tenure band assignment.

**Input**: Column name containing tenure value (e.g., `'current_tenure'`)

**Output**: SQL CASE expression that returns band_label

**Usage**:
```sql
SELECT
    employee_id,
    current_tenure,
    {{ assign_tenure_band('current_tenure') }} AS tenure_band
FROM employees
```

## State Transitions

Bands are static configuration; no state transitions apply.

Employee band assignments change when:
- Age increases (birthday crosses band boundary)
- Tenure increases (anniversary crosses band boundary)

These transitions are handled by the models that call the macros, not by the band configuration itself.

## Referential Integrity

### Foreign Key Relationships

The `band_label` column serves as the join key between:

1. **Band definition seeds** → **Hazard multiplier seeds**
   - `config_age_bands.band_label` ↔ `config_*_hazard_age_multipliers.age_band`
   - `config_tenure_bands.band_label` ↔ `config_*_hazard_tenure_multipliers.tenure_band`

2. **Event models** → **Hazard models**
   - `int_*_events.age_band` ↔ `int_hazard_*.age_band`
   - `int_*_events.tenure_band` ↔ `int_hazard_*.tenure_band`

### Validation Tests

| Test | Target | Validates |
|------|--------|-----------|
| `unique` | band_id | No duplicate IDs |
| `unique` | band_label | No duplicate labels |
| `not_null` | all columns | No missing values |
| `accepted_values` | band_label | Labels match hazard seeds |
| `custom:no_gaps` | min/max_value | Contiguous ranges |
| `custom:no_overlaps` | min/max_value | Non-overlapping ranges |

## Migration Compatibility

The new data model is fully backward compatible:

1. **Existing seeds unchanged**: Hazard multiplier seeds continue to reference `band_label`
2. **Macro output matches**: Generated CASE statements produce identical `band_label` values
3. **Join keys preserved**: All existing joins on `age_band`/`tenure_band` continue to work
