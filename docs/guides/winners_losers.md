# Winners & Losers dollar impact

Winners & Losers compares employer match plus core contributions for active
employees present in both selected scenarios in their latest shared snapshot
year. Employees active in only one scenario are excluded from counts, dollar
totals, averages, and employee detail. Age and tenure groups use Plan A's
demographics; missing bands appear as `Unknown`.

Each employee's Plan A and Plan B total is rounded to cents using half-up
rounding before calculating the delta (Plan B minus Plan A). Positive deltas
are winners, negative deltas are losers, and zero deltas are neutral. Total
increases sum positive deltas; total decreases sum negative deltas and are
displayed as signed amounts. Their sum is net contribution change. Average
change divides net change by all compared employees, including neutral
employees, and rounds to cents. An empty compared population has zero dollar
totals and a zero average. Band and heatmap totals reconcile to the overall
totals for the same population and year.

Click a band label, heatmap cell, or **View all compared employees** to open
read-only detail. Pages contain up to 25 employees in employee ID order and
show Plan A, Plan B, and delta. Group totals describe the entire filtered
population, not just the displayed page. Employee IDs link to the existing
two-scenario timeline workflow; detail adds no name or SSN fields.

The summary and detail include the selected run IDs and comparison year.
Legacy results explicitly report unavailable run IDs. Timeline links open the
scenarios' currently selected results. If a selected run or comparison year
changes between summary and drilldown, the detail API returns HTTP 409; refresh
the comparison to load the new evidence.

## API

- `GET /api/workspaces/{workspace_id}/analytics/winners-losers?plan_a=...&plan_b=...`
- `GET /api/workspaces/{workspace_id}/analytics/winners-losers/employees`
  with `plan_a`, `plan_b`, `comparison_year`, and both run IDs returned by the
  summary (`plan_a_run_id`, `plan_b_run_id`; omit IDs for legacy results).
  Optional `age_band` and `tenure_band` filters intersect. Pagination uses
  `offset` (default 0) and `limit` (default 25, maximum 100).

## Validation

```bash
source .venv/bin/activate
pytest tests/test_winners_losers.py tests/api/test_openapi_contract.py -q
npm run typecheck --prefix planalign_studio
npm run test --prefix planalign_studio -- components/WinnersLosersDetails.test.tsx
```

Service/API tests create disposable synthetic DuckDB databases under pytest's
temporary directory. They never write to the shared development database.
