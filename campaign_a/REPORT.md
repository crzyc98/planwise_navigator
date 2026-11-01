# Campaign A — calibration now predicts Studio; per-year accuracy limited by simulation dynamics and seed noise

As of 2026-10-30, branch `t3/nh-salary-calibration-campaign`. Contract amended 2026-10-29 (ORACLE.md): score Studio's **Active** view (active-row average prorated comp growth, active headcount).

## Changes (all committed on this branch)
| Commit | Change |
|---|---|
| 92f67588 | Hire dates: were Jan 1 + (sequence % 365) in level order, so mean hire day swung 166–181 with hire count and correlated with level. Now evenly spaced, seeded, level-neutral (mean day 183 every year). |
| 15331c5b | Earned comp prorated over actual days in the year (was /365; leap years paid 366/365). |
| eedcd5cf | Calibration reads Studio's Active metric from fct_workforce_snapshot; minimax scale search (root of max error + min error); `status`/`reason` with evidence-based `infeasible`; `lever_fallback` default False (Studio never sent it, so COLA/merit were silently changed). |
| (this commit) | Scorer on the Active contract; `search_fix` stage; dev results. |

## Parity (execution vs measurement)
- One-cell employee-level diagnosis (pre-fix code): fast calibration build and full Studio simulation agree on all 33,247 employee-year rows and all hire/raise/promotion/termination events; only benefit-enrollment events differ, which feed no comp/headcount column. The old 0.79pp "gap" was measurement (calibrator's methodology A vs scored ALL population), not execution.
- Dev set after fixes, 18 runs (9 cells × seeds 42/101) through the real Studio path (provenance-matched baseline → /calibration/optimize → /calibration/apply → fresh full simulation): **cal_gap = 0.000pp in every run and year**. Active headcount error ≤ 0.01pp. Plausibility failures: 0.

## Accuracy (separate from parity), dev set, stage `search_fix`
| Metric | seed 42 | seed 101 |
|---|---|---|
| Mean max-year comp_err | 0.531pp | 0.771pp |
| Range of max-year comp_err | 0.26–0.91pp | 0.28–1.29pp |
| 2026→2030 CAGR error (all 18) | mean 0.071pp, max 0.134pp | |

Pre-fix reference, balanced_h5_c1_low seed 42: max-year error 1.72pp (prerequisite_repair) → 0.52 (hire_date_fix) → 0.36 (search_fix).

Calibration status: 17 infeasible (spread: no single scale holds every year within the 0.05pp tolerance), 1 not_converged (8-evaluation budget). Converges in 4–8 evaluations, ~10 min per cell including both full simulations. Best scale is seed-stable (e.g. 1.065 vs 1.064).

## Why per-year error remains
1. **Seed noise.** At ~5k employees, the same cell at nearly the same scale differs between seeds by 0.30pp per year on average (max 0.85pp). Noise band (mean paired difference in max-year error) = 0.253pp, above the 0.25pp acceptance bar, so no calibration can meet that bar reliably for one seed.
2. **New-hire ranges are fixed nominal dollars.** `int_workforce_needs_by_level.sql` sets new-hire pay from the range with no annual indexation, while stayers receive merit+COLA each year. Relative new-hire pay erodes, so growth trends down across the horizon (e.g. 4.0, 5.1, 4.2, 2.9%), and one scale cannot flatten a trend. Indexing ranges is a modeling decision, not made here.

## Stage `indexed_cola`: 2% annual new-hire range growth (commit 8cdae2c3, 63e1211e)
New config field `new_hire.salary_growth_rate` (default 0, no effect on existing scenarios or fingerprints). Every dev cell rerun at 2% (= configured COLA) through the same baseline → calibrate → apply → full-simulation path.

| Metric | search_fix (0%) | indexed_cola (2%) |
|---|---|---|
| Mean max-year comp_err, seed 42 / 101 | 0.531 / 0.771pp | 0.620 / 0.853pp |
| Worst run | 1.29pp | 1.06pp |
| CAGR error mean / max | 0.071 / 0.134pp | 0.126 / 0.362pp |
| cal_gap max | 0.000pp | 0.000pp |
| Plausibility failures | 0 | 5 (young c4 cells: level-5 hire pay > 1.3x census level mean in 2029–2030) |

Indexing removed the downward trend but did not improve accuracy overall. Per-year growth now rises toward 2% in the 1%-target cells (e.g. 0.43, 1.39, 1.36, 1.61%) and 2027 is low in every run (mean error 0.72pp). The plausibility flags follow from comparing indexed later-year hire pay with fixed census-year means.

**Structural 2027 step.** `int_workforce_needs.sql` terminates the prior year's hires at the new-hire rate, but year 1 hard-codes `0 AS current_year_hires`, so the census's 2025 hires (1,000 of 5,000 in every synthetic census) are treated as experienced. Experienced terminations are 1,000 in 2026, then 1,185 in 2027 (0.20 x 4,000 + 0.35 x 1,100) and ~23–24% of headcount thereafter. The extra turnover and replacement hiring depress 2027 comp growth in every run. This is current Studio behavior and was not changed.

## Stage `prior_hire_turnover`: census prior-year hires get second-year turnover (commit ac5be11d, 17a796ce)
Year 1 of `int_workforce_needs.sql` now counts census employees hired in the prior year as prior-year hires (new-hire termination rate), matching later years. Starting-pay growth 0%.

| Metric | search_fix | prior_hire_turnover |
|---|---|---|
| Mean max-year comp_err, seed 42 / 101 | 0.531 / 0.771pp | 0.709 / 0.768pp |
| Worst run | 1.29pp | 1.35pp |
| 1%-target cells, mean max-year error | 0.38pp | 0.25pp |
| 4%-target cells, mean max-year error | 0.79pp | 0.98pp |
| CAGR error mean / max | 0.071 / 0.134pp | 0.116 / 0.332pp |
| cal_gap max / plausibility failures | 0.000pp / 0 | 0.000pp / 0 |

The turnover step moved into the unscored 2026 base year, so 2027 is no longer depressed; it is now the highest year in 4%-target cells (e.g. 5.35, 4.70, 3.33, 2.65%). The remaining shape is the monotone decline from fixed nominal new-hire pay, which the 2% `indexed_cola` run was masking with the old 2027 step. Seed-to-seed difference per year: mean 0.37pp, max 0.97pp.

## Stage `turnover_indexed_3pct`: turnover fix + 3% annual new-hire range growth (commit 3dad48f9)
3% chosen as a typical US assumption: 2026 salary-structure adjustments average ~2.6%, total increase budgets 3.4–3.6%, Atlanta Fed job-switcher wage growth ~5.0% and stayer ~3.6% (Aug 2026).

| Stage | Mean max-year err s42 / s101 | 1%-target cells | 4%-target cells | Worst run | CAGR err mean / max | Failures |
|---|---|---|---|---|---|---|
| search_fix | 0.531 / 0.771 | 0.380 | 0.786 | 1.29 | 0.071 / 0.134 | 0 |
| indexed_cola (2%) | 0.620 / 0.853 | 0.699 | 0.755 | 1.06 | 0.126 / 0.362 | 5 |
| prior_hire_turnover (0%) | 0.709 / 0.768 | 0.252 | 0.982 | 1.35 | 0.116 / 0.332 | 0 |
| turnover_indexed_3pct | 0.537 / 0.584 | 0.656 | 0.513 | 0.91 | 0.068 / 0.144 | 0 |

cal_gap max 0.000pp and active headcount error <= 0.01pp in every stage. 4%-target cells: 1 run <= 0.25pp, 5 runs <= 0.5pp; the oldest-workforce cells are nearly flat (e.g. 3.70, 4.30, 3.81, 3.79%). 1%-target cells now rise across the horizon (e.g. 0.09 → 1.91%) because 1% average growth with 3.5% merit + 2% COLA requires new-hire pay far below incumbents, which a market-indexed range does not sustain.

## Stage `backfill_by_level`: hires backfill each level toward the census mix (commit 66267c26)
Diagnosis (on the spent seed-42 holdout): hires were split by the current level mix, so promotions drifted the workforce upward with nothing backfilling vacated levels. Young censuses fell from 67% to 51–54% level 1 in four years, and level-mix shift supplied 1.6–2.8pp of the 2.5pp annual growth while within-level growth was near zero. High-turnover cells failed more because new hires (about 25% of actives, versus 13% at low turnover) carried the drifting mix. Hires now go to each level's shortfall against its start-year census share after expected terminations; promotion vacancies are refilled the next year. The young smoke cell now holds level 1 at 66–67%. Plausibility yardstick now rises with configured starting-pay growth (ORACLE amendment 2026-10-31).

| Dev (18 runs) | turnover_indexed_3pct | backfill_by_level |
|---|---|---|
| Mean max-year err s42 / s101 | 0.537 / 0.584pp | 0.386 / 0.488pp |
| 1% / 4%-target cells | 0.656 / 0.513pp | 0.361 / 0.475pp |
| Worst run | 0.91pp | 0.76pp |
| CAGR err mean / max | 0.068 / 0.144pp | 0.049 / 0.188pp |
| Standard runs passing per-year / compound | 4 / 12, 12 / 12 | 6 / 12, 12 / 12 |
| Runs with failures | 0 | 1 (stress) |

The failure is young_h5_c1_low seed 42: no level-2 hires in 2028 and 2030, because promotions kept level 2 above its census share. Under backfill a full level can legitimately receive no hires; the oracle counts that as a failure, and it is left unchanged. 4%-target cells now run high in 2027 and settle near target (e.g. 4.51, 3.50, 3.50, 3.88%).

## Fresh holdout: stage `two_dial`, seed 13, run once (ORACLE amendment 2026-10-31b)
All 45 cells completed; no failures. No setting was changed after seeing these results.

| Standard cells (30) | s42 pre-fix | s7 backfill | s13 two_dial |
|---|---|---|---|
| Pass per-year (<=0.50pp) | 19 | 18 | 24 |
| Pass compound (<=0.25pp) | 30 | 26 | 30 |
| Mean / worst max-year err | 0.499 / 1.18pp | 0.495 / 1.01pp | 0.326 / 0.78pp |
| CAGR err mean / max | 0.048 / 0.106pp | 0.087 / 0.285pp | 0.092 / 0.221pp |
| Runs with failures | 0 | 4 | 0 |

Stress cells (15): per-year 13, compound 15, mean max-year error 0.250pp (s42 1.036pp, s7 0.411pp). Headcount error <= 0.01pp and cal_gap <= 4e-12pp everywhere.

Every balanced, older and high-turnover standard run passes per-year. All six per-year misses are young, low-turnover cells with the same zigzag (e.g. 4.78, 3.22, 4.02, 4.78%), a likely interaction between the one-year promotion-backfill lag and a slowly churning young workforce. Not investigated on holdout data. Solved starting-pay growth: 0.8–2.4% (1% targets), 2.5–5.3% (2.5%), 4.6–7.1% (4%); scale 0.67–0.99.

## Stage `two_dial`: calibration solves range scale and starting-pay growth (commit 375d5938)
Reason (seed-7 diagnosis): with a stable level mix, average pay growth converges to the starting-pay growth rate, so one scale only front-loads targets away from 3%. Calibration now also solves `new_hire.salary_growth_rate` (bounded 0–8%, start 3%, 12 evaluations). Missing-hire failures now count only for levels with planned hires (ORACLE amendment 2026-10-31b).

| Dev (18 runs) | backfill_by_level | two_dial |
|---|---|---|
| Mean max-year err s42 / s101 | 0.386 / 0.488pp | 0.206 / 0.263pp |
| 1% / 4%-target cells | 0.361 / 0.475pp | 0.206 / 0.248pp |
| Worst run | 0.76pp | 0.50pp |
| CAGR err mean / max | 0.049 / 0.188pp | 0.062 / 0.135pp |
| Standard runs passing per-year / compound | 6 / 12, 12 / 12 | 11 / 12, 12 / 12 |
| Runs with failures | 1 | 0 |

Solved starting-pay growth: 3.6–4.4% for 4%-target cells (two older/balanced seed-42 runs 2.9–3.1%), 1.2–2.5% for 1%-target cells; scale ~1.0 and ~0.76 respectively. Every calibration reports `not_converged`: 14 stopped when the trust region collapsed at the best two-dial point, 4 used the full budget. The residual 0.1–0.4pp is year-to-year noise that the 0.05pp tolerance cannot reach.

## Fresh holdout: stage `backfill_by_level`, seed 7, run once (bars per ORACLE amendments 2026-10-30/31)
All 45 cells completed. No setting was changed after seeing these results.

| Set | Runs | Pass per-year (<=0.50pp) | Pass compound (<=0.25pp) | Mean / worst max-year err | CAGR err mean / max | Runs with failures |
|---|---|---|---|---|---|---|
| Standard, seed 42 pre-fix | 30 | 19 | 30 | 0.499 / 1.18pp | 0.048 / 0.106pp | 0 |
| Standard, seed 7 backfill | 30 | 18 | 26 | 0.495 / 1.01pp | 0.087 / 0.285pp | 4 |
| Stress, seed 42 pre-fix | 15 | 4 | 15 | 1.036 / 1.68pp | 0.049 / 0.115pp | 0 |
| Stress, seed 7 backfill | 15 | 9 | 13 | 0.411 / 0.72pp | 0.063 / 0.097pp | 2 |

Backfill fixed the high-turnover and 2.5%-target misses: high-turnover standard cells pass per-year 9/12 (was 3/12), and 2.5%-target cells 16/18 (was 8/18). It exposed a new pattern in every 4%-target cell: 2027 runs high and growth then declines (e.g. 4.86, 3.38, 3.49, 3.14%); per-year passes 2/12 (was 11/12). Likely cause: with a stable level mix, average pay growth converges toward the starting-pay growth rate (3%), so a constant starting-pay scale reaches other targets only by a one-time front-loaded jump. Before backfill, upward level drift added rising growth that offset this decline. Not investigated further on holdout data.

Failures: six young, low-turnover cells hire no level-2 employees in 3–4 years, because promotions keep level 2 above its census share; the oracle counts empty hiring levels as failures. Ignoring that flag (non-binding, post hoc) the standard compound pass would be 29/30; per-year is unchanged at 18/30.

## Holdout: stage `promo_backfill`, seed 29 (pre-registered in amendment 2026-10-31c, run once)
| Holdout (45 runs) | seed 13 two_dial | seed 29 promo_backfill |
|---|---|---|
| Standard per-year / compound | 24 / 30, 30 / 30 | **30 / 30, 30 / 30** |
| Stress per-year / compound | 13 / 15, 15 / 15 | **15 / 15, 15 / 15** |
| Standard mean max-year err | 0.326pp | 0.183pp |
| Worst run | 0.78pp | 0.38pp |
| Young low-turnover mean max-year err | 0.65pp | 0.18pp |
| Mean year-to-year swing (max-min) | 0.60pp | 0.38pp |
| Mean CAGR err | 0.081pp | 0.057pp |
| Runs with failures | 0 | 0 |

Every run meets the 0.50pp per-year and 0.25pp CAGR bars with no plausibility failures. Seeds differ, so the comparison is indicative rather than paired. 41 runs report not_converged against the 0.05pp search tolerance; the residual is year-to-year noise (the product now labels this "best achievable", PR #1049).

**CHECKPOINT: seed-29 holdout complete; awaiting human review**

## Stage `promo_backfill`: backfill gap counts expected promotions (commit bd23c051)
Diagnosis (spent seed-13 holdout): the backfill gap ignored promotions, so year 1 hired into L2/L3 by census share, promotions overfilled L2, and L2 got no hires from year 2. That one-time shift front-loaded year-2 growth ~1pp in young cells. The gap now subtracts expected promotions out and adds expected promotions in (summed promotion-hazard probabilities). L2 now receives hires every year.

| Dev (18 runs) | two_dial | promo_backfill |
|---|---|---|
| Mean max-year err s42 / s101 | 0.206 / 0.263pp | 0.157 / 0.252pp |
| Mean year-to-year swing (max-min) | 0.47pp | 0.41pp |
| Young cells mean max-year err | 0.30pp | 0.17pp |
| Worst run | 0.50pp | 0.51pp |
| Standard runs passing per-year / compound | 11 / 12, 12 / 12 | 10 / 12, 11 / 12 |
| Runs with failures | 0 | 1 |

The failure is young_h2_c4_high seed 42 (worst-year error 0.05pp): level-5 hire pay is 1.31-1.32x the indexed census mean against the 1.3 plausibility bar (calibrated scale 1.07). older_h2_c4_high seed 101 misses per-year at 0.51pp, as under two_dial. Balanced 4%-high cells are slightly worse (e.g. 0.34 -> 0.50pp), within seed noise.

## Holdout: stage `turnover_indexed_3pct`, seed 42, run once (bars per ORACLE amendment 2026-10-30)
All 45 holdout cells completed; none failed. No setting was changed after seeing these results.

| Set | Runs | Pass per-year (<=0.50pp) | Pass compound (<=0.25pp) | Mean / worst max-year err | CAGR err mean / max |
|---|---|---|---|---|---|
| Standard (2.5%, 4% targets) | 30 | 19 | 30 | 0.499 / 1.18pp | 0.048 / 0.106pp |
| Stress (1% target) | 15 | 4 | 15 | 1.036 / 1.68pp | 0.049 / 0.115pp |

Headcount error <= 0.01pp, cal_gap <= 2.5e-12pp, plausibility failures 0, in every run. Compared with dev (mean 0.537pp, CAGR mean 0.068pp), the holdout is no worse, so the calibration generalizes.

The per-year misses are concentrated, not scattered. Standard cells with low turnover (0.1/0.2) pass 16 of 18, and those with high turnover (0.2/0.35) pass 3 of 12. By target, 4% passes 11 of 12 and 2.5% passes 8 of 18. The six worst standard runs are all 2.5%-target, high-turnover cells; they grow along a rising path (e.g. 1.34, 2.31, 2.49, 3.66%), and one scale cannot flatten it. The calibrator reports these cells as `infeasible`, with the best achievable error (43 of 45 runs), rather than claiming convergence. The 2030 step-up in those cells is a simulation dynamic, not a calibration fault; it was not investigated, to avoid tuning against holdout.

## Not done
Seed 101 holdout (N/A by the oracle). Why high-turnover 2.5% cells rise toward 2030 is not investigated; any change would need a fresh holdout.

## Verification
`python3 scripts/dev.py -- python -m pytest -m fast -q -n 4` (4105 passed); `python3 scripts/dev.py -- ruff check .`; `bun run --cwd planalign_studio typecheck`; `python3 scripts/dev.py -- python campaign_a/score.py --stage search_fix --split dev`; `python3 scripts/dev.py -- python campaign_a/score.py --stage indexed_cola --split dev`; `python3 scripts/dev.py -- python campaign_a/score.py --stage prior_hire_turnover --split dev`; `python3 scripts/dev.py -- python campaign_a/score.py --stage turnover_indexed_3pct --split dev`; `python3 scripts/dev.py -- python campaign_a/score.py --stage turnover_indexed_3pct --split holdout` (4130 fast tests passed after commit 8cdae2c3).

**CHECKPOINT: seed-13 holdout complete; awaiting human review**
