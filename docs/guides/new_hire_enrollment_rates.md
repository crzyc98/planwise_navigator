# New-Hire Enrollment Rates and Deferral Spread

How to control who enrolls, and at what rate, for new hires. Issue #652.

## The two enrollment dials

Both live under `enrollment.auto_enrollment` and apply to **eligible new hires in their hire year only**. Continuing employees are never touched by either.

```yaml
enrollment:
  auto_enrollment:
    voluntary_enrollment_rate: 0.6   # 60% of eligible new hires enroll on their own
    new_hire_opt_out_rate: 0.1       # 10% of the auto-enrolled remainder opts out
```

Given a voluntary rate `P` and an opt-out rate `Q`, eligible new hires inside auto-enrollment scope land as:

| Outcome | Share |
|---|---|
| Voluntarily enrolled | `P` |
| Auto-enrolled, participating | `(1 − P) × (1 − Q)` |
| Opted out | `(1 − P) × Q` |
| Not enrolled | 0 |

Measured on a 2026–2030 run at `P=0.6, Q=0.1`: 60.2 / 59.9 / 59.9 / 61.4 / 57.9 percent voluntary by year.

### Unset means something

Leaving a key out is not the same as setting it to zero. **Unset** keeps the previous demographic model for that decision, so scenarios that never set the key reproduce their old results exactly. **Any explicit value**, including `0.0` and `1.0`, applies the flat meaning.

This matters because `voluntary_enrollment_rate` changed meaning. It used to be a multiplier on demographic probabilities, where `1.0` meant "demographics unchanged". It is now an exact fraction, where `1.0` means "everybody". A scenario that stored an explicit value will behave differently.

### What the rates do not control

The deferral percentage. An employee selected to enroll voluntarily still gets their rate from the demographic table (optionally spread; see below). The rates govern only the enroll-or-not and opt-out decisions.

### Who is in the denominator

Eligible new hires — hired in the simulation year and plan-eligible in it. New hires still inside a waiting period are excluded until the year they become eligible. In a plan with a three-month wait, that population is large and appears as `not_participating - not auto enrolled`; it is the waiting period working correctly, not a gap in coverage.

New hires who terminate before their auto-enrollment date generate no enrollment event at all. That is correct, and it means the "not enrolled" bucket is never exactly zero unless you restrict to employees active at year end.

## The deferral spread

Without it, every member of a demographic cell receives the identical rate — 421 mid-career/moderate new hires all at exactly 6% in a measured run. Real elections scatter.

```yaml
enrollment:
  auto_enrollment:
    deferral_spread_max_lift: 4   # whole percentage points; 0 (default) = off
```

The table value becomes a **floor**. Employees move up from it, never down:

| Lift | Share |
|---|---|
| +0 pp | 40% |
| +1 pp | 30% |
| +2 pp | 15% |
| +3 pp | 10% |
| +4 pp | 5% |

That same cell, before and after:

| | 6% | 7% | 8% | 9% | 10% |
|---|---|---|---|---|---|
| Before | 421 | – | – | – | – |
| After | 164 | 109 | 74 | 50 | 24 |

### It raises costs, on purpose

Enabling the spread raises the average deferral rate by about 0.3 percentage points, and therefore projected employer match cost. This is intended. The previous averages were artificially low precisely because everyone sat on the floor; the table values were never meant to be what everybody elects.

If you need comparability with earlier runs, leave the spread off.

### What it does not touch

Census employees. They carry their actual deferral rates from the input file, and no demographic setting reaches them. If you see a large cluster at one rate among existing participants, that is your census data, not the model — adjusting the demographic table or the spread will not move it.

### Interaction with the match magnet

The spread is applied before the match-maximizing snap, so an employee spread to 4% can still be pulled up to a 6% match ceiling. That means a cell can legitimately show accumulation at the employer-match rate even with the spread on. Only the accumulation at the *table value* is the thing the spread removes.

## The deferral cap

`enrollment.match_magnet.max_deferral_rate` bounds voluntary deferral selection and defaults to **15%** (raised from 10% in issue #652 so the higher cells have room to spread).

Note this is set in Python, not dbt. `_export_match_magnet` writes `voluntary_max_deferral_rate` unconditionally, so the `dbt_project.yml` value never applies on an orchestrator run.

Raising it changed results on its own: three cells (mature/executive and senior/high at 12%, senior/executive at 15%) were being clamped down to 10%. On an otherwise unchanged scenario this moves 295 of 43,903 employee-years.

## Verifying a scenario

Always in an isolated database, never the shared dev DB:

```bash
DATABASE_PATH=/tmp/run/iso.duckdb planalign simulate 2026-2030 \
  --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb
```

```sql
SELECT simulation_year, participation_status_detail,
       ROUND(100.0 * COUNT(*)
             / SUM(COUNT(*)) OVER (PARTITION BY simulation_year), 1) AS pct
FROM fct_workforce_snapshot
WHERE EXTRACT(YEAR FROM employee_hire_date) = simulation_year
  AND current_eligibility_status = 'eligible'
  AND termination_date IS NULL
GROUP BY 1, 2 ORDER BY 1, 3 DESC;
```

The integration suites in `tests/integration/test_new_hire_enrollment_rates.py` and `tests/integration/test_deferral_spread.py` run these assertions against databases named by `PLANALIGN_652_DB_*` environment variables.
