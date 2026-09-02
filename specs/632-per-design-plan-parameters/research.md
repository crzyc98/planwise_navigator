# Research: Per-Design Plan Parameters

## Decision 1: Preserve formula families as run-global compile-time selectors

**Decision**: Keep `employer_match_status`, `match_template`, `employer_core_status`, enable/disable flags, and other SQL-shape selectors global. Only numeric parameters and schedules for the selected family vary by design.

**Rationale**: `int_employee_match_calculations.sql` and `int_employer_core_contributions.sql` choose their SQL shape with Jinja branches. Supporting two shapes simultaneously requires a union of family-specific calculations and is the Tier 2 issue, not parameter-level Tier 1.

**Alternatives considered**:

- Put family names in each parameter row: rejected because a keyed value cannot change which Jinja branch dbt compiled.
- Rewrite every family as one universal SQL expression now: rejected as Tier 2 scope and a much larger compatibility risk.

## Decision 2: Add a typed map keyed by plan design

**Decision**: Add `plan_design_parameters: dict[str, PlanDesignParameters]` to both simulation config surfaces. Keys are the design ids; values contain only Tier 1 lever sections. Validate exact key equality with `SimulationConfig.get_plan_design_set()` whenever the map is present.

**Rationale**: #631 already defines the authoritative design set and sticky employee assignment. Exact equality prevents silent fallback from making one assigned population use another design's terms. A mapping naturally rejects duplicate ids and is easy to sort deterministically for dbt export and fingerprints.

**Alternatives considered**:

- An ordered list with `plan_design_id` repeated in each object: rejected because duplicate detection and lookup are less direct.
- Sparse overrides inheriting a global base: rejected for the first version because implicit fallback can hide missing design terms. The exporter will resolve legacy scalars only when no keyed map is supplied.

## Decision 3: Export one scalar relation and narrow repeated relations

**Decision**: Export one deterministic `plan_design_parameters` mapping and render it through macros as:

- `get_plan_design_parameters`: one row per design for match cap, flat core rate, auto-enrollment default/window/scope, escalation increment/cap, and eligibility waiting days;
- `get_plan_design_match_tiers`: flattened match rows with design id, family, service-band bounds where applicable, tier ordinal, employee bounds, rate, and maximum deferral;
- `get_plan_design_core_graded_schedule`: flattened service bands keyed by design and ordinal.

Every macro has explicit column casts and a `WHERE FALSE` empty branch. Tier ordinals are emitted explicitly for deterministic ordering and validation.

**Rationale**: A wide scalar relation avoids repeated parsing and joins. Narrow child relations preserve one-to-many schedules without JSON extraction in business SQL. This generalizes Feature 099's `get_tenure_graded_match_tiers` pattern.

**Alternatives considered**:

- One JSON column per design: rejected because consumers would repeat JSON extraction and type conversion.
- One fully flattened universal table: rejected because cross-products between unrelated match/core schedules would fan out employee rows.
- Persisted seed/model relations: rejected because the configuration is invocation-specific and small; inline relations need no migration or extra pipeline stage.

## Decision 4: Keep the legacy SQL path unchanged when the keyed map is absent

**Decision**: Each consumer uses an outer Jinja branch. If `plan_design_parameters` is absent, retain the existing scalar SQL text and behavior. If present, join the keyed relation and do not fall back to another row or global scalar.

**Rationale**: This protects current default precedence, data types, rounding, fingerprints, and compiled SQL for legacy runs. In keyed mode, inner joins plus cardinality tests make missing parameters visible instead of silently substituting terms.

**Alternatives considered**:

- Always export and join one resolved row: rejected because it changes compiled SQL, relation ordering, fingerprints, and potentially numeric coercion for every existing run.
- `LEFT JOIN` with scalar `COALESCE`: rejected in keyed mode because it masks invalid/missing parameter definitions.

## Decision 5: Move authoritative plan eligibility after assignment

