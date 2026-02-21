# Research: Match-Responsive Deferral Adjustments

**Feature**: `058-deferral-match-response`
**Date**: 2026-02-21

## R1: State Accumulator Integration Pattern

**Decision**: Add match-response as a fourth event source in `int_deferral_rate_state_accumulator_v2.sql`, with additive combination logic when both match-response and escalation fire for the same employee.

**Rationale**: The accumulator already merges three sources (escalation, enrollment, baseline) via COALESCE priority. Adding a fourth source follows the established pattern. The additive logic (match-response rate + escalation increment) handles the clarified behavior where both apply in Year 1.

**Alternatives considered**:
- **Separate accumulator model**: Rejected — would duplicate temporal state logic and add DAG complexity.
- **Match-response as input to escalation model**: Rejected — would create inter-event model dependencies within EVENT_GENERATION stage, complicating the DAG.
- **Post-accumulator adjustment**: Rejected — would require a second accumulator pass and break the single-pass temporal pattern.

## R2: Pipeline Stage Placement

**Decision**: Place `int_deferral_match_response_events.sql` in the EVENT_GENERATION stage of `workflow.py`, between enrollment events (line 168) and escalation events (line 169).

**Rationale**: Follows the exact pattern of `int_deferral_rate_escalation_events.sql`. Both models:
- Are ephemeral (no disk materialization)
- Read Year 1 rates from enrollment events
- Read Year 2+ rates from prior year accumulator via direct table reference
- Output standardized event columns for `fct_yearly_events`

**Alternatives considered**:
- **STATE_ACCUMULATION stage**: Rejected — would require reading from the current year's accumulator (circular dependency) or adding a separate pre-accumulation pass.

## R3: Match-Maximizing Rate Calculation

**Decision**: Calculate the match-maximizing rate within the event model using existing dbt variables and macros, branching on `employer_match_status`.

**Rationale**: For `deferral_based` mode, the max rate is simply `MAX(employee_max)` from the `match_tiers` array — a constant for all employees. For service/tenure/points modes, the existing `get_tiered_match_max_deferral()` macro already returns the `max_deferral_pct` for an employee's tier. No new macros needed.

**Alternatives considered**:
- **New dedicated macro**: Rejected — existing macros handle all four modes. A new macro would duplicate logic.
- **Reading from match calculations model**: Rejected — `int_employee_match_calculations.sql` runs in STATE_ACCUMULATION (after events), creating a circular dependency.

## R4: Configuration Architecture

**Decision**: Add `DeferralMatchResponseSettings` Pydantic model to `workforce.py` with nested `UpwardResponseSettings` and `DownwardResponseSettings` sub-models. Export as flat dbt variables prefixed with `deferral_match_response_`.

**Rationale**: Follows the established pattern from `DeferralAutoEscalation` (flat variable export) and `EmployerMatchSettings` (nested Pydantic model). Flat dbt variables are simpler to access in Jinja templates than nested dicts.

**Alternatives considered**:
- **Nested dbt variable dict**: Rejected — accessing nested values in Jinja requires `{{ var('config')['nested']['key'] }}` which is verbose and error-prone. Flat variables like `{{ var('deferral_match_response_upward_participation_rate', 0.40) }}` are cleaner.

## R5: Deterministic Selection Algorithm

**Decision**: Use HASH-based deterministic random assignment with a unique salt (`'-match-response-'`), following the pattern from `int_voluntary_enrollment_decision.sql` line 150.

**Rationale**: The existing enrollment model uses `HASH(employee_id || '-deferral-rate-' || year)` for deterministic random values. Using a different salt ensures match-response selections are independent from enrollment optimization selections (different employees may be selected for each).

**Alternatives considered**:
- **Same salt as enrollment**: Rejected — would cause the same employees to always be selected for both enrollment optimization and match-response, creating unrealistic correlation.
- **Non-deterministic random**: Rejected — violates Constitution Principle I (reproducibility).

## R6: Event Type Name

**Decision**: Use `'deferral_match_response'` as the event_type string in `fct_yearly_events`.

**Rationale**: Follows the naming pattern of existing event types (`deferral_escalation`, `enrollment`, `enrollment_change`). Descriptive and distinct from escalation events. Does not require changes to the `fct_yearly_events` accepted_values test — that test will need to be updated to include the new type.

**Alternatives considered**:
- **Reuse `enrollment_change` type**: Rejected — semantically different (enrollment change implies voluntary participant action; match-response is behavioral modeling).
- **Generic `deferral_adjustment`**: Rejected — too vague; would conflate future adjustment types.

## R7: Circular Dependency Avoidance

**Decision**: For Year 2+ state reads, use direct table reference `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` instead of `{{ ref('int_deferral_rate_state_accumulator_v2') }}`.

**Rationale**: The accumulator depends on event models via `{{ ref() }}`. If the event model also used `{{ ref() }}` to read the accumulator, dbt would detect a circular dependency. Direct table reference (same pattern as escalation events, line 160) bypasses the DAG while maintaining the temporal read from prior year.

**Alternatives considered**:
- **Separate state snapshot table**: Rejected — would add materialization overhead and another model to maintain.
