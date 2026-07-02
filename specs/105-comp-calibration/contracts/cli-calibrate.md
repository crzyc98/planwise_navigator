# CLI Contract: `planalign calibrate`

Registered in `planalign_cli/main.py` as `@app.command("calibrate")`, implemented in `planalign_cli/commands/calibrate.py:run_calibration()`. Mirrors `simulate.py` conventions (Rich output, `parse_years`, `validate_year_range`).

## Synopsis

```text
planalign calibrate <year-range> [OPTIONS]
```

`<year-range>`: `2025-2029` (multi-year) or `2025` (single year). Required positional argument.

## Options

| Flag | Type | Default | Meaning |
|------|------|---------|---------|
| `--config`, `-c` | path | auto-discovered | Simulation config YAML (same as `simulate`) |
| `--database` | path | isolated `<calibration>.duckdb` | Target DB. Omitted → isolated DB (never the shared dev DB) |
| `--target-growth` | float | from config | Target avg-comp YoY growth (e.g. `0.035`) for the delta column |
| `--cola` | float | from config | Override COLA rate |
| `--merit` | float | from config | Override merit budget |
| `--new-hire-mix` | str/path | from config | New-hire age/level distribution override |
| `--interactive` | bool | false | Open a re-tune loop (FR-009) |
| `--threads` | int | 1 | dbt threads (work-laptop default 1) |

## Behavior

1. Parse + validate the year range (`end ≥ start`, sane years) → clear error on failure (exit 2).
2. Resolve target DB; default to isolated calibration DB seeded from / pointing at a fully-built DB.
3. **Prerequisite guard**: verify DC tables required by `fct_workforce_snapshot`/`fct_yearly_events` exist. Missing → actionable error, exit non-zero, **no build attempted** (FR-011/SC-005).
4. For each year: run the comp-only workflow variant (`build_calibration_year_workflow`) via the dbt runner with `--select <comp model list>` and `--vars` from `to_dbt_vars()`.
5. Build/read `fct_compensation_growth`; assemble `PerYearCompensationResult` rows.
6. Render a Rich table.

## Output table (stdout)

| Year | Avg Comp | YoY Growth | Target | Δ vs Target | Headcount | NH Gap |
|------|----------|-----------|--------|-------------|-----------|--------|
| 2025 | $98,400 | — | 3.5% | — | 10,000 | -$12,100 |
| 2026 | $101,900 | 3.6% | 3.5% | +0.1% | 10,250 | -$11,800 |

- First year shows `—` for growth/delta (undefined).
- `--interactive`: after each render, prompt for new param values, re-run, re-render until the user exits.

## Exit codes

| Code | Condition |
|------|-----------|
| 0 | Success |
| 2 | Invalid arguments (year range, param out of range) |
| 3 | Prerequisite guard failure (DC tables missing) |
| 1 | Other runtime/build failure |

## Invariants

- Default run leaves the shared `dbt/simulation.duckdb` byte-identical (SC-004).
- `fct_compensation_growth` avg-comp / YoY columns are **exact** vs. a full `simulate` run under the same config (SC-002).
