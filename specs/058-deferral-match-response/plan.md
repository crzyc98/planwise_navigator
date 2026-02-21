# Implementation Plan: Match-Responsive Deferral Adjustments

**Branch**: `058-deferral-match-response` | **Date**: 2026-02-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/058-deferral-match-response/spec.md`

## Summary

Generate one-time deferral adjustment events when the match formula creates a gap between employee deferrals and the match-maximizing rate. A configurable fraction of below-max employees increase their deferrals (upward response, default 40%), and a smaller fraction of above-max employees decrease theirs (downward response, default 15%). Events flow through the existing deferral rate state accumulator with correct additive interaction with auto-escalation.

**Technical approach**: Create a new ephemeral dbt model (`int_deferral_match_response_events.sql`) following the established escalation events pattern. Add a Pydantic config model, export to dbt variables, and merge into the state accumulator with additive escalation logic.

## Technical Context

**Language/Version**: Python 3.11 (config/orchestrator), SQL/Jinja2 (dbt models)
**Primary Dependencies**: dbt-core 1.8.8, dbt-duckdb 1.8.1, Pydantic v2.7.4
**Storage**: DuckDB 1.0.0 (`dbt/simulation.duckdb`) — immutable event store
**Testing**: pytest (Python integration tests), dbt tests (data quality SQL tests)
**Target Platform**: Linux/macOS server (on-premises analytics)
**Project Type**: Single project — backend simulation engine (no frontend changes)
**Performance Goals**: Handle 100K+ employees without memory errors; no measurable regression to simulation runtime
**Constraints**: Single-threaded dbt execution (`--threads 1`); ephemeral materialization for event models; no circular DAG dependencies
**Scale/Scope**: 6 files modified/created; ~400 lines new SQL, ~80 lines new Python config, ~100 lines tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| **I. Event Sourcing & Immutability** | PASS | Match-response events recorded as distinct immutable events in `fct_yearly_events` with audit fields (FR-013). Deterministic reproducibility via seeded random assignment (FR-006). |
| **II. Modular Architecture** | PASS | New ephemeral model < 200 lines. Config model < 50 lines. No module exceeds 600-line limit. Single responsibility: match-response event generation. |
| **III. Test-First Development** | PASS | Plan includes dbt data quality tests + Python integration tests. Schema-level validation for new event type. |
| **IV. Enterprise Transparency** | PASS | Events include previous rate, new rate, target rate, response type, match mode. Full audit trail reconstruction possible. |
| **V. Type-Safe Configuration** | PASS | New Pydantic v2 model with explicit validation. dbt variables accessed via `{{ var() }}` with defaults. |
| **VI. Performance & Scalability** | PASS | Ephemeral materialization avoids disk I/O. Hash-based deterministic selection is O(n) per employee. No cross-join or self-join patterns. |

**Gate result**: ALL PASS — no violations, no complexity tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/058-deferral-match-response/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
# New files
dbt/models/intermediate/events/int_deferral_match_response_events.sql  # Core event generation model

# Modified files
planalign_orchestrator/config/workforce.py                             # DeferralMatchResponseSettings Pydantic model
planalign_orchestrator/config/export.py                                # Export new config to dbt variables
config/simulation_config.yaml                                          # New deferral_match_response section
dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql     # Merge match-response events
planalign_orchestrator/pipeline/workflow.py                            # Add model to EVENT_GENERATION stage

# New test files
dbt/tests/data_quality/test_deferral_match_response.sql                # dbt data quality tests
dbt/models/intermediate/events/schema.yml                              # Schema tests for new model
tests/test_match_response_events.py                                    # Python integration tests
```

**Structure Decision**: Follows existing single-project layout. New model placed in `dbt/models/intermediate/events/` alongside `int_deferral_rate_escalation_events.sql` (same pattern). Config additions follow established Pydantic model → export → dbt variable chain.

## Design Decisions

### D1: Pipeline Placement — EVENT_GENERATION Stage

