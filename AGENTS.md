# Fidelity PlanAlign Engine – AGENTS.md (Codex CLI Assistant Playbook)

This playbook defines how the Codex CLI assistant operates in this repository to produce precise, production-ready changes aligned to the architecture and standards in CLAUDE.md. When this file and CLAUDE.md disagree, CLAUDE.md wins.

---

## 1) Mission & Scope

- Generate or modify code, dbt SQL models, and docs that fit the Fidelity PlanAlign Engine architecture.
- Favor surgical, minimal diffs that solve the request at the root cause.
- Preserve event-sourced design, auditability, and deterministic reproducibility at all times.

---

## 2) Operating Environment

- Filesystem: workspace-write (edit only within this repo) via `apply_patch`.
- Network: restricted. No installs or remote fetches unless explicitly approved.
- Approvals: on-request; escalate only when necessary with a one-sentence justification.
- Do not commit or create branches unless the user requests it.

---

## 3) Core Workflow

1) **Clarify scope**: restate the request; call out unknowns and assumptions.
2) **Plan**: use `update_plan` for multi-step work; keep exactly one step in progress.
3) **Implement**: minimal, localized patches via `apply_patch`, consistent with surrounding style.
4) **Validate**: targeted checks first, broaden as needed — and always in an **isolated database** for behavioral changes (Section 5).
5) **Document**: update README/docs/schema.yml where relevant.
6) **Handoff**: summarize what changed, how to verify, assumptions, and follow-ups.

---

## 4) Architecture Alignment (from CLAUDE.md)

- **Event sourcing**: immutable, UUID-stamped events; identical seed + inputs ⇒ identical outputs.
- **Unified event model**: Pydantic v2 events in `planalign_core/events` with required context (`scenario_id`, `plan_design_id`).
- **Pipeline**: `PipelineOrchestrator` runs six stages per year — INITIALIZATION → FOUNDATION → EVENT_GENERATION → STATE_ACCUMULATION → VALIDATION → REPORTING.
- **Temporal state accumulators**: Year N reads Year N−1 accumulator state + Year N events (e.g., `int_enrollment_state_accumulator`, `int_deferral_rate_state_accumulator`). Never create circular dependencies.
- **Build order**: accumulators → `int_*` → `fct_yearly_events` → `fct_workforce_snapshot`.
- **`int_*` models never read `fct_*` tables** — sanctioned exceptions: `fct_yearly_events` (built first in STATE_ACCUMULATION) and prior-year reads of `fct_workforce_snapshot`.
- **Event generators**: new event types implement `EventGenerator` in `planalign_orchestrator/generators/`, registered via `@EventRegistry.register("name")` (see `generators/sabbatical.py`).

---

## 5) Validation: Isolated Databases Only

`dbt/simulation.duckdb` is the **shared dev database** — fine for quick reads, never for validating a behavioral change. Do not `dbt run`/`dbt build` into it to "check" a change, and do not treat its current contents as ground truth.

```bash
# Preferred: isolated per-scenario databases
planalign batch --scenarios my_edge_case --clean

# Or: one-off isolated run with an explicit config + database path
DATABASE_PATH=/tmp/run/iso.duckdb \
  planalign simulate 2025-2027 --config /tmp/run/cfg.yaml --database /tmp/run/iso.duckdb

# Point tests at the isolated DB (get_database_path() honors DATABASE_PATH)
DATABASE_PATH=/tmp/run/iso.duckdb pytest tests/test_my_feature.py -v
```

- Cover **edge configs**, not just defaults (e.g., `auto_enrollment_scope: all_eligible_employees` with an early hire-date cutoff).
- For multi-year invariants, run a full `planalign simulate <start>-<end>`; a single-year `dbt run` of a few models can hide cross-year issues.
- Confirm a model actually feeds `fct_yearly_events`/`fct_workforce_snapshot` before trusting it — some `int_*` models are orphaned and never built by the pipeline.

---

## 6) Naming & Coding Standards

- **dbt models**: `tier_entity_purpose` (`stg_*`, `int_*`, `fct_*`, `dim_*`). Uppercase keywords, 2-space indents, CTEs, `{{ ref() }}`, no `SELECT *`. Incremental models use `incremental_strategy='delete+insert'` keyed on `(scenario_id, plan_design_id, employee_id, simulation_year)`; filter heavy models by `{{ var('simulation_year') }}`.
- **Python**: PEP 8, mandatory type hints, functions < ~40 lines, explicit exceptions (never bare `except:`), Pydantic v2 for config/models.
- **Quality gates**: cognitive complexity ≤ 15 (guard clauses, extracted helpers, dictionary dispatch), ≤ 13 parameters per function, no dead/commented-out code, no mutable default arguments.
- **Config**: YAML `snake_case`, hierarchical; validated by Pydantic.
- **Bands**: age/tenure bands live in seeds (`config_age_bands.csv`, `config_tenure_bands.csv`); use the `assign_age_band`/`assign_tenure_band` macros; `[min, max)` interval convention.

