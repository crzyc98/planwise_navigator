# Campaign A frozen oracle
Frozen before any simulation on 2026-10-29 at base 53b3c32a706bcdf57ddaf71976576bfce67c250c.

## Population and compensation
Score the default ALL population displayed in Studio AnalyticsDashboard (population useState defaults to 'all', line 215) via simulation/results_reader.py: all fct_workforce_snapshot rows; headcount is COUNT(DISTINCT employee_id), compensation is AVG(prorated_annual_compensation). Include new hires and terminated employees; this is earned prorated compensation, not annualized salary. Compute with unrounded values, not displayed thousands. 2026 supplies the denominator only; score YoY for 2027–2030.
Calibrator reads fct_compensation_growth methodology_a_current: detailed_status_code IN ('continuous_active','new_hire_active'), AVG(prorated_annual_compensation). This differs from the default Studio ALL population: record this source-verified metric mismatch. Also report active-only growth and active headcount as secondary diagnostics (LOWER(employment_status) = 'active'); never replace primary ALL-population scores with those diagnostics.

## Scores
For each year, growth = 100*(current/prior - 1). comp_err and hc_err are absolute differences from cell targets in percentage points. cal_gap is absolute difference between the calibration prediction for that same year and the applied full simulation growth. Cell scores are maxima across the four years; campaign score is arithmetic mean of cell maximum comp_err. Report maximum hc_err, maximum cal_gap and failure counts alongside it. Missing years, duplicate employee/year records, missing predictions or nonfinite metrics fail; never drop failed cells or average only successful cells.

## Plausibility
Each is failure: range min >= max; either endpoint decreases with ascending level; per-level new-hire annual salary average outside 0.6–1.3 times frozen census level average; scale clamped; unannounced lever fallback; negative or nonfinite salary/range/scale/count value. Negative signed growth or signed target errors are legitimate and are not negative monetary values. Audit new-hire annual salary from hire events (before subsequent increases); also report active new-hire current_compensation. Empty new-hire levels are unscorable, not automatically passing.

## Acceptance and split
All holdout cells must have max comp_err <= 0.25pp, hc_err <= 0.10pp, cal_gap <= 0.10pp and zero failures. Infeasibility passes only with explicit system diagnosis and no implausible returned range; record separately, never substitute a numeric zero score. No numeric campaign acceptance with missing cells.
Matrix.json freezes 54 cells: all three shapes crossed with HC {2,3.5,5}, compensation {1,2.5,4}, turnover low {0.1,0.2} / high {0.2,0.35}. Dev is each shape crossed with (HC,comp,turnover) {(5,1,low),(2,4,high),(5,4,high)}: nine cells. Other 45 are holdout. Seed 42 all cells; seed 101 dev at baseline and end. Holdout seed 101 is not required and reported N/A.
Noise band is mean absolute paired difference in baseline dev max comp_err between seeds 42 and 101. Keep only dev score improvements strictly exceeding this frozen band, with no new failures and passing fast suite and ruff. Holdout baseline/final/every third kept change only, never tune from holdout.

## Protocol
Synthetic censuses only, hashed before runs. Full provenance-matched baseline, Studio new_hire_scale calibration, exact fractional apply with provenance, fresh full simulation. Every database under /tmp/nhcal/<cell>/ with underscore-safe basename and identical DATABASE_PATH. Save raw annual predictions and applied ranges in cell JSON. Independent auditor reads this oracle and raw tables, never lead scorer or implementer reasoning. Resolve scorer disagreement before hill climb. First test fast/full parity. At most 12 iterations, stop at acceptance or three consecutive non-improvements. No Campaign B.

## Amendment 2026-10-29 (user decision, after parity diagnosis)
The scored metric is Studio's **Active** population view, not the ALL default: comp growth = YoY of AVG(prorated_annual_compensation) over LOWER(employment_status)='active' fct_workforce_snapshot rows; headcount = active rows. ALL-population and annualized figures are diagnostics only. Reason: ALL rows include terminated employees, so hire/termination timing dominates that growth figure (and ALL headcount drifts from the E077 active target). New stages `hire_date_fix` and `search_fix` follow the simulation fixes for hire-date assignment (92f67588) and leap-year proration (15331c5b) plus the minimax search (eedcd5cf). Pre-amendment stage scores are not comparable to post-fix stages.

## Amendment 2026-10-30 (user decision, before any post-fix holdout run)
Written and committed before any holdout cell runs at stage `turnover_indexed_3pct`; holdout results must not change it.
- **Acceptance bars** replace the per-year 0.25pp bar, which sits below measured seed noise (~0.3–0.4pp per year at 5,000 employees). A run passes a bar only if hc_err <= 0.10pp, cal_gap <= 0.10pp and it has zero failures, plus:
  - per-year bar: max annual comp_err <= 0.50pp;
  - compound bar: |2026→2030 compound Active comp growth − target| <= 0.25pp.
  Both pass rates are reported; neither replaces the other.
- **Stress cells:** cells with a 1% comp-growth target are stress tests, scored and reported separately. With 3.5% merit and 2% COLA, 1% average growth requires new-hire pay to keep falling behind incumbents, which is not a typical US workforce. Campaign acceptance is judged on the remaining (standard) cells.
- **Holdout configuration:** stage `turnover_indexed_3pct` (first-year prior-hire turnover fix ac5be11d, 3% annual new-hire range growth), seed 42, all 45 holdout cells, run once. Infeasible-but-diagnosed cells are scored on their returned best scale like every other run.

## Amendment 2026-10-31 (user decision, before any backfill holdout run)
The seed-42 holdout was examined while diagnosing level-mix drift, so it no longer counts as unseen. Stage `backfill_by_level` (commit 66267c26) allocates hires to each level's shortfall against its start-year census share.
- **Plausibility yardstick:** the per-level new-hire band (0.6–1.3× census level average) compares against the census average grown by the run's configured `new_hire.salary_growth_rate`, i.e. `census_mean × (1 + rate)^(year − 2026)`. Reason: starting pay is meant to rise with the market, so a frozen 2026 yardstick flags normal market pay as implausible. With rate 0 the check is unchanged. Earlier stages' committed scores used the frozen yardstick.
- **Fresh holdout:** all 45 holdout cells at seed 7 (never run), stage `backfill_by_level`, run once after dev review, using the 2026-10-30 bars and stress-cell split.

## Amendment 2026-10-31b (user decision, after the seed-7 holdout; applies only to later runs)
The seed-7 holdout is spent. Seed-7 scores stay as recorded under the earlier rules.
- **Planned-hire rule:** `missing_hires_<year>_<level>` fails only when Studio planned hires for that level and year (`int_workforce_needs_by_level.hires_needed > 0`) and none were made. Under backfill-by-level a level at or above its census share legitimately plans zero hires.
- **Stage `two_dial`:** calibration solves the new-hire range scale and the annual starting-pay growth rate (`new_hire.salary_growth_rate`) together, rate bounded 0–8%, starting from 3%, evaluation budget 12, on top of backfill-by-level. Reason: with a stable level mix, average pay growth converges to the starting-pay growth rate, so one scale can only front-load other targets.
- **Plausibility yardstick** uses the run's applied (calibrated) growth rate, per the 2026-10-31 amendment.
- **Fresh holdout:** all 45 holdout cells at seed 13 (never run), stage `two_dial`, run once after dev review, with the 2026-10-30 bars and stress-cell split.
