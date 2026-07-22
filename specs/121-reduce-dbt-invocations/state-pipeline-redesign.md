# Follow-up Design: Normalize the Event and State Pipeline

**Status**: Recommended follow-up; intentionally outside Feature 121's
schedule-only scope.

## Why a redesign is warranted

Tier C exposed architecture debt rather than a difficult batching problem. The
current results depend on persisted intermediate relations and command boundaries
that are not fully represented by the dbt DAG.

Concrete findings:

- `fct_yearly_events` is built twice per simulation year: once through
  `tag:EVENT_GENERATION`, then again as the first STATE_ACCUMULATION model.
- `int_employee_state_by_year` is built every year but has no model consumers. It
  also hard-codes `default` / `main` instead of using the active scenario and plan.
- Workforce state is implemented three times across
  `int_employee_state_by_year` (318 lines),
  `int_workforce_snapshot_optimized` (484 lines), and
  `fct_workforce_snapshot` (1,044 lines).
- `int_workforce_snapshot_optimized` is a current-year scratch relation used by
  only employer-core and match calculations, yet requires a command-level
  `--full-refresh` that splits the entire stage.
- Some prior-year dependencies use `adapter.get_relation()` to bypass dbt graph
  discovery. The orchestrator therefore owns sequencing that the manifest cannot
  validate.
- Stage tags do not express ownership cleanly. Contribution and match models carry
  EVENT_GENERATION tags but must be explicitly excluded because they consume state
  produced later.

The safe three-command schedule should remain until these relationships are made
explicit. Removing a command boundary before that work is complete changes results.

## Target architecture

The target is one authoritative relation per state domain and one publication of
the current year's immutable event set.

```text
census + prior-year facts/projections
                  |
                  v
       current-year event candidates
                  |
                  v
       fct_yearly_events (publish once)
                  |
       +----------+-------------+
       |                        |
       v                        v
workforce-state accumulator   enrollment-state accumulator
       |                        |
       |                        v
       |                    deferral-state accumulator
       |                        |
       +-----------+------------+
                   v
        contributions and employer match
                   |
                   v
        fct_workforce_snapshot (publish once)
```

### Event publication

1. Event candidate models consume census, prior-year projections, configuration,
   and other candidate models. They do not consume the current year's
   `fct_yearly_events`.
2. A single current-year event relation unions and sequences every candidate.
3. `fct_yearly_events` replaces only the active scenario/plan/year partition once
   per year. No later stage rebuilds it.
4. The existing fact-backed `enrollment_decision_projection` remains a valid
   prior-state boundary. It is rebuilt before event generation and reads only years
   earlier than the decision year.

### Domain state

1. Replace the orphaned `int_employee_state_by_year` with a scenario- and
   plan-scoped workforce-state accumulator, or rebuild that model to fulfill this
   role. It owns employment status, dates, compensation, level, age, tenure, and
   proration only.
2. Keep enrollment and deferral state in their existing domain accumulators. Do not
   fold benefit/account fields into workforce state.
3. Make employer-core, employee-contribution, and match calculations consume the
   workforce, enrollment, and deferral accumulators directly.
4. Eliminate `int_workforce_snapshot_optimized`; it is a duplicate current-year
   workforce implementation and should not be a materialization boundary.
5. Simplify `fct_workforce_snapshot` to join authoritative domain state and
   contribution outputs rather than replaying workforce events again.

### dbt graph and stage ownership

- Give event candidates, event publication, domain state, benefit calculations,
  and snapshot publication distinct tags or explicit stage selections.
- Remove EVENT_GENERATION tags from models that require accumulated state.
- Replace hidden current-year reads and ordering comments with `ref()` edges.
- Keep prior-year temporal reads explicit through self-referencing accumulators or
  orchestrator-built, documented sources. Do not use dynamic relation lookup merely
  to suppress a cycle.
- After the graph is normalized, STATE_ACCUMULATION can be one dbt invocation: dbt
  will order the models from declared dependencies and no selected model will need
  command-level `--full-refresh`.

## Staged migration

### 1. Characterize current behavior

- Freeze the accepted A+B databases as golden inputs.
- Record per-year and per-event-type counts, duplicate multiplicities, schemas, and
  state transition samples.
- Add graph-contract tests for model ownership, duplicate yearly builds, and staged
  models with no consumers.

### 2. Normalize event ownership

- Remove `fct_yearly_events` from the EVENT_GENERATION tag selection.
- Introduce an explicit event-publication step and build the fact exactly once.
- Where a persisted candidate prevents same-command visibility, make the candidate
  a current-year ephemeral/view relation or introduce a dedicated current-year
  union model. Do not read a previous materialization accidentally.
- Preserve the existing command boundaries until event parity is proven.

### 3. Establish canonical workforce state

- Define the workforce-state contract from the columns actually consumed by
  contributions, match, and the final snapshot.
- Implement year N as year N-1 workforce state plus year N workforce events.
- Migrate employer-core and match consumers away from
  `int_workforce_snapshot_optimized`.
- Compare the new state relation with the corresponding accepted snapshot columns
  for every year before removing old logic.

### 4. Simplify snapshot publication

- Rebuild `fct_workforce_snapshot` as a composition of workforce, enrollment,
  deferral, contribution, and match state.
- Remove duplicated event replay and the optimized scratch snapshot.
- Remove the orchestrator's special full-refresh rule only after no consumer depends
  on the old relation.

### 5. Consolidate and measure

- Run the normalized STATE_ACCUMULATION DAG in one dbt invocation per year.
- Re-run full multi-year parity, determinism, stale-rerun, failed-stage, and memory
  gates on both the reference and 60,040-employee Studio configurations.
- Treat invocation reduction as the final consequence of the clean DAG, not as the
  mechanism used to force the redesign.

## Required gates

- Every `fct_*` and `dim_*` mart has bidirectional `EXCEPT ALL` parity with the
  accepted A+B baseline, excluding only documented audit timestamps.
- Event counts match by scenario, plan, year, and event type.
- No current-year event candidate reads `fct_yearly_events`.
- `fct_yearly_events` and `fct_workforce_snapshot` are each published once per year.
- Every staged production model either has a downstream consumer or is explicitly
  documented as an audit output.
- Every temporal table is keyed by scenario, plan, employee, and simulation year as
  applicable; no hard-coded scenario or plan identifiers remain.
- No STATE_ACCUMULATION model requires command-level `--full-refresh`.
- The shared development database remains byte-unchanged; all behavioral validation
  uses isolated databases.

## Scope decision

This work should be specified as a new architecture feature. Feature 121 requires
preserving existing SQL/model behavior and explicitly excludes workforce/DC SQL
redesign. Mixing the two efforts would make parity failures difficult to attribute
and would invalidate Feature 121's per-tier performance evidence.
