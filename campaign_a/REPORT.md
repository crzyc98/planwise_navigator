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

## Not done
Holdout (45 cells) not run. Decisions pending: the first-year prior-hire turnover rule, the analyst growth-rate choice, and the per-year acceptance bar. Needs ~11 GB unless databases are deleted after scoring.

## Verification
`python3 scripts/dev.py -- python -m pytest -m fast -q -n 4` (4105 passed); `python3 scripts/dev.py -- ruff check .`; `bun run --cwd planalign_studio typecheck`; `python3 scripts/dev.py -- python campaign_a/score.py --stage search_fix --split dev`; `python3 scripts/dev.py -- python campaign_a/score.py --stage indexed_cola --split dev` (4130 fast tests passed after commit 8cdae2c3).

**CHECKPOINT: awaiting human review**
