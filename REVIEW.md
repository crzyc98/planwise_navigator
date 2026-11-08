# Review guide

Read `CLAUDE.md` and `dbt/CLAUDE.md` first. This file says what matters when reviewing this repo.

## What failure looks like here

- **Results stop being reproducible.** Same seed + inputs must give the same events. Watch for unseeded randomness, set/dict ordering leaking into output, `ORDER BY`-less window functions, and wall-clock values in event rows.
- **Events get mutated.** `fct_yearly_events` rows are appended, never updated or deleted in place.
- **Wrong compensation basis.** Core, match and deferrals use the accumulator's `prorated_annual_compensation` (earned, time-weighted), not annual salary. The headline cost % uses the all-employee denominator on purpose.
- **Cross-year state breaks.** A change that works for one year but loses or double-counts state in year 2+ (accumulators, enrollment, tenure, terminations).
- **Shared state gets written.** Code or tests that write to `dbt/simulation.duckdb`, bypass `get_database_path()`, or let one scenario's DB read another's.
- **Saved work changes silently.** A new Studio or config default that overwrites saved workspaces, scenario files or explicit user values. New defaults apply to new workspaces only.
- **Security defaults get weaker.** The API's loopback bind, `PLANALIGN_API_TOKEN`, path handling on uploads and run IDs.
- **dbt runs that can't work in production:** missing `--threads 1`, incremental models without a correct unique key, or SQL that only passes on the small dev census.
- **Docs that lie.** Docs, guides or comments that describe behavior the code doesn't have.

## Rules for findings

- Every finding names a `file:line` and a concrete scenario: the input or state, and the wrong output or crash.
- Tag each finding **Important** (wrong results, data loss, security, crash), **Nit**, or **Pre-existing** (a real bug this PR didn't introduce). Only Important findings go inline, because inline threads block merge. Nits and Pre-existing findings go in the summary.
- Post at most 3 nits. Don't comment on style, formatting or naming that ruff and eslint accept.
- Flag the bug class, not one line: if the same mistake appears elsewhere in the diff, list every location.
- Don't repeat a finding already posted on the PR.

## Skip

`data/`, `var/`, `workspaces/`, `runs/`, `*.duckdb`, `dbt/seeds/*.csv` contents, `planalign_studio/package-lock.json`, `uv.lock`, `.specify/`, and generated files.

## Summary

Start with the count, for example "2 Important, 1 Nit". If nothing needs fixing, say "No issues found" and stop.
