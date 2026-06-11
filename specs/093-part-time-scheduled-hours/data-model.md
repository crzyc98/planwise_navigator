# Data Model: scheduled_hours_per_week (#093)

## New Field: `scheduled_hours_per_week`

| Attribute | Value |
|-----------|-------|
| Type | `DECIMAL(5,2)` (SQL) / `Optional[float]` (Python) |
| Nullable | Yes — NULL means "assume 40 hrs/wk" |
| Valid range | 1–40 hrs/wk (part-time is 1–39; full-time is 40) |
| Default | NULL (backward-compatible) |

## New Config Field: `part_time_new_hire_pct`

| Attribute | Value |
|-----------|-------|
| Type | `float` |
| Default | `0.0` |
| Valid range | `[0.0, 1.0]` |
| Location | `WorkforceSettings` in `planalign_orchestrator/config/workforce.py` |
| Meaning | Fraction of newly generated hires assigned 20 hrs/wk |

## Data Flow

```
census.parquet
  └─ stg_census_data.sql           (scheduled_hours_per_week NULLABLE)
       └─ int_employer_eligibility.sql     (replace 2080 → COALESCE(hrs,40)*52)
       └─ int_eligibility_computation_period.sql (same replacement)
       └─ int_hiring_events.sql           (assign part-time to pct fraction)
            └─ int_workforce_previous_year.sql  (carry forward)
                 └─ fct_workforce_snapshot.sql  (expose in output)
```

## API Response: `/analyze-part-time-pct`

```typescript
interface PartTimePctResponse {
  column_present: boolean;     // false → disable button
  headcount: number;           // total employees in census
  part_time_count: number;     // employees with (hrs * 52) < 1000
  part_time_pct: number;       // part_time_count / headcount
}
```

## Hours Formula Change

**Before:**
```sql
days * (2080.0 / 365.0)
-- or: 2080  (full year)
```

**After:**
```sql
days * (COALESCE(scheduled_hours_per_week, 40.0) * 52.0 / 365.0)
-- or: COALESCE(scheduled_hours_per_week, 40.0) * 52.0  (full year)
```

`COALESCE(40.0) * 52.0 = 2080.0` — NULL rows are identical to current behavior.
