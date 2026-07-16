# Quickstart: Employee Event Timeline

**Feature**: 114-employee-event-timeline

## Prerequisites

```bash
source .venv/bin/activate          # project venv (Python 3.11)
planalign health                   # sanity check
```

## Build an isolated validation database (never the shared dev DB)

```bash
mkdir -p /tmp/run114
cp config/simulation_config.yaml /tmp/run114/cfg.yaml
DATABASE_PATH=/tmp/run114/iso.duckdb \
  planalign simulate 2025-2027 --config /tmp/run114/cfg.yaml --database /tmp/run114/iso.duckdb
```

For US5 (comparison), build a second DB from the same census with a plan-design difference (e.g., flip auto-enrollment or the match formula in the copied config), or use `planalign batch --scenarios baseline high_growth --clean` to get two isolated scenario DBs.

## Run the backend tests

```bash
pytest -m fast tests/test_timeline_service.py -v          # unit: merge/order/pagination/filters
DATABASE_PATH=/tmp/run114/iso.duckdb pytest tests/test_timeline_api.py -v   # integration
```

## Exercise the API directly

```bash
planalign studio --api-only &
BASE="http://localhost:8000/api/workspaces/<ws>/scenarios/<scn>"

curl "$BASE/employees?q=EMP_2025"                                  # autocomplete
curl "$BASE/employees?status=terminated&year=2026&has_escalations=true"  # attribute filter
curl "$BASE/employees/EMP_2025_001/timeline?start_year=2025&years=3"     # timeline page
```

## Verify in Studio

```bash
planalign studio
```

1. **US1**: open `/#/timeline`, pick the scenario, type a partial ID → suggestions appear; select one → year-grouped timeline, oldest-first.
2. **US2**: each year shows the state strip; cross-check one year against
   `duckdb -readonly <scenario.duckdb> "SELECT * FROM fct_workforce_snapshot WHERE employee_id='...' AND simulation_year=..."`.
3. **US3**: copy the URL (`/#/timeline/<ws>/<scn>/<emp>`), open in a fresh tab → lands populated.
4. **US4**: clear the search, apply filters (status/level/year/enrolled/escalations) → paginated list; click a row → timeline.
5. **US5**: on a timeline, pick a second scenario → two labeled columns aligned by year; add `?compare=<scn2>` to the URL and reload → same view.

## Acceptance-critical checks (from Success Criteria)

- **SC-002 exactness**: for one employee, diff the API's event list against
  `duckdb -readonly <db> "SELECT event_id FROM fct_yearly_events WHERE employee_id='...' UNION ALL SELECT event_id FROM fct_employer_match_events WHERE employee_id='...'"` — must match exactly.
- **SC-003**: seed an inconsistency (or find one) and confirm it's spottable from the year strip alone.
- **SC-007**: with the two-scenario pair, confirm the divergence year is identifiable side-by-side and each column matches its own DB.

## Key implementation files

| Path | Role |
|------|------|
| `planalign_api/routers/timeline.py` | Endpoints |
| `planalign_api/services/timeline_service.py` | Queries, merge, pagination |
| `planalign_api/models/timeline.py` | Pydantic models |
| `planalign_studio/components/timeline/` | Page + subcomponents |
| `planalign_studio/services/api.ts` | Client functions + TS interfaces |
| `specs/114-employee-event-timeline/contracts/timeline-api.md` | The contract tests assert against |
