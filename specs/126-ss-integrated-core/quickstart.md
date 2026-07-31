# Quickstart: Verifying Integrated Employer Core Contributions

**Feature**: `126-ss-integrated-core` | **Date**: 2026-07-30

Every step below uses an **isolated database**. Per `CLAUDE.md` §8, the shared `dbt/simulation.duckdb` is never built into for this work — a half-built shared DB has produced false conclusions on this exact model before.

---

## 1. Fast checks first (no database)

The §401(l) legality checks are pure Python over configuration plus the seed CSV (research R2), so they run in the fast suite:

```bash
pytest -m fast tests/unit/config/test_core_contribution_validation.py -v
pytest -m fast tests/unit/orchestrator/test_config_export.py -v
```

These cover every boundary in the FR-013 factor table (SC-006), both config shapes (direct YAML and Studio `dc_plan`), and the error-message contract. If a factor boundary is wrong, this is where it shows — before anything takes minutes.

---

## 2. Scenario configs

Two scenarios differing **only** in the integration block, so the cost delta is attributable:

```yaml
# scenarios/flat_core.yaml
employer_core_contribution:
  enabled: true
  status: 'flat'
  contribution_rate: 0.03
  integration:
    enabled: false
```

```yaml
# scenarios/integrated_core.yaml
employer_core_contribution:
  enabled: true
  status: 'flat'
  contribution_rate: 0.03
  integration:
    enabled: true
    level_mode: 'ss_wage_base'
    disparity_rate: 0.027
```

```bash
planalign batch --scenarios flat_core integrated_core --clean
```

Each scenario writes its own `.duckdb` in a timestamped directory — the one-DB-per-scenario invariant, and the reason the two runs can be compared without cross-contamination.

---

## 3. The core verification query

```bash
duckdb <integrated_core>.duckdb "
  SELECT simulation_year,
         eligible_compensation > integration_level_applied AS above_wage_base,
         COUNT(*)                    AS employees,
         SUM(base_core_amount)       AS base,
         SUM(disparity_core_amount)  AS disparity,
         SUM(employer_core_amount)   AS total
  FROM int_employer_core_contributions
  GROUP BY 1, 2 ORDER BY 1, 2"
```

**Expected**: the `above_wage_base = false` group has `disparity = 0` in every year (SC-005). The `true` group has non-zero disparity, and `base + disparity = total` in both groups.

Note `int_employer_core_contributions` is a **table** materialization, so it retains only the final simulation year of a run. To inspect an earlier year, run that year as its own range — the same constraint #522's test suite works around by building the boundary year and the migration year as separate runs.

---

## 4. Invariant checks (all must return zero rows)

```bash
DB=<integrated_core>.duckdb

# FR-018 / SC-004 — components reconcile exactly
duckdb $DB "SELECT * FROM int_employer_core_contributions
            WHERE ROUND(base_core_amount + disparity_core_amount, 2)
               <> ROUND(employer_core_amount, 2)"

# SC-005 — no excess ⇒ no disparity
duckdb $DB "SELECT * FROM int_employer_core_contributions
            WHERE excess_compensation = 0 AND disparity_core_amount <> 0"

# FR-009 — disparity is computed off the CAPPED figure, never gross
duckdb $DB "SELECT * FROM int_employer_core_contributions
            WHERE excess_compensation
                > GREATEST(0, LEAST(eligible_compensation, irs_401a17_limit)
                              - integration_level_applied) + 0.01"

# Ineligible employees receive nothing at all
duckdb $DB "SELECT * FROM int_employer_core_contributions
            WHERE eligible_for_core = FALSE
              AND (employer_core_amount <> 0 OR disparity_core_amount <> 0)"
```

---

## 5. Cost reconciliation between the two scenarios (SC-008)

```bash
duckdb -c "
  ATTACH '<flat_core>.duckdb'       AS flat  (READ_ONLY);
  ATTACH '<integrated_core>.duckdb' AS integ (READ_ONLY);
  SELECT
    (SELECT SUM(employer_core_amount)     FROM integ.int_employer_core_contributions)
  - (SELECT SUM(employer_core_amount)     FROM flat.int_employer_core_contributions)  AS cost_delta,
    (SELECT SUM(disparity_core_amount)    FROM integ.int_employer_core_contributions) AS disparity_total"
```

**Expected**: `cost_delta = disparity_total` exactly. If they differ, the base component moved — integration is not behaving as a pure modifier, which is the central design claim (FR-005).

---

## 6. Disabled-parity check (FR-007 / SC-002) — the one that must not be skipped

Byte-identical means the full result set, not aggregates:

```bash
# Build the same scenario on the pre-feature commit and on this branch, then diff.
git stash && planalign batch --scenarios flat_core --clean   # baseline → baseline.duckdb
git stash pop && planalign batch --scenarios flat_core --clean  # feature → feature.duckdb

duckdb -c "
  ATTACH 'baseline.duckdb' AS base (READ_ONLY);
  ATTACH 'feature.duckdb'  AS feat (READ_ONLY);
  SELECT COUNT(*) AS differing_rows FROM (
    SELECT employee_id, simulation_year, eligible_compensation, employer_core_amount
      FROM base.int_employer_core_contributions
    EXCEPT
    SELECT employee_id, simulation_year, eligible_compensation, employer_core_amount
      FROM feat.int_employer_core_contributions
  )"
```

**Expected**: `0`. Repeat for `graded_by_service`, `points_based`, and `age_banded` — SC-002 requires all four shapes, and the shapes are exactly where a refactored amount expression would betray itself.

---

## 7. Integration test suite

```bash
pytest -m integration tests/integration/test_integrated_core_contributions.py -v
```

Covers the three ordering decisions as named tests (SC-007):

| Test | Pins |
|---|---|
| `test_employee_at_integration_level_receives_no_disparity` | boundary is exclusive of excess |
| `test_cap_applies_before_split` | FR-009 — an employee above the 401(a)(17) cap has disparity off the capped figure |
| `test_integration_level_not_prorated_for_mid_year_hire` | FR-010 — partial-year pay vs. full-year level; the counterintuitive zero-disparity result |
| `test_disparity_composes_with_every_core_status` | FR-011 across all four shapes |
| `test_illegal_disparity_rate_fails_validation` | FR-012/FR-014, both config shapes |

---

## 8. Studio check (FR-019 / FR-020 / SC-009)

```bash
planalign studio
```

In the DC Plan section, confirm the **configure** half:
- The "Social Security Integration" toggle appears for **all four** contribution types, not just flat — it modifies whichever base rate the type resolved.
- Selecting `% of the wage base` or `Fixed dollar amount` reveals the level input; `Social Security wage base` hides it.
- Save, reopen, and confirm every setting round-trips — including the disparity rate, which crosses the boundary as a decimal fraction and must come back as the same percentage.
- Set a disparity rate above the §401(l) limit (e.g. 8% on a 3% base) and start a run: it must fail with the applicable limit named, exactly as the YAML path does.

Then the **describe** half:
- The plan design modal shows the integration block with the resolved level and disparity rate.
- The comparison summary reads `"Flat 3% of eligible compensation, plus 2.7% above the Social Security wage base."` — **not** `"Flat 3% of eligible compensation."` Without this, the flat and integrated scenarios carry identical labels while showing different costs, which is the failure the comparison view is least able to survive.
- Turning integration off restores today's wording exactly.
