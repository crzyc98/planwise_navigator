# Quickstart: Validating the Match-Magnet Dial & Ceiling Fix

> **Rule:** validate in an **isolated** database — never `dbt/simulation.duckdb`. Cover the no-AE + stretch-match edge config and run the **full multi-year** horizon (cross-year deferral drift is invisible in a single-year run).

## 0. Prerequisites

```bash
source .venv/bin/activate
python -c "import planalign_orchestrator"   # auto-installs sqlparse token fix
```

## 1. Build two isolated scenarios that differ only in match ceiling (US1 / SC-001/002)

Create `scenarios/match_ceiling_6.yaml` and `scenarios/match_ceiling_10.yaml`: no auto-enrollment, a stretch/simple match at **50% on the first 6%** vs **50% on the first 10%**, voluntary enrollment rate set to hold ~baseline participation. Keep `random_seed` identical.

```bash
planalign batch --scenarios match_ceiling_6 match_ceiling_10 --clean
# → writes match_ceiling_6.duckdb and match_ceiling_10.duckdb in a timestamped dir
```

## 2. Compare voluntary-deferral distributions

```bash
for db in match_ceiling_6 match_ceiling_10; do
  echo "== $db =="
  duckdb "<run-dir>/$db.duckdb" "
    SELECT simulation_year,
           ROUND(AVG(employee_deferral_rate), 4) AS avg_deferral,
           ROUND(AVG(CASE WHEN employee_deferral_rate >= 0.10 THEN 1 ELSE 0 END), 4) AS share_10pct_plus
    FROM fct_workforce_snapshot
    WHERE employment_status = 'active' AND employee_deferral_rate > 0
    GROUP BY 1 ORDER BY 1"
done
```

**PASS criteria**:
- `avg_deferral` is strictly higher in `match_ceiling_10` than `match_ceiling_6` (SC-001).
- `share_10pct_plus` is strictly higher in `match_ceiling_10` (SC-002).
- (Pre-fix, both columns are identical across the two DBs — the bug.)

## 3. Sweep the dial (US2 / SC-003)

Clone `match_ceiling_10` to scenarios with `match_magnet.snap_probability` at e.g. 0.20, 0.45, 0.80 (and one with `enabled: false`). Re-run via `planalign batch`. Confirm:
- Higher `snap_probability` → higher share at the ceiling and higher `avg_deferral`.
- `enabled: false` → no rows snapped to the ceiling (rates match demographic assignment).

## 4. Reach the configured ceiling (US3)

Scenario with match ceiling 10% and `match_magnet.max_deferral_rate: 0.10`: confirm snapped enrollees appear **at** 10% in the distribution (not capped below).

## 5. Backward-compatibility regression (SC-004)

Run an existing scenario that sets **none** of the new fields against an isolated DB; compare the voluntary-deferral distribution to a pre-change baseline build of the same scenario. They MUST match exactly.

## 6. Reproducibility (SC-005)

Run the same scenario twice into two isolated DBs with the same seed; the deferral distributions MUST be identical.

## 7. Unit / dbt tests

```bash
pytest tests/test_config_export_match_magnet.py -v        # new var export + always-on ceiling
DATABASE_PATH=<run-dir>/match_ceiling_10.duckdb \
  cd dbt && dbt test --select int_voluntary_enrollment_decision int_proactive_voluntary_enrollment --threads 1
```

## Mode coverage (clarification B)

Repeat step 2's comparison with `employer_match_status` set to `graded_by_service`, `tenure_graded`, and `points_based` (varying each mode's `max_deferral_pct`) to confirm the per-employee ceiling drives snapping in all match modes.
