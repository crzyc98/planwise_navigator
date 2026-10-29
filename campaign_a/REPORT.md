# Campaign A — in progress
Branch t3/nh-salary-calibration-campaign; base 53b3c32a706bcdf57ddaf71976576bfce67c250c.
Checkout /Users/nicholasamaral/.t3/worktrees/fidelity_planalign/t3-e8a89381.
Oracle and 9 dev/45 holdout split committed d97b8079. Harness and initial synthetic census committed 31a95207; five focused tests passed. No production changes.

First balanced dev seed 42 attempt retained as failed: simulation completed all years, but harness compared /tmp to canonical /private/tmp and falsely rejected publication. Verified matching run UUID and canonical file. Path comparison corrected; failed attempt is not scored. Census preparation correction before matrix baseline: gross compensation must represent earned 2025 pay because Studio annualizes recent hires. V2 prorates that input; original synthetic files and failed attempt remain intact. No target outcomes used in this correction.

Source finding: Studio Analytics defaults to ALL employees; calibrator uses active employees. Oracle scores ALL and retains active-only diagnostics. No measured calibration/full-simulation gap yet.
Baseline/final scores pending for dev seeds 42/101 and holdout seed 42 (holdout seed 101 N/A). No kept production changes, reverted hypotheses, or infeasibility conclusions. No campaign stop criterion met. Analyst recommendation pending measured evidence.

First corrected cell: baseline completed (105s), calibration completed without convergence (539s; max active annual error 1.72pp), applied full failed (25s). Independent Terra audit and lead raw-table verification confirm decimal ages from apply cause MAKE_DATE binder failure and no applied snapshot. Primary applied score/gap undefined. Baseline ALL max comp error 5.169118pp and HC error 1.584709pp are diagnostics, not an applied score. Remaining baseline matrix queued; no tuning yet.
