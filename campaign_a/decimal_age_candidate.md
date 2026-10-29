> Historical proposal, retained as evidence. Implemented by prerequisite repair commit 4616f452; the unapplied/proposed status below describes the earlier bounded investigation.

# Decimal age candidate — unapplied proposal

Scope: one production annotation (`AgeWeight.age: float` → `int`) plus one new focused regression test. No router/provenance changes, SQL casts, refactor, config changes, or application to production. Current code already has an AgeWeight TypedDict rather than the older Dict[str, float]; its float age annotation retains the proven coercion defect.

Evidence: `campaign_a/cells/balanced_h5_c1_low.json` records integer input ages 22/25, float best-parameter ages 22.0/25.0, completed baseline, and failed applied run. Applied run `42b12882-0eaf-4146-9569-6f36e97cd4ce` simulation.log under `/tmp/nhcal/balanced_h5_c1_low/baseline_seed_42_v2/workspaces/b47dfe41-332b-4c9d-8d4c-dfcf7f7e15a9/scenarios/471104b5-f273-456c-a6b8-aed634458f27/runs/` reports MAKE_DATE(DECIMAL(22,1), ...) binder failure in int_plan_eligibility_determination for 2026. No census or database was modified or queried for this proposal.

Root cause: Pydantic coerces input ages to float; the calibration runner injects these dictionaries directly into dbt vars and apply persists them directly. int_hiring_events interpolates age as an uncast SQL literal. Decimal literals propagate decimal employee ages into eligibility date arithmetic. Canonicalizing age at the shared parameter boundary ensures calibration evaluation and applied candidate use the same domain integer, including legacy integral float inputs. Fractional ages are rejected rather than truncated. Weights remain floats. API provenance checks are untouched.

Assumption: age buckets represent whole completed years, as documented by the production export and hiring SQL. This intentionally narrows fractional-age acceptance and changes the generated API age schema from number to integer; schema snapshots/generated clients should be refreshed by the eventual authorized implementation using the repository tooling. They were not changed in this bounded proposal.

## Executed focused pre/post validation

Temporary copies are individual modules, not a checkout. The harness imports the chosen module copy under its canonical module name before loading the router/test; imported production source files are never edited. Production hiring CTE text is read and rendered; DuckDB runs only in memory. The test covers integer and integral-float ages 22/25 through parameter validation, JSON round-trip, actual router merge, YAML round-trip, production hiring age CTE, and MAKE_DATE arithmetic; fifth case requires rejecting 22.5.

Exact commands from repository root:

```bash
python3 scripts/dev.py --check
python3 scripts/dev.py -- python /tmp/nhcal/proposal/run_focused.py /tmp/nhcal/proposal/calibration_runner.before.py > /tmp/nhcal/proposal/before.log 2>&1
# Expected exit 1: 5 failed; four decimal MAKE_DATE BinderExceptions and one missing fractional-age rejection.
python3 scripts/dev.py -- python /tmp/nhcal/proposal/run_focused.py /tmp/nhcal/proposal/calibration_runner.after.py > /tmp/nhcal/proposal/after.log 2>&1
# Observed exit 0: 5 passed, 28 pre-existing Pydantic deprecation warnings.
git apply --check campaign_a/decimal_age_candidate.patch
git diff --exit-code -- planalign_orchestrator planalign_api planalign_core tests dbt config
```

Raw evidence and the loader/test remain at `/tmp/nhcal/proposal/`. The before run reproduced DECIMAL(13,1) in the bounded expression (production has DECIMAL(22,1)); the relevant binder incompatibility is identical. An initial harness extraction included trailing SQL comments and failed parsing; that extraction was corrected before the recorded pre/post comparison. No full or multi-year candidate simulation was executed; transferability, cross-year invariants, numeric score and acceptance remain unestablished. Baseline numeric score is undefined for this proposal. It is not a kept hill-climb iteration and acceptance is not authorized.

After a separately authorized application, run the added test normally:

```bash
python3 scripts/dev.py -- python -m pytest tests/test_calibration_decimal_age.py -q
```

The baseline matrix already has unrelated campaign file modifications; they were preserved. Production git diff is empty. No commits, network, installs, or subagents.

## Evidence SHA-256

- `calibration_runner.before.py`: `7639a1768155a046e392efb60ee1f4df7f9a9953ddbba019c4402e77e6f83afa`
- `calibration_runner.after.py`: `5d4833647bf8c2ef3b87a87498a8207c05d95e4f05925f568d783749ec736c02`
- `test_calibration_decimal_age.py`: `02573f413d4c09a46952429cf9eff1291c2dcd3b1cee17a8f3864d6970ac8d1e`
- `run_focused.py`: `cbf28ba0c91eaec9e8171e2c605f07be6c7f409a8c6e8c97c96259a2c0823b2e`
- `before.log`: `7eb1263903d0382a8bd073adcfacdccf3e5eee2e4d55eb8a0891463379e48e72`
- `after.log`: `864f02ebdcfabd6659d6bd50861915ac8ee0ca9e420cd9abce537154b7e5f3ce`
