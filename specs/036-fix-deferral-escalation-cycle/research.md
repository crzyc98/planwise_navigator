# Research: Fix Deferral Rate Escalation Circular Dependency

**Feature**: 036-fix-deferral-escalation-cycle
**Date**: 2026-02-07

## Research Questions & Findings

### R1: What is the exact circular dependency?

**Decision**: The original `.disabled` model referenced `fct_workforce_snapshot` for prior-year escalation state. The dependency chain was: `int_deferral_rate_escalation_events` -> (via ref) -> `fct_workforce_snapshot` -> (via accumulator) -> `fct_yearly_events` -> (via UNION ALL) -> `int_deferral_rate_escalation_events`. This creates an unresolvable cycle in the dbt DAG.

**Rationale**: Confirmed by reading the commented-out code in `.disabled` (lines 89-98) which shows `FROM {{ ref('fct_workforce_snapshot') }} WHERE simulation_year = {{ simulation_year - 1 }}`.

**Alternatives considered**: None needed -- the root cause is definitive.

### R2: How does the corrected model break the cycle?

**Decision**: The active `.sql` model uses `{{ target.schema }}.int_deferral_rate_state_accumulator_v2` (a direct SQL table reference) instead of `{{ ref('int_deferral_rate_state_accumulator_v2') }}`. This makes the dependency invisible to dbt's DAG parser while still accessing the needed data at runtime.

**Rationale**: This is the same pattern used by the accumulator's own temporal self-reference (`{{ this }}`). The orchestrator pipeline guarantees execution order: Year N-1 STATE_ACCUMULATION completes before Year N EVENT_GENERATION begins.

**Alternatives considered**:
- `{{ ref() }}` with `depends_on` override: Not supported by dbt-duckdb adapter.
- Separate pre-escalation snapshot: Would add unnecessary complexity and duplicate data.
- Read from `{{ this }}` on escalation model: Not applicable since escalation events are ephemeral.

### R3: Is the existing corrected model complete and functional?

**Decision**: The `.sql` model contains a complete implementation (293 lines) with all required business logic:
- Configuration toggle (`deferral_escalation_enabled`)
- Enrollment requirement check
- Rate cap enforcement (won't reduce rates above cap)
- Year 1 base case (reads from enrollment events)
- Year 2+ temporal case (reads from accumulator via direct table ref)
- Configurable hire date cutoff, delay years, effective date
- Full audit trail in event output columns

**Rationale**: Line-by-line code review confirmed all eligibility checks from the spec (FR-002) are present. The model handles the empty `{% if not esc_enabled %}` branch correctly, returning zero rows with the proper schema.

**Remaining concern**: The model is materialized as `ephemeral`, which means it's inlined into downstream models (primarily `fct_yearly_events`). This is correct for the E068A fused event generation pattern. However, `int_deferral_rate_state_accumulator_v2` also reads from it via `{{ ref() }}`, meaning the escalation SQL will be inlined there too. This could make compiled SQL large but should not cause functional issues.

### R4: What is the state of downstream consumers?

**Decision**: Three models consume escalation events:

1. **`fct_yearly_events`** (line 347): UNION ALL leg -- ready, no changes needed.
2. **`int_deferral_rate_state_accumulator_v2`** (line 96): Reads current year escalation events -- ready, no changes needed.
3. **`int_deferral_escalation_state_accumulator`** (line 71): Reads all escalation events up to current year -- this is an **orphaned legacy model** (no downstream ref). Can be left as-is or removed.

Additionally, `int_deferral_rate_state_accumulator` (without v2) also references it but is also legacy.

**Rationale**: Confirmed by searching all `ref('int_deferral_rate_escalation_events')` across the dbt project. The `int_deferral_rate_state_accumulator_v2` is the canonical accumulator per schema documentation.

### R5: What tests exist and what needs replacement?

**Decision**: Current test state:

| Test | Status | Action |
|------|--------|--------|
| `dbt/models/intermediate/schema.yml` (escalation tests) | Commented out | Re-enable |
| `dbt/tests/data_quality/test_deferral_escalation.sql` | Placeholder (always passes) | Replace with real assertions |
| `dbt/models/marts/data_quality/dq_deferral_escalation_validation.sql` | Placeholder (hardcoded healthy) | Replace with real validation |
| `dbt/tests/analysis/test_escalation_bug_fix.sql` | Real test (3 scenarios) | Verify still passes |
| `dbt/tests/marts/test_deferral_orphaned_states.sql` | Real test | Verify still passes |
| `dbt/tests/marts/test_deferral_state_continuity.sql` | Real test | Verify still passes |
| pytest tests for escalation | None exist | Create new |

**Rationale**: Searched all test files for `deferral_escalation` references. The placeholder pattern is documented in E080 conversion tracking.

### R6: What orchestrator changes are needed?

**Decision**: No orchestrator changes required. The pipeline already:
- Lists `int_deferral_rate_escalation_events` as the last model in EVENT_GENERATION (workflow.py:169)
- Special-cases it for `--full-refresh` (year_executor.py:507-516)
- Exports all escalation config vars via `config/export.py` (lines 162-184, 210-227)
- Has `DeferralEscalationRegistry` for post-year updates (registries.py:278-339)

**Rationale**: All integration points are already wired up. The only reason escalation wasn't working was the `.disabled` model returning empty sets and the corrected `.sql` model never being validated.

### R7: Configuration readiness

**Decision**: Configuration is complete and ready:
- `config/simulation_config.yaml` (lines 639-651): All 7 escalation parameters defined
- `config/export.py`: Maps all config fields to dbt variables
- Default values in the dbt model match the config file values:
  - `enabled: true`, `increment: 0.01`, `cap: 0.10`, `effective_day: 01-01`
  - `hire_date_cutoff: 2020-01-01`, `require_enrollment: true`, `delay_years: 1`

**Rationale**: Direct comparison of `simulation_config.yaml` values with model defaults confirms consistency.
