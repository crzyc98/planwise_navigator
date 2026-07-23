# Phase 0 Research: Match-Response Deferral Events in Client/Studio Simulations

**Feature**: 123-match-response-events | **Date**: 2026-07-23

This is a regression/integration investigation. The research goal was to locate exactly where match-response events are lost on the Studio/workspace path, and to decide the minimal, spec-aligned fix. All findings below are grounded in the current code on `main`.

## Evidence gathered

| # | Question (from issue #451) | Finding | Evidence |
|---|----------------------------|---------|----------|
| 1 | Does the resolved scenario export `deferral_match_response_enabled: true`? | Only if `cfg.deferral_match_response.enabled` is true. It defaults to **False**. | `config/export.py:1258-1259`, `config/loader.py:55-58`, `config/workforce.py:475` |
| 2 | Do Studio/workspace `dc_plan` configs preserve or override the legacy `deferral_match_response`? | They carry **neither**. Studio `base_config.yaml` files contain **0** `deferral_match_response` blocks, and there is **no `dc_plan` → `deferral_match_response` bridge** nor a `dc_plan` match-response field. | `grep` of `workspaces/*/base_config.yaml` (0 hits); no bridge in `workspace_storage.py` / config layer |
| 3 | Does `int_deferral_match_response_events` receive eligible first-year participants? | The model logic is correct; it simply never runs because its enable var is false. It gates on `deferral_match_response_enabled` **and** first-year, joins enrollment events + census deferral rates, and computes the below-threshold set. | `dbt/models/intermediate/events/int_deferral_match_response_events.sql:11,49,128-199` |
| 4 | Is the model built in EVENT_GENERATION and does it flow to `fct_yearly_events`? | Yes — listed in the EVENT_GENERATION stage and the event-generation executor; its rows are unioned into `int_current_year_events` → `fct_yearly_events`. | `pipeline/workflow.py:213`, `pipeline/event_generation_executor.py:416`, `int_current_year_events.sql` |
| 5 | Is the employer-match ceiling exported correctly, producing a nonempty below-threshold population? | The ceiling is exported once, always-on, as `employer_match_max_deferral_rate` when a match formula is configured; the model reads it directly. If no match formula/ceiling exists, the below-threshold population is empty (expected). | `config/export.py:859`, model line 29 (`var('employer_match_max_deferral_rate', none)`) |
| 6 | Is there regression coverage for the Studio path + fact-table integration? | No test exercises the Studio/workspace config path for this feature; existing 058 coverage is config-export/CLI-oriented. | `tests/test_config_export_match_magnet.py`, `tests/unit/orchestrator/test_config_export.py` |

## Root cause (decision D1)

**The dbt model and the typed exporter are correct. The defect is entirely in the Studio/workspace configuration layer.** Because Studio scenarios carry only `dc_plan`/base config without a `deferral_match_response` block, the merged config has no such key; Pydantic's `default_factory=DeferralMatchResponseSettings` yields `enabled=False`; the exporter emits `deferral_match_response_enabled=False`; and the model returns its empty-schema branch (`{% if mr_enabled and simulation_year == start_year %}` is false). The absence is silent — nothing in the resolved config signals that the feature was off.

Note: a user could enable it **today** by hand-adding a top-level `deferral_match_response:` block to a scenario's `config_overrides` (the deep-merge preserves top-level keys and Pydantic reads it). The real gaps are **discoverability** (no supported Studio mechanism), **transparency** (silent disabled), and **coverage** (no regression test).

## Decision D2 — Resolution approach

**Chosen**: In `WorkspaceStorage._merge_config`, add a focused reconciliation that resolves the effective `deferral_match_response` block from (a) an explicit top-level block (CLI/legacy parity) and/or (b) a Studio-native `dc_plan.deferral_match_response` sub-block, funneling both into the typed top-level block, **defaulting to disabled**. This mirrors the existing precedent in the same method where `dc_plan.match_template` is reconciled into `employer_match.active_formula` (`workspace_storage.py:629-640`) and the `_inject_seed_config_defaults` normalization.

**Rationale**: Keeps the typed `DeferralMatchResponseSettings` as the single source of truth (Constitution V), gives Studio a supported on-switch, preserves CLI behavior, and keeps the default disabled so no existing scenario changes silently.

**Alternatives considered**:
- *Base-config template injection* — add the block to newly created workspace `base_config.yaml`. Rejected as primary: doesn't help existing workspaces and still relies on manual YAML editing to toggle.
- *Default-on injection* in `_inject_seed_config_defaults` — inject an **enabled** default when absent. Rejected: silently flips behavior for all existing scenarios, violating "disabled by default" and surprising existing clients.
- *dbt/model change* — rejected: the model is correct; changing it would mask the config bug and risk CLI parity.

## Decision D3 — Transparency

The merged config the run consumes (and persists to the run's `config.yaml`) MUST always contain an explicit `deferral_match_response.enabled` boolean, so the enabled/disabled state is observable without inferring from absence (spec FR-001, SC-005). The machine-checkable signal downstream is the exported `deferral_match_response_enabled` dbt var.

## Decision D4 — Determinism & the "~40%" assertion

The model's responder selection is deterministic: `ABS(HASH(employee_id || '-match-response-' || year)) % 1000 / 1000.0 < upward_participation`. The regression test therefore asserts an **exact expected responder count** for a fixed seed and a small, fixed fixture census (chosen so its below-threshold population yields a stable count near 40%), not a fuzzy percentage. This avoids flaky tolerance-based assertions while still validating the ~40% assumption.

## Decision D5 — UI scope

Surfacing the toggle in the Studio DC Plan page is a **follow-up**, out of scope here. This feature delivers the API/config-layer bridge, transparency, and regression coverage — sufficient to satisfy every acceptance criterion in the spec. A follow-up can add the React control that writes `dc_plan.deferral_match_response.enabled`.

## Open risks

- **Ceiling absence**: if a Studio scenario enables match response but configures no match formula, `employer_match_max_deferral_rate` is absent and the below-threshold population is empty. The fix must make this distinguishable (resolved config shows enabled=true; zero events explained by empty eligible set) rather than looking like the disabled case. Covered by an edge-case test.
- **Merge precedence**: if both a legacy top-level block and a `dc_plan.deferral_match_response` sub-block are present, define a deterministic precedence (dc_plan UI overrides legacy, consistent with the E101 ordering in `to_dbt_vars`). Documented in the contract.