Match-response events go in the EVENT_GENERATION stage (workflow.py line ~170), after enrollment events (line 168) and before or alongside escalation events (line 169). This follows the exact pattern of `int_deferral_rate_escalation_events.sql`:

- **Year 1**: Read initial deferral rates from `int_enrollment_events` and `int_synthetic_baseline_enrollment_events`
- **Year 2+**: Read prior year's accumulated rate from `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` (direct table reference, not `ref()`, to avoid circular DAG dependency)

### D2: Accumulator Merge — Additive Escalation Logic

The state accumulator (`int_deferral_rate_state_accumulator_v2.sql`) currently uses COALESCE priority: escalation → enrollment → baseline → fallback. Adding match-response requires handling the case where both match-response AND escalation fire for the same employee in the same year:

```sql
-- New COALESCE logic in accumulator:
CASE
  -- Both match-response AND escalation fired: additive
  WHEN mr.match_responsive_rate IS NOT NULL AND e.escalation_rate IS NOT NULL
    THEN LEAST(
      mr.match_responsive_rate + e.escalation_rate,
      {{ var('deferral_escalation_cap', 0.10) }},
      {{ var('irs_402g_limit', 23500) }} / NULLIF(comp.compensation_amount, 0)
    )
  -- Only escalation fired
  WHEN e.latest_deferral_rate IS NOT NULL
    THEN e.latest_deferral_rate
  -- Only match-response fired
  WHEN mr.match_responsive_rate IS NOT NULL
    THEN mr.match_responsive_rate
  ELSE NULL
END
```

Note: Individual event models (escalation, match-response) already cap their own output rates at both limits. The accumulator LEAST guard is a defense-in-depth check for the additive case where two individually-capped rates could sum above the IRS limit.

This respects the clarification: "Both apply in Year 1. Match response fires first, then escalation applies on top."

### D3: Match-Maximizing Rate Calculation — Per Match Mode

The event model calculates the match-maximizing deferral rate differently per match mode:

| Match Mode | Calculation | Source |
|------------|-------------|--------|
| `deferral_based` | `MAX(employee_max)` across all match tiers | `match_tiers` dbt variable |
| `graded_by_service` | `max_deferral_pct` from employee's service tier | `employer_match_graded_schedule` variable + `get_tiered_match_max_deferral()` macro |
| `tenure_based` | `max_deferral_pct` from employee's tenure tier | `tenure_match_tiers` variable |
| `points_based` | `max_deferral_pct` from employee's points tier | `points_match_tiers` variable |

For `deferral_based` mode, the max is uniform across all employees (top of highest tier). For other modes, it varies per employee based on their service/tenure/points.

### D4: Deterministic Random Selection

Follow the existing pattern from `int_voluntary_enrollment_decision.sql` (line 150):

```sql
(ABS(HASH(employee_id || '-match-response-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0
```

This deterministic hash produces a value in [0, 1) that is:
- Reproducible across identical simulation runs
- Different from the enrollment optimization random value (different salt: '-match-response-' vs '-deferral-rate-')
- Evenly distributed across the employee population

Employee selection: `hash_value < participation_rate` → selected for response.
Sub-group assignment: Of selected, `hash_value < participation_rate * maximize_rate` → maximizer, otherwise partial responder.

### D5: First-Year-Only Guard

The model uses a simple config guard:

```sql
{% if var('deferral_match_response_enabled', false) and var('simulation_year') == var('start_year') %}
  -- Generate match-response events
{% else %}
  -- Empty result set with correct schema
  SELECT ... WHERE FALSE
{% endif %}
```

This ensures zero events outside Year 1 with no runtime overhead. Future "gradual" mode would replace `== var('start_year')` with a range check.

### D6: Event Type — Reuse Existing Schema

Match-response events use event_type = `'deferral_match_response'` and output the same column schema as `int_deferral_rate_escalation_events.sql` (employee_deferral_rate, prev_employee_deferral_rate, escalation_rate, etc.) so they integrate cleanly into `fct_yearly_events` without schema changes.

## Complexity Tracking

> No violations detected — table intentionally left empty.
