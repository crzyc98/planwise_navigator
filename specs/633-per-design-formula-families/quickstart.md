# Quickstart: Running and Validating a Grandfathering Scenario

The worked example below grandfathers **both** contributions: the legacy cohort keeps a
deferral-based match and a flat core, while post-cutoff hires get a tenure-graded match and an
age-banded core with permitted disparity. Each axis can be varied on its own; this example varies
both so every code path is exercised at once.

## 1. Configure two designs on different families

Activate the checked-in environment first:

```bash
cd /Users/nicholasamaral/Developer/fidelity_planalign
source .venv/bin/activate
```

Copy a working config and add the `plan_design_assignment` and `plan_design_parameters` blocks from
[contracts/config-schema.md](./contracts/config-schema.md):

```bash
mkdir -p /tmp/run633
cp config/simulation_config.yaml /tmp/run633/two_family.yaml
# edit: legacy    -> match deferral_based + core flat
#       new_hires -> match tenure_graded  + core age_banded
#       cutoff 2026-01-01
```

Check the config loads before spending a run on it — C-01 through C-04 all fail here, not mid-run:

```bash
python -c "
from planalign_orchestrator.config import load_simulation_config
cfg = load_simulation_config('/tmp/run633/two_family.yaml')
p = cfg.validated_plan_design_parameters()
print({d: (p.root[d].match.family, p.root[d].employer_core.family) for d in p.design_ids()})
"
```

## 2. Run it in an isolated database

Never in `dbt/simulation.duckdb`.

```bash
DATABASE_PATH=/tmp/run633/two_family.duckdb \
  planalign simulate 2025-2029 \
    --config /tmp/run633/two_family.yaml \
    --database /tmp/run633/two_family.duckdb
```

## 3. Confirm each design used its own family

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT plan_design_id, formula_id, COUNT(*) AS employees,
       ROUND(SUM(employer_match_amount), 2) AS total_match
FROM int_employee_match_calculations
WHERE simulation_year = 2027
GROUP BY 1, 2 ORDER BY 1"
```

Expect one `formula_id` per design, and the two ids to differ.

Then the same for core:

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT plan_design_id,
       COUNT(*) AS employees,
       COUNT(DISTINCT core_contribution_rate) AS distinct_rates,
       ROUND(SUM(employer_core_amount), 2) AS total_core,
       ROUND(SUM(disparity_core_amount), 2) AS total_disparity
FROM int_employer_core_contributions
WHERE simulation_year = 2027 AND eligible_for_core
GROUP BY 1 ORDER BY 1"
```

Expect the `flat` design to show one distinct rate and zero disparity, and the `age_banded` design to
show one rate per populated age band plus non-zero disparity (its `integration_enabled: true`). If
the age-banded design shows a single distinct rate equal to its `contribution_rate`, every employee
fell through to the fallback — the D8 failure the guard in step 5 exists to catch.

## 4. Confirm the assignment stayed sticky (an #631 invariant this must not break)

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT COUNT(*) AS employees_with_multiple_designs FROM (
  SELECT employee_id FROM int_plan_design_assignment_accumulator
  GROUP BY employee_id HAVING COUNT(DISTINCT plan_design_id) > 1)"
```

Expect `0`.

## 5. Confirm exactly-one-arm coverage

The in-model guard aborts the build if this is ever violated, so a completed run already proves it.
To check explicitly:

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT COUNT(*) AS bad_grain FROM (
  SELECT employee_id, plan_design_id, simulation_year
  FROM int_employee_match_calculations
  GROUP BY 1,2,3 HAVING COUNT(*) <> 1)"
```

Expect `0`.

To see the guard fire on purpose, configure a `graded_by_service` design whose bands stop at 30 years
of service in a population containing a 35-year employee, and run. The build must fail with a
diagnostic naming the invocation correlation identifier, employee, design, year, match side, family,
missed service value, and the schedule field to correct; it must not complete with a zero match.

### 5b. Confirm core band resolution (D8)

