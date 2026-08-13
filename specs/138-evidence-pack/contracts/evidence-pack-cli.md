# CLI Contract: `planalign evidence-pack`

## Invocation

```text
planalign evidence-pack SCENARIO_PATH \
  --metric METRIC \
  --base-year YYYY \
  --target-year YYYY \
  [--output FILE] \
  [--force]
```

`SCENARIO_PATH` is a scenario directory. The command resolves and validates its
`current_result.json` once and binds that run for the entire command. For an
established legacy scenario without a pointer, it may read
`SCENARIO_PATH/simulation.duckdb` and must include a `legacy_result` warning.
It never falls back to the shared project database or searches unrelated
workspaces.

## Arguments and options

| Input | Type | Required | Behavior |
|---|---|---:|---|
| `SCENARIO_PATH` | existing directory | yes | Scenario containment root; not a database file |
| `--metric` | canonical metric enum | yes | One of the six IDs in the API contract |
| `--base-year` | integer | yes | Must be earlier than target and present in result |
| `--target-year` | integer | yes | Must be later than base and present in result |
| `--output` | file path | no | Atomically writes canonical Markdown; default is stdout |
| `--force` | flag | no | Permits replacing an existing output file; has no effect without `--output` |

## Output behavior

- Without `--output`, stdout is exactly the canonical Markdown contract in
  [evidence-pack-text.md](./evidence-pack-text.md), encoded as UTF-8 with one
  trailing newline. Rich markup, progress, and diagnostics must not contaminate
  it.
- With `--output`, the command atomically writes those same bytes and prints the
  output path and bound run ID as a diagnostic. It refuses an existing target
  unless `--force` is provided.
- The output path must be outside the resolved result run directory. The
  command never writes to the scenario archive or database.
- Repeated successful invocations against the same bound run/metric/years are
  byte-identical.
- The structured figures and Markdown bytes are produced by the same shared
  service/renderer used by the API; the CLI contains no decomposition SQL.

## Exit codes

| Code | Meaning | Required message content |
|---:|---|---|
| `0` | Pack produced | Bound run/scenario when writing a file |
| `1` | Unexpected generation failure | Concise operation and cause |
| `2` | Invalid input or unsupported metric/year/schema | Name invalid/missing item; include available year range or missing columns |
| `3` | Scenario/result not found | Exact scenario path and missing result condition |
| `4` | Result identity/integrity/lock conflict | State that the source cannot be read safely; no retry/wait |

Mathematically undefined drivers are not command errors. The command succeeds
and reports the undefined reason and resulting residual. If an endpoint metric
itself is undefined because its denominator is zero, the request is unsupported
and exits `2` with the reason.

## Privacy and read-only guarantees

- Output and SQL result columns contain aggregates and structural metadata only.
- Exact citation SQL may use `employee_id` inside joins but never projects it.
- Absolute source paths, usernames, SSNs, birth dates, hire dates, and employee-
  level values are prohibited from stdout/output.
- Database connections are short-lived and `read_only=True`; no temp table,
  cache, archive file, or result-table write is permitted.
