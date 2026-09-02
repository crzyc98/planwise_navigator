# Quickstart: Validate Per-Design Plan Parameters

All behavioral runs use fresh isolated DuckDB files. Never point these commands at `dbt/simulation.duckdb`.

## Prerequisites

```bash
cd /Users/nicholasamaral/Developer/fidelity_planalign
source .venv/bin/activate
```

## 1. Configuration and export contracts

```bash
pytest \
  tests/unit/orchestrator/test_config_export.py \
  tests/unit/orchestrator/test_config.py \
  tests/test_dbt_var_coverage.py \
  -q
```

Expected: exact design-set validation, deterministic keyed export, legacy scalar export, and the lever inventory guard all pass.

## 2. Macro empty-relation execution

From the dbt directory, run the singular macro contract with an isolated target database and one thread:

```bash
cd dbt
DATABASE_PATH=/private/tmp/plan_design_parameters_empty.duckdb \
  dbt test --select test_plan_design_parameter_relations --threads 1
cd ..
```

Expected: each macro compiles and returns the documented typed schema with zero rows; no invalid `VALUES`, empty `UNION`, or missing-column SQL is produced.

## 3. Multi-design same-family acceptance

```bash
pytest tests/integration/test_plan_design_parameters.py -v
```

The dedicated fixtures run 2025–2027 in pytest `tmp_path` databases and prove:

- exact one-row parameter resolution for every employee/design/year;
- employee-level match amounts tie exactly, at cent precision, to the assigned
  design's compensation, actual deferral rate, tier ceiling, and match rate;
- independent match caps and flat/service-graded core rates;
- independent auto-enrollment default rates, windows, and scopes;
- independent escalation increments/caps across boundary cases;
- independent waiting-day eligibility dates and transitions;
- sticky parameter selection across all years.

The 4% deferral is deliberate: at 6%, both headline formulas produce 3% of pay and could conceal cross-design leakage.

## 4. Single-design hard gate

```bash
pytest \
  tests/integration/test_plan_design_parameters.py \
  -k equivalent_single_design_business_rows \
  -v
```

Expected: for deterministic 40- and 149-row census slices, canonical marts
have bidirectional `EXCEPT ALL` counts of `0/0` and identical ordered row
hashes. Only `created_at` and `snapshot_created_at`
wall-clock columns are excluded. Raw DuckDB file hashes are not an acceptance
measure.

## 5. Targeted quality gates

```bash
ruff check \
  planalign_orchestrator/config/plan_design.py \
  planalign_orchestrator/config/export.py \
  tests/integration/test_plan_design_parameters.py

black --check \
  planalign_orchestrator/config/plan_design.py \
  planalign_orchestrator/config/export.py \
  tests/integration/test_plan_design_parameters.py

pytest -m fast -q
```

For changed dbt models, run `dbt parse` and the targeted model/schema/singular tests from `dbt/` with `--threads 1` and an isolated `DATABASE_PATH` before the full isolated campaign.

## 6. Manual spot-check query

Against the acceptance database, select the employee id, assigned design, compensation, deferral rate, applied tiers/rates, cap, uncapped amount, and final match amount from `int_employee_match_calculations`, then reconcile each design independently using decimal arithmetic. Also confirm the same amount is carried to `fct_employer_match_events` and `fct_workforce_snapshot`.

## Vesting limitation

Vesting is intentionally not claimed by these checks. It remains a request-level Python/API schedule applied globally. The follow-up must define a per-design vesting analytics contract and its own forfeiture tie-outs.

## Recorded validation — 2026-09-02

- Focused configuration/export/workflow regression set: `206 passed`.
- Isolated 2025–2027 two-design acceptance suite: `5 passed in 48.88s`.
- Isolated scalar-versus-keyed parity runs cover 40- and 149-row census sizes
  across four canonical relations: `8 passed in 196.10s`.
- Empty/cardinality macro contract: `1 passed` in a fresh isolated DuckDB.
- Design-aware targeted dbt tests: 401(a)(17), escalation, flat core,
  voluntary-enrollment effective date, and new-hire core proration all passed.
- Keyed match SQL compiled for `deferral_based`, `graded_by_service`,
  `tenure_graded`, and `points_based` families.
- `ruff check` passed and Black formatting was applied to the changed Python
  files.
- Full fast suite: `2652 passed, 895 deselected in 270.44s`.