The in-model guard checks rate provenance before the public schema is projected.
The durable publication-layer check verifies grain and non-null eligible rates:

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT COUNT(*) AS bad_core_rows FROM (
  SELECT employee_id, plan_design_id, simulation_year,
         COUNT(*) AS row_count,
         COUNT(*) FILTER (WHERE eligible_for_core AND core_contribution_rate IS NULL)
           AS unresolved_count
  FROM int_employer_core_contributions
  GROUP BY 1,2,3
  HAVING row_count <> 1 OR unresolved_count <> 0)"
```

Expect `0`. A completed guarded build already proves that every eligible banded-family row matched
exactly one band and never used the flat fallback.

To see it fire on purpose, truncate an `age_banded` design's top band to `max_age: 60` in a population
containing a 64-year-old. The build must fail naming that employee and their age, not quietly pay
them `contribution_rate`. The diagnostic must also include the invocation correlation identifier,
design, year, core side, family, and the age-schedule correction hint.

Also confirm overlapping bands abort rather than dedup (D8/D11): give a design two age bands that
both cover age 45 and re-run. Expect a multiplicity diagnostic, not an arbitrary winner.

## 6. Hand-verify amounts (SC-002)

Pull ten employees per design with their inputs and check the arithmetic by hand:

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT employee_id, plan_design_id, formula_id, applied_years_of_service,
       ROUND(deferral_rate, 4) AS deferral_rate,
       ROUND(eligible_compensation, 2) AS comp,
       ROUND(employer_match_amount, 2) AS match_amt
FROM int_employee_match_calculations
WHERE simulation_year = 2027 AND is_eligible_for_match AND annual_deferrals > 0
QUALIFY ROW_NUMBER() OVER (PARTITION BY plan_design_id ORDER BY employee_id) <= 10
ORDER BY plan_design_id, employee_id"
```

For a `tenure_graded` employee the expected amount is the sum over their band's tiers of
`min(deferral_rate - tier.employee_min, tier.employee_max - tier.employee_min) × tier.match_rate ×
min(comp, 401(a)(17) limit)`, floored at zero per tier. For a `deferral_based` employee it is the same
sum over the design's flat tiers, then capped at `comp × cap_percent`.

For core, pull the same shape and check the band lookup:

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT employee_id, plan_design_id,
       applied_years_of_service,
       ROUND(eligible_compensation, 2) AS comp,
       ROUND(core_contribution_rate, 6) AS rate,
       ROUND(base_core_amount, 2) AS base,
       ROUND(disparity_core_amount, 2) AS disparity,
       ROUND(employer_core_amount, 2) AS core_amt
FROM int_employer_core_contributions
WHERE simulation_year = 2027 AND eligible_for_core
QUALIFY ROW_NUMBER() OVER (PARTITION BY plan_design_id ORDER BY employee_id) <= 10
ORDER BY plan_design_id, employee_id"
```

For a `flat` design without integration, expect `core_amt = min(comp, 401(a)(17) limit) × rate` and
`disparity = 0`. For an `age_banded` design with integration on, `rate` must equal the band matching
the employee's age, `base` is that rate applied to recognized compensation, and `disparity` is
`disparity_rate × (recognized comp above the integration level)`. Confirm the two designs' employees
draw different rates at the same age — that is the grandfathering the feature exists to deliver.

## 7. Canonical deterministic parity (SC-001)

Eight single-design cells: four match families (core held at `flat`) and four core families (match
held at `deferral_based`). Run each on `main` and on the branch into separate isolated databases, then
compare in both directions.

```bash
for FAM in deferral_based graded_by_service tenure_graded points_based; do
  duckdb /tmp/run633/base_$FAM.duckdb "
    ATTACH '/tmp/run633/branch_$FAM.duckdb' AS b (READ_ONLY);
    SELECT '$FAM' AS family,
      (SELECT COUNT(*) FROM (SELECT * EXCLUDE (created_at) FROM main.int_employee_match_calculations
        EXCEPT ALL SELECT * EXCLUDE (created_at) FROM b.int_employee_match_calculations)) AS base_only,
      (SELECT COUNT(*) FROM (SELECT * EXCLUDE (created_at) FROM b.int_employee_match_calculations
        EXCEPT ALL SELECT * EXCLUDE (created_at) FROM main.int_employee_match_calculations)) AS branch_only"
