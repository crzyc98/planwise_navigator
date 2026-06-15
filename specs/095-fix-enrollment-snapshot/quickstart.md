# Quickstart: Reproduce, Fix, and Verify

**Date**: 2026-06-15 | **Branch**: `095-fix-enrollment-snapshot`

A focused walk-through to reproduce the defect, apply the core fix, and verify it. Assumes an existing multi-year `dbt/simulation.duckdb` (2025–2027). Run all dbt commands from `dbt/` with `--threads 1`.

## 1. Reproduce (Red)

Show voluntary enrollees that are missing from snapshot participation:

```bash
duckdb dbt/simulation.duckdb "
WITH vol AS (
  SELECT DISTINCT employee_id, simulation_year, event_category
  FROM fct_yearly_events
  WHERE event_type='enrollment'
    AND event_category IN ('voluntary_enrollment','proactive_voluntary','year_over_year_voluntary')
)
SELECT vol.simulation_year, vol.event_category,
       COUNT(*) AS enrollees,
       COUNT(CASE WHEN ws.participation_status='participating' THEN 1 END) AS participating
FROM vol
LEFT JOIN fct_workforce_snapshot ws
  ON vol.employee_id=ws.employee_id AND ws.simulation_year=vol.simulation_year
GROUP BY ALL ORDER BY 1,2;"
```

Expected pre-fix: 2026 `voluntary_enrollment` shows `enrollees=59, participating=0` and `year_over_year_voluntary` `1 / 0`.

Confirm the drop point (employee present in enrollment-state accumulator but absent from deferral accumulator):

```bash
duckdb dbt/simulation.duckdb "
WITH vol2026 AS (
  SELECT DISTINCT employee_id FROM fct_yearly_events
  WHERE event_type='enrollment' AND event_category='voluntary_enrollment' AND simulation_year=2026)
SELECT COUNT(*) vol, COUNT(d.employee_id) in_deferral_accum
FROM vol2026 v
LEFT JOIN int_deferral_rate_state_accumulator d
  ON v.employee_id=d.employee_id AND d.simulation_year=2026;"
```

Expected pre-fix: `vol=59, in_deferral_accum=0`.

## 2. Apply the core fix (Phase A)

Edit `dbt/models/intermediate/int_deferral_rate_state_accumulator.sql`, **subsequent-year branch only** (`{% else %}` / `subsequent_year_state`):

- **`is_enrolled_flag` expression** (≈ line 465): replace the `COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false)` with explicit precedence:

  ```sql
  CASE
    WHEN oo.employee_id IS NOT NULL THEN false
    WHEN ne.employee_id IS NOT NULL THEN true
    ELSE COALESCE(ps.is_enrolled_flag, false)
  END AS is_enrolled_flag,
  ```

- **`WHERE` clause** (≈ line 506): change the inclusion predicate so a new enrollment counts even when prior state is `false`:

  ```sql
  WHERE (ps.employee_id IS NOT NULL OR ne.employee_id IS NOT NULL OR ce.employee_id IS NOT NULL OR mr.employee_id IS NOT NULL)
    AND (
      ne.employee_id IS NOT NULL
      OR COALESCE(ps.is_enrolled_flag, false) = true
    )
    AND oo.employee_id IS NULL  -- opted-out employees carry rate 0 via the rate CASE; keep existing behavior if they must remain — see note
  ```

  > Note: preserve current handling of opt-outs and carried-forward enrolled employees exactly as today; the only behavioral change is that **a current-year enrollment is never excluded by a stale prior-year `false`**. Validate against the reconciliation tests rather than assuming.

Do **not** modify the `first_year_state` branch.

## 3. Rebuild the affected chain

Rebuild from the accumulator forward for the affected years (do **not** `--full-refresh` the accumulator):

```bash
cd dbt
dbt run --select int_deferral_rate_state_accumulator+ --vars '{"simulation_year": 2026}' --threads 1
dbt run --select int_deferral_rate_state_accumulator+ --vars '{"simulation_year": 2027}' --threads 1
```

(Or re-run the multi-year simulation via `planalign simulate 2025-2027` for an end-to-end check.)

## 4. Verify (Green)

Re-run the Step 1 reconciliation query — every voluntary category in every year should show `enrollees == participating`.

Spot-check one previously-failing employee gets rate **and** match:

```bash
duckdb dbt/simulation.duckdb "
SELECT ws.employee_id, ws.participation_status, ws.current_deferral_rate,
       m.amount AS employer_match
FROM fct_workforce_snapshot ws
LEFT JOIN fct_employer_match_events m
  ON ws.employee_id=m.employee_id AND ws.simulation_year=m.simulation_year
WHERE ws.simulation_year=2026 AND ws.employee_id='EMP_2025_0000129';"
```

Expected post-fix: `participating`, `current_deferral_rate=0.08`, `employer_match > 0`.

## 5. Run the regression guard

```bash
cd dbt
dbt test --select dq_voluntary_enrollment_snapshot fct_workforce_snapshot --threads 1
```

Expected: 0 failing rows. (Before the fix, this same test must report the 60 offending 2026 rows.)

## 6. Multi-year persistence (FR-007)

Confirm a 2026 voluntary enrollee with no later opt-out is still participating in 2027:

```bash
duckdb dbt/simulation.duckdb "
SELECT simulation_year, participation_status, current_deferral_rate
FROM fct_workforce_snapshot
WHERE employee_id='EMP_2025_0000129' AND simulation_year IN (2026,2027)
ORDER BY simulation_year;"
```

## Out of scope here (Phase C)

Same-year enroll-then-opt-out **prorated contribution** crediting (FR-008 active-window) is not addressed by these steps; year-end status is correct, but partial-window contributions require the separate Phase C change to `int_employee_contributions`.
