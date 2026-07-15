# Quickstart: Multi-Year Invariant Suite + Determinism Test

## Run the whole suite locally

```bash
source .venv/bin/activate
pytest -m multi_year_invariants -v
```

Expected: two 3-year simulations (~150-employee census) run into tmp DuckDBs, then all invariant and determinism tests pass. Budget: < 10 minutes. The shared dev DB (`dbt/simulation.duckdb`) is never touched.

## Run only the invariants (single simulation, faster)

```bash
pytest tests/integration/test_multi_year_invariants.py -v
```

## Run only the determinism check

```bash
pytest tests/integration/test_determinism.py -v
```

## Debug a failure

1. Read the failure message — it names the invariant, the guarded issue (e.g. #418), and shows up to 20 violating rows with employee_id and simulation_year.
2. The isolated DB(s) are preserved at `var/test-artifacts/113/` (locally) or as the `multi-year-invariants` workflow artifact (CI). Inspect directly:

```bash
duckdb var/test-artifacts/113/run_a.duckdb \
  "SELECT * FROM fct_yearly_events WHERE employee_id = 'INV_EMP_0042' ORDER BY simulation_year, event_sequence"
```

## Change the reference census or config

- Census: edit `tests/fixtures/invariant_census.csv` (or regenerate via `python scripts/generate_invariant_census.py`). The fixture self-test enforces band/level/enrollment coverage minimums — it will fail if an edit loses coverage.
- Config: edit `tests/fixtures/invariant_config.yaml`. Keep the levers that make invariants bite (AE on, escalation cap binding by 2027, multi-tier match, positive growth).
- Either change alters simulation output: expect to review invariant results, not just re-run.

## Add a new invariant

1. Add an `Invariant(...)` entry in `tests/invariants/catalog.py` with a violation-returning SQL query (empty result = pass; include `employee_id`, `simulation_year` columns).
2. Document it in `specs/113-invariants-determinism/contracts/invariant-catalog.md` (names are append-only).
3. Prove it red: introduce the defect it guards on a scratch branch and confirm it fails with a useful diagnostic.

## Exempting a field from the determinism diff

Only run-bookkeeping wall-clock fields qualify. Add the `(table, column, justification)` entry in `tests/invariants/comparison.py` **and** the contract table in `contracts/invariant-catalog.md` in the same PR. `event_id` is deliberately not exempt.
