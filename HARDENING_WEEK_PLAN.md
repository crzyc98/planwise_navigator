# PlanWise Navigator — One-Week Production Hardening Plan

Audience: you and me working together this week to get the system production‑ready, resilient, and auditable without broad refactors.

Goals
- Stabilize multi‑year runs with clear recovery and checkpoints.
- Tighten config, contracts, and data‑quality gates to prevent silent drift.
- Improve observability and runbooks so incidents are easy to triage.

Assumptions
- Event‑sourced design stays intact; we never mutate `fct_yearly_events`.
- We run dbt from `./dbt` and use the DuckDB at `dbt/simulation.duckdb`.
- Network is restricted; no new packages unless explicitly approved.

Deliverables (by week’s end)
- Preflight DB backup + run metadata stamping for every run.
- Stronger config validation and explicit identifiers (scenario_id, plan_design_id) surfaced in CLI.
- Data‑quality “tripwire” tests for hiring demand, contributions, and match presence.
- Checkpoint/resume sanity with quick verification script and a concise runbook.
- CSV/console summaries for multi‑year runs plus minimal on‑disk logs for audits.

Day‑by‑Day Plan

Day 1: Safety Nets (Backups + Run Metadata)
- Add preflight snapshot: copy `dbt/simulation.duckdb` to `simulation_backup.duckdb` before each multi‑year run when file exists.
- Stamp run metadata: ensure `int_simulation_run_log` is written before/after runs with scenario, plan, years, and hashes.
- Verify
  - Command: `python -m navigator_orchestrator.cli validate -c config/simulation_config.yaml`
  - Dry run: `python -m navigator_orchestrator.cli run --dry-run -v`
  - Check `reports/` and `.navigator_checkpoints/` are updated.

Day 2: Config Contracts & Identifier Hygiene
- Enforce identifiers optional toggle (no behavioral changes by default): produce a clear error if missing when flag used.
- Add a lightweight config linter (analysis only): confirm required keys and sensible bounds; print warnings, not failures.
- Verify
  - `python -m navigator_orchestrator.cli validate --enforce-identifiers` (should fail if missing ids).
  - Ensure `to_dbt_vars` parity with YAML so timing/eligibility vars map correctly.

Day 3: Data‑Quality Tripwires (dbt‑side)
- Tripwire 1: Hiring demand vs hires
  - If `int_workforce_needs_by_level.hires_needed > 0` but `int_hiring_events = 0`, flag/force targeted rebuild.
- Tripwire 2: NULL compensation on hires
  - Detect and rebuild `int_workforce_needs_by_level -> int_hiring_events` path.
- Tripwire 3: Contributions/match presence
  - If `int_employee_contributions.annual_contribution_amount > 0` and `fct_employer_match_events = 0`, print actionable hints.
- Verify
  - `dbt run --select int_workforce_needs_by_level int_hiring_events`
  - `dbt test --select fct_workforce_snapshot fct_yearly_events`

Day 4: Idempotency, Checkpoints, and Recovery
- Year‑level clears: keep `setup.clear_mode: 'year' | 'all'` behavior; document recommended default per environment.
- Confirm checkpoint writing at end of each year; verify resume logic uses the latest checkpoint.
- Add a minimal “resume smoke test” script that runs 1 year, aborts, resumes for the rest.
- Verify
  - Delete last year’s checkpoint and re‑run with `--resume` to confirm safe behavior.
  - Confirm completed years are unchanged when re‑running.

Day 5: Observability & Runbook
- Multi‑year CSV: ensure `reports/multi_year_summary_YYYY_YYYY.csv` is always produced.
- Console dashboard: keep concise year‑end audit (active mix, events, contributions, match summary).
- Create `RUNBOOK.md` with:
  - “Happy path” commands for local vs prod.
  - Common failures and the exact targeted `dbt run --select` sequences to recover.
  - Where checkpoints and summaries live; how to restore from backup quickly.

Concrete Tasks (ticket‑sized)
- Orchestrator: add preflight DB backup (copy-if-exists) before first year.
- Orchestrator: stamp `int_simulation_run_log` with scenario/plan/year bounds and start/end timestamps.
- CLI: expose `--enforce-identifiers` (advisory; can be disabled) and surface a clear error when used without ids.
- dbt: add or tighten tests in `models/marts/schema.yml` only where they don’t trigger DuckDB relation issues.
- Reporting: guarantee multi‑year CSV summary and print contribution/match summaries per year.
- Docs: write `RUNBOOK.md` (operate/restore/resume); add a short “Prod checklist” to README.

How We’ll Verify
- Targeted builds over full runs:
  - `dbt seed`
  - `dbt run --select int_baseline_workforce int_employee_compensation_by_year`
  - `dbt run --select int_workforce_needs_by_level int_hiring_events`
  - `dbt run --select fct_yearly_events int_workforce_snapshot_optimized int_employee_contributions fct_workforce_snapshot`
  - `dbt test --select fct_workforce_snapshot fct_yearly_events`
- Orchestrator smoke:
  - `python -m navigator_orchestrator.cli run -c config/simulation_config.yaml -v --years 2025-2026`
  - `python -m navigator_orchestrator.cli checkpoint`
  - Inspect `reports/` for CSV summary and check console audits.

Production Checklist (fast)
- Identifiers present: `scenario_id`, `plan_design_id` (or run without `--enforce-identifiers`).
- Backups enabled and disk space confirmed.
- Checkpoints enabled; `--resume` flow documented and tested.
- Data‑quality tests pass; no unexpected row count swings (>0.5%) from raw→staged.
- Hiring demand non‑zero when growth configured; no NULL comp hires.
- Contributions exist for deferral states; match events present when formulas active.

Risks & Mitigations
- DuckDB lock contention: the file lock guard is present; avoid concurrent runs on same DB.
- Large runs: keep `--select` targeted during investigation; full refresh only when invariants break.
- dbt test flakiness on DuckDB relations: prefer column‑level tests and expression guards already present in `schema.yml`.

Nice‑to‑Haves (post‑week)
- Structured logging (JSON) for each stage with timings.
- Lightweight HTML report for year‑over‑year deltas and DQ summaries.
- Optional S3 (or remote) snapshotting hook for DB backups (requires network approval).

Ask
- Want me to wire the preflight backup + run metadata and draft RUNBOOK.md now? Those are the highest leverage, low‑risk changes that unlock smoother prod runs.
