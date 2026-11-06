# Growth metrics

What each pay growth figure in Studio measures. Calibration studies and solver
work (#1107) are judged against these definitions. Change them here first.

All pay is earned pay: `prorated_annual_compensation` in `fct_workforce_snapshot`,
which is pay for the days actually worked in the year. The start year is the
first simulated year, not the census, so it has a level and no growth rate.

## Annual metrics

| Metric | Where it appears | Pay | Population | Denominator |
|---|---|---|---|---|
| **Total pay per head** (`payroll_per_head`) | Calibration target; Analysis page "Total Pay ÷ Year-End Headcount" | Earned | Everyone paid in the year, leavers included | Active headcount at year end |
| **Active average** (`active_average`) | Calibration target; Analysis page "Average Compensation", Active view | Earned | Employees active at year end | Same employees |
| **New-hire and existing pay** (`new_hire_avg_comp`, `existing_avg_comp`) | Calibration results | Annualized rate | Hires of the year; everyone else | Same employees |

Annual growth is `this year / last year - 1`, for every year after the start
year.

Total pay per head is the figure a sponsor can reproduce from their own payroll
and headcount totals. It's not a pay rate. Its numerator and denominator cover
different people, so it also moves with how many days hires worked, how much
leavers were paid before leaving, and year-end headcount. Use annualized pay when
the question is what a job pays.

## Horizon growth

Two horizon figures exist, and they aren't the same number:

- **Horizon mean**: the arithmetic mean of the annual growth rates. Calibration
  reports this as "horizon mean", holds it inside `compound_band_pct`, and the
  Analysis page shows it as "Average growth". It's slightly above CAGR whenever
  annual rates vary.
- **CAGR**: `(last / first) ^ (1 / years) - 1`, from the start year to the end
  year. Studio shows it on the Analysis page for active average pay and total
  compensation. Calibration doesn't report it yet.

CAGR is the contract for judging a study or a solver result, because it's what a
sponsor's compounded pay actually does. A mean within tolerance doesn't prove a
CAGR within tolerance. Anything still reporting the mean must say so.

## Annual guardrails

A horizon result also has to hold up year by year:

- **Tolerance** (`tolerance_pct`, 0.05pp by default) is the largest miss the
  analyst accepts in any year after the start year. Calibration converges only
  when every year is inside it.
- **Worst-year error** is the largest absolute gap to the target in any one year.

## Seed variability and tolerance

These answer different questions, so they're set separately.

- **Seed variability** is measured: rerun the same inputs across seeds and report
  the spread of each year's growth. It says how precisely the model can answer.
- **Tolerance** is approved by the analyst: it says how close the answer must be.

Never widen a tolerance to hide bias. A miss that keeps the same sign across
seeds is bias, however small it is. A miss inside the seed spread with changing
sign is noise, and more search won't remove it.