done
```

Then the core side, holding match constant:

```bash
for FAM in flat graded_by_service points_based age_banded; do
  duckdb /tmp/run633/base_core_$FAM.duckdb "
    ATTACH '/tmp/run633/branch_core_$FAM.duckdb' AS b (READ_ONLY);
    SELECT '$FAM' AS core_family,
      (SELECT COUNT(*) FROM (SELECT * EXCLUDE (created_at) FROM main.int_employer_core_contributions
        EXCEPT ALL SELECT * EXCLUDE (created_at) FROM b.int_employer_core_contributions)) AS base_only,
      (SELECT COUNT(*) FROM (SELECT * EXCLUDE (created_at) FROM b.int_employer_core_contributions
        EXCEPT ALL SELECT * EXCLUDE (created_at) FROM main.int_employer_core_contributions)) AS branch_only"
done
```

Run the core comparison twice, once with `integration_enabled: false` and once with it true — phase 6
makes the integration columns always-projected, and the `true` case is where a regression would hide.
Both sides must actually be integrated: pass `integration_enabled=True` to
`apply_single_design_formula` on the branch **and** to `apply_legacy_single_design_formula` on `main`.
Confirm the cell really exercised integration before trusting it —
`SELECT SUM(disparity_core_amount) FROM int_employer_core_contributions` must be non-zero on both
sides. A zero there means integration never engaged and the comparison proves nothing; that is exactly
how the ineligible-disparity regression recorded in `validation-baselines.md` survived the first
sixteen-cell matrix.

Expect `0, 0` everywhere. Repeat for `fct_employer_match_events` and `fct_workforce_snapshot`. Do this
at both the 7.5k and the 60k census. The run-timestamp column is named per table: exclude `created_at`
for the two intermediate models and `fct_employer_match_events`, and `snapshot_created_at` for
`fct_workforce_snapshot` — that column, not a literal `created_at`, is the sole permitted exclusion
there, and comparing the snapshot without excluding it reports every row as different. Use the same seed and the same config on both sides — event
counts are config-dominated, so a cross-config comparison proves nothing.

`created_at` is the only permitted exclusion from canonical equality. Compare every other column in
both directions and by ordered row hash. Do not add another exclusion to make a comparison pass;
change the specification first if a newly introduced field is genuinely nondeterministic.

### A note on comparing against `main`

Phases 3 and 6 change what a *run-global* core config means only in where the value is read from, not
in the value itself. If a core-family comparison shows a diff, check the percentage-to-decimal
conversion first (R-17): the Jinja macro divides by 100 inline, and the relation must do it exactly
once, at export.

Also verify the canonical audit map:

```bash
duckdb /tmp/run633/two_family.duckdb "
SELECT design_formula_families_json FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1"
```

Legacy metadata rows remain readable and return `NULL` for this additive field.

## 8. Timing (SC-005)

Time the 60k single-design run on both sides. The branch must be within 5% of baseline; a larger gap
means an unreferenced family is being compiled, which violates FR-008.

## 9. Test suite

```bash
pytest -m "fast and config" -q
pytest -m integration -k plan_design -q
cd dbt && DATABASE_PATH=/tmp/run633/two_family.duckdb \
  dbt test --select test_plan_design_parameter_relations \
  test_match_formula_arm_coverage test_core_rate_band_resolution --threads 1
```

Then run and time the complete fast suite from the repository root. It must finish in under 10
seconds:

```bash
cd /Users/nicholasamaral/Developer/fidelity_planalign
time pytest -m fast -q
```

## 10. Capacity gate (SC-010)

Run one 100k full multi-year scenario on the default single-threaded path in a separate isolated
database and record peak memory plus completion status:

```bash
DATABASE_PATH=/tmp/run633/capacity_100k.duckdb \
  planalign simulate 2025-2029 \
    --config /tmp/run633/capacity_100k.yaml \
    --database /tmp/run633/capacity_100k.duckdb
```

The run must complete without a memory error. This is a capacity gate, not a replacement for the
60k baseline/branch timing comparison.
