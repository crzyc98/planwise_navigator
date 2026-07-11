# Quickstart: Clear Stale Prior-Run State on Scenario Re-Run

**Feature**: 108-clear-stale-rerun-state | validates issue #419 fixes

All validation runs in **isolated databases** — never `dbt/simulation.duckdb`.

## 1. Fast unit slice (TDD loop)

```bash
source .venv/bin/activate
pytest -m fast tests/unit/orchestrator/test_cleanup_scoping.py -v
```

Covers: default-on purge with absent `setup`, unset-key purge, explicit `clear_tables: false` opt-out, stale accumulator-key deletion, fresh-DB no-op, scenario/plan scoping.

## 2. Integration regression (seeded contamination shape)

```bash
pytest -m integration tests/integration/test_stale_rerun_purge.py -v
```

Seeds an isolated DuckDB with prior-run-shaped rows (old `created_at`, keys the "new run" does not regenerate), drives the orchestrator per-year cleanup, asserts zero survivors and untouched other-scenario/other-year rows.

## 3. dbt label-lineage compile + test

```bash
cd dbt
dbt compile --select fct_workforce_snapshot --threads 1
dbt test --select test_participation_label_lineage --threads 1   # requires a built isolated DB (see §4)
```

## 4. Full end-to-end validation (the literal issue #419 recipe)

```bash
# Run 1: AE ON into a fresh isolated DB
mkdir -p /tmp/run419 && cp config/simulation_config.yaml /tmp/run419/cfg_ae_on.yaml
# edit cfg_ae_on.yaml: enrollment.auto_enrollment.enabled: true (scope: all_eligible_employees)
DATABASE_PATH=/tmp/run419/iso.duckdb planalign simulate 2026-2030 \
  --config /tmp/run419/cfg_ae_on.yaml --database /tmp/run419/iso.duckdb

# Run 2: AE OFF into the SAME database (the re-run that used to contaminate)
cp /tmp/run419/cfg_ae_on.yaml /tmp/run419/cfg_ae_off.yaml
# edit cfg_ae_off.yaml: enrollment.auto_enrollment.enabled: false
date -u +"%Y-%m-%d %H:%M:%S" > /tmp/run419/run2_start.txt
DATABASE_PATH=/tmp/run419/iso.duckdb planalign simulate 2026-2030 \
  --config /tmp/run419/cfg_ae_off.yaml --database /tmp/run419/iso.duckdb
```

### Assertions (SC-001, SC-002, SC-003)

```bash
# (a) No deferral-state rows predate run 2 (SC-001)
duckdb /tmp/run419/iso.duckdb "
  SELECT simulation_year, COUNT(*) AS stale_rows
  FROM int_deferral_rate_state_accumulator
  WHERE created_at < TIMESTAMP '$(cat /tmp/run419/run2_start.txt)'
  GROUP BY 1 ORDER BY 1"
# Expect: zero rows

# (b) Never-enrolled census employees stay not_participating every year (SC-002)
duckdb /tmp/run419/iso.duckdb "
  SELECT COUNT(*) FROM fct_workforce_snapshot s
  WHERE s.participation_status = 'participating'
    AND NOT EXISTS (
      SELECT 1 FROM int_enrollment_state_accumulator esa
      WHERE esa.employee_id = s.employee_id
        AND esa.simulation_year = s.simulation_year
        AND esa.enrollment_status = true)"
# Expect: 0

# (c) Census label only with baseline lineage (SC-003)
duckdb /tmp/run419/iso.duckdb "
  SELECT COUNT(*) FROM fct_workforce_snapshot s
  LEFT JOIN int_enrollment_state_accumulator esa
    ON esa.employee_id = s.employee_id AND esa.simulation_year = s.simulation_year
  WHERE s.participation_status_detail = 'participating - census enrollment'
    AND COALESCE(esa.enrollment_source, 'none') <> 'baseline'"
# Expect: 0
```

### Determinism check (SC-004)

Re-run Run 2 a second time (identical config + seed) and diff participation counts per year — must be identical.

## 5. Full fast suite + regression sweep before PR

```bash
pytest -m fast                    # all fast tests green
pytest -m integration             # integration suite green
```

## Validation Results (executed 2026-07-10)

§4 executed with a 2025–2026 window (exercises the year boundary at lower cost):

| Check | Result |
|---|---|
| SC-001 — deferral-state rows predating run 2 | **0** across all years (compare `created_at` as TIMESTAMPTZ; it is stored with the local offset — a naive UTC string comparison false-positives) |
| SC-002 — participating rows without enrollment-state support | **0** |
| SC-003 — census labels without baseline lineage | **0** (dbt `test_participation_label_lineage`: PASS against the isolated DB) |
| AE-off run auto-enrollment participants | **0** |
| SC-004 — repeat run 2 (identical config+seed) participation counts + deferral sums | identical |

Label distribution after the AE-off re-run: `participating - census enrollment` 10,792 (identical to run 1 — census enrollees stable across configs), `participating - voluntary enrollment` 3,201, `participating - unknown source` **0** (empty in a clean database, as designed — its presence is the contamination signal).

Implementation note discovered during §4: legitimately event-enrolled employees whose enrollment event carries no method (`enrollment_source = 'event_<year>'`, `enrollment_method IS NULL`) take the voluntary-enrollment fallback rather than "unknown source" — under the old label logic they were miscounted as census enrollment; "unknown source" is reserved for participation with no enrollment lineage at all.
