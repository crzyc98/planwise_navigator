# Scenario comparison read failures

`GET /api/workspaces/{workspace_id}/comparison` compares all requested scenarios.
If any database is missing, unreadable, corrupt, lacks a required table/column,
or has no snapshot results, the endpoint returns HTTP 409 with
`detail.scenario_id` and `detail.reason`. It returns no partial comparison or
summary deltas. The service raises `ComparisonDataError` for these failures.
Completed scenario status alone does not establish that results remain readable.

Older snapshots missing only `prorated_annual_compensation` can still be compared.
Their workforce `avg_compensation` and DC plan `employer_cost_rate` values and
deltas are `null`. Other query failures still fail the comparison. Successfully
observed zeroes remain zero and can produce a legitimate −100% delta.

Run the synthetic regression tests against disposable databases:

```bash
source .venv/bin/activate
pytest tests/test_comparison_read_failures.py tests/test_comparison_dc_plan.py -q
```