**Decision**: Stop deriving design-sensitive eligibility dates in `stg_census_data`. Introduce or relocate an assignment-aware eligibility relation immediately after `int_plan_design_assignment_accumulator` in EVENT_GENERATION, and route `int_plan_eligibility_determination`, `int_eligibility_events`, enrollment decision models, and snapshot fields through it.

**Rationale**: The present `int_plan_eligibility_determination` is built in FOUNDATION, before the design assignment exists, and three aliases (`eligibility_waiting_days`, `eligibility_waiting_period_days`, `plan_eligibility_waiting_period_days`) are consumed independently. A per-design scalar cannot be correct until the assignment is known. One authoritative post-assignment relation prevents event dates, enrollment dates, and snapshot dates from diverging.

**Alternatives considered**:

- Recompute the hire-date cutoff independently in eligibility: rejected because assignment must remain sticky and rule evaluation must not be duplicated.
- Leave staging dates global and adjust only events: rejected because audit/snapshot fields would contradict event eligibility.

## Decision 6: Make all consumers of a derived parameter design-aware

**Decision**: Convert not only headline calculators but every consumer of the same parameter. In particular:

- the match-maximizing ceiling used by voluntary enrollment, proactive enrollment, and match-response events must be derived from the employee's design tiers;
- escalation caps in event generation, state accumulation, match response, and data-quality checks must use the same design row;
- enrollment event generation must join the assignment accumulator before using default rate, window, or scope;
- joins between employee-level persisted relations must include `scenario_id`, `plan_design_id`, `employee_id`, and `simulation_year` whenever available.

**Rationale**: Partial conversion would produce internally inconsistent decisions even if the final contribution calculator were correct. Complete join keys also prevent cross-design fan-out.

**Alternatives considered**: Convert only contribution amount models; rejected because behavior-generating models consume the same terms upstream.

## Decision 7: Vesting is deferred as an explicit architecture gap

**Decision**: Do not add a fake vesting dbt relation in Tier 1. Record vesting as deferred and open a follow-up that changes vesting/forfeiture analytics to select schedules per terminated employee's `plan_design_id`.

**Rationale**: There is no effective vesting dbt var or simulation vesting model. `planalign_api/services/vesting_service.py` accepts one request-level `VestingScheduleConfig` and applies it globally. A relation unused by the simulation would satisfy neither behavior nor acceptance. Correct support requires an API/service contract decision, archived config lookup, and cohort-specific forfeiture tests.

**Alternatives considered**:

- Export a vesting schedule row with no consumer: rejected as misleading dead configuration.
- Expand the current issue into API/UI changes: rejected because it is materially different from dbt parameter conversion and would obscure the Tier 1 hard gate.

## Decision 8: Define byte identity over deterministic row content

**Decision**: The compatibility hard gate is bidirectional `EXCEPT ALL` equality and stable ordered row hashes for deterministic columns, excluding only explicitly listed wall-clock metadata such as `created_at` and `snapshot_created_at`. Compare at two census sizes across full multi-year runs.

**Rationale**: DuckDB files and tables containing `CURRENT_TIMESTAMP` cannot be physically byte-identical across executions. This definition matches the existing #631 regression test while making the semantic content gate exhaustive.

**Alternatives considered**:

- Compare DuckDB file hashes: rejected as nondeterministic and unrelated to business output.
- Compare only aggregate totals: rejected because employee-level leakage can net to the same total.

## Decision 9: Use a dedicated isolated validation suite

**Decision**: Add `tests/fixtures/plan_design_parameters/` and `tests/integration/test_plan_design_parameters.py`; do not add an eighth case to Feature 124's capped edge-config catalog. Reuse the isolated `ConstructionSpec`, `DATABASE_PATH`, and shared-database signature guard patterns.

**Rationale**: The feature needs multiple years, design-aware employee fixtures, hand calculations, and cardinality checks. A dedicated suite is clearer and avoids violating the existing edge matrix's measured seven-case performance ceiling.

**Alternatives considered**: Add cases to the generic edge matrix; rejected because that catalog deliberately caps its runtime and does not express paired employee/design assertions well.
