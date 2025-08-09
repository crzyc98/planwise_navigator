# PlanWise Navigator – AGENTS.md (Codex CLI Assistant Playbook)

This playbook defines how the Codex CLI assistant operates in this repository to produce precise, production‑ready changes aligned to the project’s architecture and standards described in CLAUDE.md.

---

## 1) Mission & Scope

- Generate or modify code, SQL models, and docs that fit the PlanWise Navigator architecture.
- Favor surgical, minimal diffs that solve the user’s request at the root cause.
- Preserve event‑sourced design, auditability, and reproducibility at all times.

---

## 2) Operating Environment

- Filesystem: workspace‑write (only edit within this repo). Use `apply_patch` for all edits.
- Network: restricted. Avoid installs or remote fetches unless explicitly approved.
- Approvals: on‑request. Ask for escalation only when necessary (e.g., networked installs, writing outside workspace).

---

## 3) Interaction Style

- Default tone: concise, direct, friendly; focus on actionable steps.
- Before running tools, send a brief 1–2 sentence preamble describing what’s next.
- Use the `update_plan` tool for multi‑step or ambiguous tasks; keep one step in progress.
- Provide short progress updates during longer work; avoid unnecessary verbosity.

---

## 4) Core Workflow

1) Clarify scope: restate the request; call out unknowns/assumptions.
2) Plan: outline concise steps (use `update_plan` when multi‑phase work).
3) Implement: edit files via `apply_patch`; keep changes localized and consistent with style.
4) Validate: where possible, run targeted checks/tests with `functions.shell` (no network). Start specific, broaden as needed.
5) Document: update README/docs/dbt docs where relevant; add clear docstrings/comments when helpful.
6) Handoff: summarize what changed, how to run/verify, and next steps.

Constraints:
- Do not commit or create branches unless the user requests it.
- Do not add licenses/headers; avoid broad refactors unrelated to the task.

---

## 5) Architecture Alignment (from CLAUDE.md)

- Event Sourcing: maintain immutable, auditable events; ensure reproducibility and type safety.
- Unified Event Model: respect `SimulationEvent` (Pydantic v2) and required context (`scenario_id`, `plan_design_id`).
- Modular Engines: keep logic separable (compensation, termination, hiring, promotion, DC plan, admin).
- Snapshot Reconstruction: avoid breaking the event→state lineage used by marts and accumulators.

---

## 6) Naming & Coding Standards

- dbt models: `tier_entity_purpose` (e.g., `int_*`, `fct_*`, `stg_*`). Avoid `SELECT *`; uppercase SQL keywords; 2‑space indents; use CTEs and `{{ ref() }}`.
- Event tables: `fct_yearly_events` immutable; `fct_workforce_snapshot` point‑in‑time.
- Python: PEP8, type hints, functions < ~40 lines when practical; explicit exceptions; Pydantic for config/models.
- Config: YAML `snake_case`, hierarchical.
- File edits: minimal, focused patches consistent with surrounding style.

---

## 7) Development & Testing

- Local commands to favor (no network):
  - Python: `venv/bin/python` or `python` within the activated venv.
  - dbt: run from `/dbt` directory only (e.g., `dbt run`, `dbt test`).
  - Multi‑year: `python run_multi_year.py` or `python orchestrator_dbt/run_multi_year.py`.
- Data‑quality gates to respect:
  - Row counts drift ≤ 0.5% from raw→staged.
  - Primary‑key uniqueness on every model.
  - Distribution drift checks (KS) should maintain p‑value expectations per CLAUDE.md.
- When adding/changing models:
  - Provide/adjust `schema.yml` tests.
  - Ensure types/contracts align; avoid breaking dbt model contracts.

Note: This sandbox may prevent package installs or long‑running jobs; prefer targeted checks. If a command needs elevated permissions (e.g., network), request approval with a brief justification.

---

## 8) Paths, Tools, and Gotchas

- DuckDB location: `simulation.duckdb` at repo root; avoid IDE locks during runs.
- Always run dbt from `/dbt`; prefer `--select` for targeted runs.
- Enrollment architecture: respect the temporal accumulator (`int_enrollment_state_accumulator`) and avoid circular dependencies.
- Use `shared_utils.py` patterns for shared logic or locking.

---

## 9) Edit & Review Guidelines

- Keep diffs minimal and scoped to the request.
- Prefer adding small utilities over entangling existing modules.
- Update or add inline documentation where it clarifies intent; do not over‑comment.
- If you detect unrelated issues, note them in the final message but do not change them unless asked.

---

## 10) Tooling Protocols (Codex CLI)

- `apply_patch`: the only way to create/modify/delete files.
- `functions.shell`: run read or test commands; batch related reads; avoid destructive commands without explicit user direction.
- `update_plan`: maintain a lightweight, living plan when work spans multiple steps; one `in_progress` step at any time.
- Preambles: short, friendly description before tool calls (e.g., “Checking dbt model contracts next.”).

---

## 11) Final Message Expectations

- Concise summary of what changed and why.
- Commands to validate changes locally (dbt run/test, scripts) if applicable.
- Any assumptions, limitations, or follow‑ups.
- Offer next logical steps (e.g., run tests, open PR) without overstepping.

---

## 12) Escalation & Safety

- Request elevated permissions only when required (e.g., install deps, network access, writing outside workspace). Include a one‑sentence justification.
- Avoid destructive actions (e.g., `rm -rf`, resets) unless the user explicitly requests them and risks are called out.
- Treat sensitive data and large binaries (DuckDB files) with care; do not expose contents unless necessary.

---

## 13) Quick Checklists

Feature/change checklist:
- Clarified scope and constraints
- Minimal, targeted patch created via `apply_patch`
- Style and naming match project norms
- dbt/Python tests or checks adjusted as needed
- Docs updated if relevant
- Short verification steps provided

dbt change checklist:
- Model lives in correct tier (`stg/`, `int/`, `marts/`)
- Inputs use `{{ ref() }}` and have tests in `schema.yml`
- No `SELECT *`; columns typed and documented
- Contracts/constraints updated to reflect schema changes

Python change checklist:
- Types and docstrings present where useful
- Clear exceptions and small functions
- Config via Pydantic when applicable

---

By following this playbook, the Codex CLI assistant produces high‑quality, auditable changes that align with the event‑sourced architecture and enterprise standards documented in CLAUDE.md.
