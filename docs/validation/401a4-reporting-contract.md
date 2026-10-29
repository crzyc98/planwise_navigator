# 401(a)(4) reporting contract correction

This intentionally changes successful `test_result` responses from `pass`/`fail` to `unavailable`. Execution errors remain `error`. Clients must handle unavailable explicitly, never as fail or pass. The engine has not implemented statutory rate-group coverage or collected all required plan facts.

`heuristic_result` preserves the legacy average/median comparison when computed; it is null for missing groups or no applicable contributions. It is not a qualification determination. Employee details and average/median contribution rates remain available for the selected contributing population. This population is not the full statutory nonexcludable population.

Legacy compatibility fields remain: `applied_test=ratio` selects average-rate ratio and `general` selects median-rate ratio; neither names a statutory test. `ratio` is the NHCE/HCE average-rate ratio. `ratio_test_threshold=0.70` is the old heuristic threshold. `margin` is the selected heuristic ratio minus 0.70. Ratios and margins are meaningful only when `heuristic_result` is non-null; default zeros otherwise are not observations. UI omits those default values and does not render heuristic pass/fail compliance cues.

The independent counterexample has HCE rate 10% and four NHCE rates 9%, 9%, 9%, 1%. Its average ratio is 70% and its median ratio 90%, but none of the NHCEs belongs to the HCE's rate group. This disproves the equivalence of the heuristic and rate-group coverage. It does not establish failure of every permitted statutory alternative.

Original evidence: main checkout `validation_campaign/terra/public_oracle.json` and `public_run.txt`. Expectations are preserved. Fix regression: `tests/test_ndt_401a4.py`; rendering regression: `planalign_studio/components/NDT401a4.test.tsx`. The UI test's initial 70.0% text assertion was corrected to the existing formatter's two-decimal 70.00%; no numerical oracle or tolerance changed.