---

## 7) Development & Testing

Local commands to favor (no network):

- **Environment**: `source .venv/bin/activate` first — `ModuleNotFoundError` almost always means the venv is inactive.
- **dbt**: run from the `dbt/` directory only, always `--threads 1`; prefer `--select` for targeted runs.
- **CLI**: `planalign health`, `planalign simulate 2025-2027`, `planalign batch`, `planalign validate`, `planalign calibrate` (comp-only, isolated DB by default).
- **Tests**: `pytest -m fast` for the TDD loop; `pytest -m integration` against an isolated `DATABASE_PATH` DB; full suite is ~2,200 tests.
- **Lint/type**: `ruff check`, `mypy planalign_orchestrator/ planalign_cli/ planalign_core/ --ignore-missing-imports`.

When adding or changing dbt models: add/adjust `schema.yml` tests, keep types and contracts aligned, and document columns.

---

## 8) Paths & Gotchas

- **Database access in Python**: always `get_database_path()` from `planalign_orchestrator.config`; it honors the `DATABASE_PATH` env var.
- **Database locks**: IDE/DBeaver connections cause `Conflicting lock is held`; `planalign health` detects them.
- **sqlparse token limit**: multi-year runs auto-install a `.pth` fix on first `import planalign_orchestrator` — don't hand-patch sqlparse.
- **Frontend**: Tailwind v4 bundled via `@tailwindcss/vite`; never add CDN scripts, external stylesheets, or import maps to `planalign_studio/index.html`.
- **API security**: loopback bind by default; `PLANALIGN_API_TOKEN` gates non-local deployments (see SECURITY.md). Don't weaken these defaults.
- **Sensitive data**: census inputs (`data/`), runtime outputs (`var/`), and `*.duckdb` files are git-ignored PII-bearing artifacts — never commit or expose their contents unnecessarily.

---

## 9) Edit & Review Guidelines

- Keep diffs minimal and scoped to the request; avoid broad refactors and license headers.
- Prefer small utilities over entangling existing modules.
- Note unrelated issues in the final message; don't fix them unasked.
- Avoid destructive actions (`rm -rf`, resets, overwriting the shared dev DB) unless explicitly requested with risks called out.

---

## 10) Final Message Expectations

- Concise summary of what changed and why.
- Exact commands to validate locally (isolated-DB runs, targeted pytest/dbt selections).
- Assumptions, limitations, and sensible next steps — without overstepping.

---

## Active Technologies
- Python >=3.11 + dbt Core/dbt DuckDB execution via the existing orchestrator, Pydantic configuration models, DuckDB-backed simulation state, pytest for tests (106-fail-dbt-stage)
- No schema or persisted data-model changes; existing DuckDB run outputs may be partially present for failed runs and must remain clearly associated with failed status (106-fail-dbt-stage)
- Python >=3.11; dbt SQL/Jinja compatible with dbt Core 1.8.8 + Existing PlanAlign orchestrator, Pydantic v2 configuration, dbt Core 1.8.8, dbt DuckDB 1.8.1, DuckDB 1.0.0 (107-preserve-census-enrollment)
- Existing scenario-isolated DuckDB tables; no schema or persisted contract changes; incremental yearly rows must be retained (107-preserve-census-enrollment)
- Python >=3.11; dbt SQL/Jinja compatible with dbt Core 1.8.8 + PlanAlign orchestrator, Pydantic v2 configuration, dbt Core 1.8.8, dbt DuckDB 1.8.1, DuckDB 1.0.0, pytest 7.4, psutil (107-preserve-census-enrollment)
- Existing scenario-isolated DuckDB outputs plus one disposable internal `enrollment_decision_projection` table rebuilt from census and immutable fact events; no public mart, API, or configuration schema change (107-preserve-census-enrollment)
- Python >=3.11; TypeScript 5.8; SQL compatible with DuckDB 1.0.0 + FastAPI, Pydantic v2, DuckDB; React 19, React Router 7, Recharts 3.5, Tailwind CSS 4, Lucide React (110-scenario-diff-view)
- Existing workspace `base_config.yaml` and scenario overrides plus existing scenario-isolated DuckDB outputs and append-only `run_metadata`; no new tables or persisted fields (110-scenario-diff-view)
- Python >=3.11 + Existing FastAPI, Pydantic v2, Typer, Rich, DuckDB 1.0.0, PyYAML, and Python standard-library `hashlib`/`json`/`zipfile`/`subprocess`; no new dependency (111-run-provenance-report)
- Existing `workspaces/<workspace>/scenarios/<scenario>/runs/<run_id>/` archives plus one versioned `provenance.json` sidecar created during execution; existing append-only DuckDB `run_metadata` reuses its schema with the authoritative run ID; no public mart or new database table (111-run-provenance-report)

## Recent Changes
- 106-fail-dbt-stage: Added Python >=3.11 + dbt Core/dbt DuckDB execution via the existing orchestrator, Pydantic configuration models, DuckDB-backed simulation state, pytest for tests
