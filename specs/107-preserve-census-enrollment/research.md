# Research: Preserve Census Enrollment

## Decision: Treat Full Reset as a Run Boundary

**Decision**: Resolve omitted `clear_mode` to year-preserving cleanup. An explicit `clear_mode: all` reset occurs once before the multi-year loop. FOUNDATION may full-refresh in the start year, but later years preserve incremental foundation and temporal rows. Model-specific safe exceptions remain explicit.

**Rationale**: The orchestrator already owns run initialization. Reapplying full refresh during every year destroys Year N-1 inputs and contradicts temporal accumulator design.

**Alternatives considered**:

- Change only the missing-value fallback: rejected because explicit `all` would remain destructive mid-run.
- Exempt individual enrollment tables: rejected because all temporal models share the preservation invariant.

## Decision: Rebuild a Fact-Authoritative Enrollment-Decision Projection

**Decision**: Before EVENT_GENERATION for each year, atomically rebuild a disposable `enrollment_decision_projection`. The start-year projection uses `int_baseline_workforce`; later-year projections fold baseline with only `fct_yearly_events` rows whose year is earlier than the decision year and whose `scenario_id` and `plan_design_id` match the active run.

**Rationale**: `fct_yearly_events` is the constitutional event authority. A direct dbt `ref()` from enrollment models to the fact table would create a static cycle, while self-reading `int_enrollment_events` makes an intermediate table authoritative. An orchestrator-owned projection creates a year boundary dbt cannot express, remains idempotently rebuildable on retry/resume, and can be reconciled directly to facts.

**Alternatives considered**:

- `ref('fct_yearly_events')` or `ref('int_enrollment_state_accumulator')`: rejected because each creates a dbt cycle.
- Raw table reads from dbt models: rejected because they hide dependencies and violate explicit dependency governance.
- Incrementally trust the existing enrollment registry: rejected because production does not update it after each year and retries can leave stale cache state.
- Continue the `{{ this }}` event-history self-read: rejected because intermediate rows can diverge from the immutable fact store.

## Decision: Expose the Projection Through Source and Staging Contracts

**Decision**: Declare the orchestrator projection in `dbt/models/sources.yml`, expose a thin `stg_prior_enrollment_state`, and require `int_enrollment_events`, `int_voluntary_enrollment_decision`, and `int_proactive_voluntary_enrollment` to use `ref('stg_prior_enrollment_state')`.

**Rationale**: The source/staging boundary makes the external orchestration dependency visible to dbt without reversing the event DAG. One shared input eliminates inconsistent state sources across enrollment paths.

**Alternatives considered**:

- Let each model query the projection directly: rejected because dependency and schema validation would be duplicated.
- Create multiple path-specific projections: rejected because they could disagree about participant status.

## Decision: Define Deterministic Transition and Opportunity Semantics

**Decision**: Order prior enrollment events by `effective_date`, `simulation_year`, `event_sequence`, and `event_id`. An `enrollment` event establishes enrolled status and applicable date/rate; an `enrollment_change` explicitly identified as opt-out sets status false and `ever_opted_out` true; other changes preserve status unless existing business rules explicitly define a status transition. Re-enrollment is allowed only through existing configured rules after the projected status permits it.

An enrollment **opportunity** means membership in the applicable eligible decision population. Tests assert an emitted enrollment event only when the fixture forces the relevant probability to `1.0`; normal stochastic configurations assert eligibility, not event occurrence.

**Rationale**: Explicit transitions and tie-breaking make replay reproducible. Separating eligibility from random event realization prevents flaky regression tests.

**Alternatives considered**:

- Treat every enrollment-change event as unenrollment: rejected because some changes affect rates rather than status.
- Require every eligible control to emit an event under normal probabilities: rejected because eligibility is not deterministic selection.

## Decision: Validate and Reconcile Before Event Generation

**Decision**: For year N after the start year, run the registered year-dependency validator, rebuild the projection, validate uniqueness and scenario/plan scope, and log baseline/fact/projection reconciliation before any SQL or hybrid event path runs. Any failure prevents event generation and preserves structured YearDependencyError or projection error context.

**Rationale**: Voluntary and proactive decisions consume prior state during EVENT_GENERATION. Validation after decisions is too late.

**Alternatives considered**:

- Let SQL models fall back to never-enrolled: rejected because that recreates mass enrollment silently.
- Validate only before STATE_ACCUMULATION: rejected because corrupt events may already exist.

## Decision: Prove Scenario and Run Isolation Through Separate Outputs

**Decision**: Execute scenario A and scenario B into distinct temporary DuckDB paths and artifact directories. Assert every fact row matches the configured scenario/plan IDs and that running B leaves A's checksum and row counts unchanged. Do not add a run ID column to marts.

**Rationale**: The existing architecture isolates runs by database/artifact path and scopes facts by scenario/plan. The test proves that contract without expanding persisted schemas or the companion cross-run-contamination issue.

**Alternatives considered**:

- Add `run_id` to event and snapshot schemas: rejected as out of scope and a breaking data-model change.
- Treat use of `tmp_path` alone as proof: rejected because isolation must be asserted, not assumed.

## Decision: Add Measurable Performance and Fast-Suite Gates

**Decision**: Add an opt-in performance test that set-wise generates 100K employees and 200K two-year history inputs in a temporary DuckDB database. The projection must return exactly 100K unique states in <=30 seconds with <=1,024 MiB RSS growth. Against an accepted JSON baseline, median runtime may regress by at most 15% and RSS by at most 20%. Separately, a hard-timed wrapper must exit nonzero when the complete `pytest -m fast` run reaches 10 seconds.

**Rationale**: These gates directly enforce constitution requirements using repository-standard performance markers, psutil, and existing regression thresholds. Set-wise fixture generation prevents Python row-loop overhead from dominating the measured projection.

**Alternatives considered**:

- Use a plain shell `time` command: rejected because it reports but does not enforce the limit.
- Put the 100K test in the fast suite: rejected because enterprise-scale validation is intentionally opt-in.
- Rely on stale stress documentation: rejected because several referenced stress sources are absent.

## Decision: Make Auditability and Validation Commands Executable

**Decision**: The quickstart lists every new dbt selector before tasks reference it. A fixture participant trace queries census state, prior fact events, projection provenance, accumulator state, and snapshot outcome, asserting both correct lineage and elapsed time below 300 seconds.

**Rationale**: Lineage presence alone does not prove the operator can complete SC-006, and late selector repair makes story checkpoints non-runnable.

**Alternatives considered**:

- Document the trace without timing it: rejected because SC-006 is measurable.
- Repair selectors only during final polish: rejected because earlier story checkpoints depend on them.
