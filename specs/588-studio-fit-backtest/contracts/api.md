# API Contract: Fit & Backtest (#588)

All routes are mounted under `/api/workspaces` and protected by `require_api_token`.

| Method | Path | Success | Errors |
|---|---|---|---|
| POST | `/{ws}/fit-history` (multipart `files[]`, 2–5 files) | 201 HistorySet | 404 workspace · 400 extension or no files · 413 size · 422 snapshot validation (message from `load_snapshots`) |
| GET | `/{ws}/fit-history` | 200 list[HistorySet] (newest first) | 404 |
| GET | `/{ws}/fit-history/{history_id}` | 200 HistorySet (re-hashed and re-validated) | 404 · 422 if the files became invalid |
| DELETE | `/{ws}/fit-history/{history_id}` | 204 | 404 · 409 if a queued/running job uses it |
| POST | `/{ws}/param-fits` (ParamFitRequest) | 202 ParamFitJob (queued) | 404 workspace, history or scenario · 422 validation or invalid split · 409 backtest already running in the workspace |
| GET | `/{ws}/param-fits` | 200 list[ParamFitJobSummary] (newest first) | 404 |
| GET | `/{ws}/param-fits/{job_id}` | 200 ParamFitJob (+ `result` when completed) | 404 |
| POST | `/{ws}/param-fits/{job_id}/cancel` | 200 ParamFitJob (cancelled) | 404 · 409 if already terminal |
| GET | `/{ws}/param-fits/{job_id}/reports/{kind}` where kind ∈ {`fit`, `scorecard`} | 200 `text/markdown` | 404 (missing, or job not completed) |
| GET | `/{ws}/param-fits/{job_id}/apply-preview?source_scenario_id=` | 200 ApplyPreview | 404 · 409 if the job is not completed or the pack is stale |
| POST | `/{ws}/param-fits/{job_id}/apply` (ApplyRequest) | 201 Scenario | 404 · 409 `{detail, stale: [...]}` for fingerprint or history drift · 409 `{detail, suggested_name}` for a name collision · 422 `{detail, missing_acknowledgements: [...]}` |

## Invariants

- A launch never blocks on the job: the response is sent before the child process starts its work.
- No endpoint reads or writes `dbt/simulation.duckdb`, and none reads or writes any scenario's run databases.
- Apply never modifies the source scenario's `scenario.json`, `overrides.yaml`, or runs.
- Error `detail` strings for 500s are sanitized (`sanitize_job_error`). CLI user-facing messages are passed through only for classified 4xx failures.
