# Phase 0 Research: Per-Design Match Formula Families

All findings below come from reading the code as it stands after #631 and #632 merged
(`main` @ `9b13107e`). Line references are to that state.

## Starting observation: #632 did most of the structural work

Issue #633 measured the blast radius as 9+8+7+2+2+2 compile-time branches across six models. That
count was taken before #632 landed. Reading the models now, the per-design code path already exists
and is already runtime-joined; what remains is a much smaller set of literals.

`int_employee_match_calculations.sql` illustrates it. Each family arm already reads:

```sql
INNER JOIN plan_design_match_tiers tier
  ON tier.plan_design_id = ec.plan_design_id
 AND tier.formula_family = 'graded_by_service'      -- literal, per arm
 AND ec.years_of_service >= tier.band_min_value
 AND (tier.band_max_value IS NULL OR ec.years_of_service < tier.band_max_value)
```

and `get_plan_design_match_tiers` (macros/get_plan_design_match_tiers.sql) already emits one relation
covering **all four families for all designs**, with a `formula_family` column per row. So the tier
data is family-agnostic and design-keyed today. The `{% if employer_match_status == ... %}` chain is
the only thing preventing two arms from coexisting.

`int_deferral_match_response_events.sql:163-186` is further along still — its per-design path is a
fully runtime correlated subquery whose only compile-time residue is a single literal
(`tier.formula_family = '{{ employer_match_status }}'`) and a `CASE` that already switches the band
key between points and tenure at run time. That is the proven pattern to copy elsewhere.

**Consequence for the plan**: the work is concentrated in `int_employee_match_calculations` and
`resolve_match_magnet_ceiling`. The other models need a literal swapped for a join.

---

## D1 — How a design declares its formula family

**Decision**: add `family: Literal["deferral_based", "graded_by_service", "tenure_graded",
"points_based"]` to `MatchParameterSet` (`planalign_orchestrator/config/plan_design.py:92`), and emit
it as a new `match_formula_family` column on the existing per-design scalar relation produced by
`get_plan_design_parameters`.

**Rationale**: `MatchParameterSet` already carries all four schedules (`tiers`, `graded_schedule`,
`tenure_graded_bands`, `points_tiers`) side by side, with nothing saying which one is live — the
selector lives outside, in the run-global `employer_match_status`. Moving the selector next to the
schedules is the minimal change that makes the config self-describing per design. Emitting it on the
scalar relation rather than a new relation reuses a join every affected model already performs.

**Back-compat**: `family` defaults to the run-global `employer_match_status` (with the legacy
`tenure_based` → `tenure_graded` migration already implemented at `loader.py:151-153` applied first),
so every existing config loads unchanged and produces the same single-arm run.

**Validation**: `validated_plan_design_parameters` (`loader.py:134-168`) already checks that each
design has the schedule its family requires, using the *global* family. That loop becomes per-design
— the same check, keyed on `design_parameters.match.family`. It additionally rejects a design whose
`family` is set but whose corresponding schedule is empty (FR-007).

**Alternatives considered**:
- *A separate `plan_design_match_family` relation.* Rejected: one column on an existing relation
  costs one less CTE and one less join in five models.
- *Infer the family from which schedule list is non-empty.* Rejected: `MatchParameterSet` permits
  several to be populated at once, so inference would silently pick one. An explicit selector plus a
  validator is the version that fails loudly (FR-007).
- *Keep the selector in `employer_match_status` and add a per-design override map.* Rejected: two
  places to look for the same fact, and the override map would have to be design-set-validated
  separately from the parameters it modifies.

---

## D2 — Runtime dispatch without compiling unused families

**Decision**: restructure the arm chain into `UNION ALL` over the families actually referenced by the
run's design set. Jinja computes the referenced set from `plan_design_parameters` and loops over it;
each arm carries `INNER JOIN plan_design_parameters pdp ON pdp.plan_design_id = ec.plan_design_id
AND pdp.match_formula_family = '<arm family>'` in addition to its existing tier join.

**Rationale**: this satisfies FR-002 and FR-008 simultaneously — dispatch is a run-time join, but the
*set of arms* is still decided at compile time from configuration, so a single-family run compiles
exactly one arm and executes precisely the SQL it executes today. It also means the arm bodies do not
change at all; only their join predicate and their assembly into `all_matches` do. That keeps the
canonical-parity gate (SC-001) meaningful, because a single-design plan produces a one-arm `UNION ALL`,
which DuckDB plans identically to the bare CTE.

Each arm already ends in an identically-shaped projection, so `all_matches` becomes a union of those
projections plus a new `formula_family` column. Downstream, three compile-time sites become runtime:

| Site | Today | Becomes |
|---|---|---|
| `int_employee_match_calculations.sql:454` cap branch | `{% elif employer_match_status in ('graded_by_service','tenure_graded','points_based') %}` | `CASE WHEN am.formula_family IN (...) THEN am.match_amount ELSE LEAST(am.match_amount, ... pdp.match_cap_percent) END` |
| `int_employee_match_calculations.sql:535-547` final identifiers | `{% if/elif %}` over `formula_id`, `formula_name`, `applied_years_of_service`, `applied_points` | `CASE` on `formula_family` |
| `resolve_match_magnet_ceiling.sql:34-46` | `tier.formula_family = '{{ status }}'` plus family-specific band predicate | join on `pdp.match_formula_family`; band predicate becomes the `CASE`-on-family form already used in `int_deferral_match_response_events.sql:169-185` |

**Alternatives considered**:
- *One `CASE` expression computing all families inline per row.* Rejected: the families differ in
  aggregation, not just in rate. `deferral_based` and `tenure_graded` both `GROUP BY` over a tier
  relation to sum cumulative tiers; `graded_by_service` and `points_based` do not aggregate at all.
  A single expression cannot express both grains, which is exactly the ordering/grain risk #633 named.
- *Compile every supported family always and filter empties.* Rejected outright by FR-008, and it
  would make every existing single-design run pay for three unused arms.
- *A per-design macro that emits one full model per design, unioned.* Rejected: cost scales with
  design count rather than family count, and duplicates the shared cap/eligibility logic per design.

---

## D3 — Where the exactly-one-arm guard fires

**Decision**: guard inside `int_employee_match_calculations`, as a CTE that counts arms per
employee-year and forces a runtime error when any count is not exactly 1, with the dbt invocation
correlation identifier, offending employee, design, simulation year, family, count/value, and a
schedule-field resolution hint embedded in the error text. Back it with a dbt singular test
`dbt/tests/data_quality/test_match_formula_arm_coverage.sql` as a second net.

**Rationale**: spec AS-1 requires that no partial match results are published. The VALIDATION stage
runs *after* STATE_ACCUMULATION (`planalign_orchestrator/pipeline/workflow.py:241-247`), and
STATE_ACCUMULATION is where `int_employee_match_calculations`, `fct_employer_match_events`, and
`fct_workforce_snapshot` are all built (`workflow.py:233-236`). A dbt test alone would therefore fail
the run only after the numbers had already been written to published tables. Failing inside the model
stops the year at the first model that could produce a wrong number.

**Why the failure mode is real, not hypothetical**: the family arms use `INNER JOIN` against the tier
relation. An employee whose service, tenure, or points value falls outside every configured band
matches no tier row and is silently dropped from `all_matches` today — a missing row rather than a
wrong number, but equally invisible. Conversely, overlapping bands in a design's schedule produce two
tier rows; for the non-aggregating families (`graded_by_service`, `points_based`) that duplicates the
employee's row, and for the aggregating families it inflates the sum. Both are the failure #633 names.

**Mechanism**: dbt SQL cannot raise. The guard uses a deliberate cast failure — a `CASE` that, on
violation, casts a diagnostic string containing the offending keys to `INTEGER`, which DuckDB reports
as a conversion error carrying that string. Ugly, but it is the only in-SQL abort available and it
produces a message an operator can act on.

**Alternatives considered**:
- *dbt singular test only.* Rejected on AS-1: it fails the run but after publication.
- *Move data-quality tests earlier in the stage list.* Rejected as a larger change than this feature
  should carry: it reorders the pipeline for every model, not just this one, and #612/#611 are
  already open against stage/model-set drift.
- *An orchestrator-side Python assertion after the model builds.* Rejected as a primary mechanism —
  it is one more place the check can be skipped (`validation_mode`, calibration workflow, direct
  `dbt run`) — but it is compatible with the chosen design if ever wanted.

---

## D4 — Which of the six models are actually in scope

**Decision (revised 2026-09-02)**: `int_employee_match_calculations`,
`int_employer_core_contributions`, `int_deferral_match_response_events`,
`int_voluntary_enrollment_decision`, and `int_proactive_voluntary_enrollment` are in scope.
`int_employer_eligibility` and `int_plan_eligibility_override` are **not**.

> **Revision note.** The original survey covered six models named in the issue and concluded four
> were in scope. It missed `int_employer_core_contributions` entirely, which carries the same
> compile-time family branching for employer core contributions. Per the 2026-09-02 clarification,
> grandfathering must work for core as well as match, so core is in scope and this feature covers
> five models. D7-D11 below are the core-side decisions.

**Rationale**: reading the branches shows the last two do not branch on *formula family* at all:

- `int_employer_eligibility.sql:35-69` branches on employer core and match **eligibility rules**
  (`minimum_tenure_years`, `require_active_at_year_end`, `minimum_hours_annual`, `allow_new_hires`,
  `allow_terminated_new_hires`, `allow_experienced_terminations`). These are per-design *parameters*
  of the kind #632 handled, not formula shapes, and they are not in the #632 parameter relation.
  Making them per-design is a Tier 1 follow-up, not part of this feature.
- `int_plan_eligibility_override.sql:47,91-92` branches on `new_hire_eligibility_match_census`, a
  run-global calibration switch unrelated to plan design.

Including them would widen the feature into per-design eligibility rules — real work, but a different
issue. Recommend filing it as a follow-up sub-issue of #571 rather than absorbing it here.

**Impact on spec**: FR-003 is satisfied by the four in-scope models. The two excluded models keep
their current run-global behavior, which is correct for a run where designs differ only in match
formula family.

---

## D5 — `match_template` becomes per-design

**Decision**: move `match_template` into the per-design parameter set alongside `family`.

**Rationale**: the `deferral_based` arm stamps `'{{ match_template }}'` as both `formula_type`
(`int_employee_match_calculations.sql:381`) and `formula_id`/`formula_name` (`:554-555`). It is a
run-global var. In a two-design run where both designs are `deferral_based` with different tiers, or
where one is `deferral_based` and one is not, a single global template label mislabels the output
audit trail. Since the label is purely descriptive it cannot break a number, but it violates
Principle IV (audit reconstruction) and FR-012.

**Alternatives considered**: leaving it global and accepting a shared label. Rejected — it is a
one-line addition to a relation that is already being modified, and the audit trail is the reason the
column exists.

---

## D6 — Validating at 7.5k and 60k without slowing the test suite

**Decision**: two tiers. Extend the existing #632 parity harness in-suite at census 40 and 149; run
the 7.5k and 60k comparisons out of band against isolated databases before merge.

**Rationale**: `tests/integration/test_plan_design_parameters.py:45-60` already builds parity
databases at census 40 and 149 and compares them with `EXCEPT ALL` in both directions plus an ordered
row-hash equality check (`:218-256`). That harness is the right shape and the wrong scale for SC-001,
which asks for 7.5k and 60k. Full multi-year runs at 60k are minutes, not seconds, and belong outside
`pytest -m integration`.

The in-suite tier catches any structural regression (arms produce different rows); the out-of-band
tier is what actually discharges SC-001 and SC-005. Both use isolated databases per the project rule
— never `dbt/simulation.duckdb`.

**Note on baselines**: because event counts are config-dominated, the baseline must be the same
config and seed on `main` at branch point, run into its own database. Comparing against any
previously-captured run under a different config is meaningless.


---

## D7 — Core family dispatch uses a different mechanism than match

**Decision**: dispatch core families with a `CASE` over the design's declared `core_formula_family`
producing a rate per row, not with match's union-of-arms. Each family's branch reads a design-keyed
schedule relation.

**Rationale**: the two models compute at different grains.

- Match builds each family as a **row-producing CTE** (`service_based_match`, `tenure_graded_match`,
  `points_based_match`, `tiered_match`), each `INNER JOIN`ed to a tier relation and unioned into
  `all_matches` (`int_employee_match_calculations.sql:197-421`). Some families aggregate with
  `GROUP BY`. Counting arms per employee-year is natural because arms are rows.
- Core computes the rate as a **scalar expression**, `core_rate_expr`
  (`int_employer_core_contributions.sql:56-69`), inlined once into `integration_basis` at line 310.
  There is one row per employee regardless of family. There are no arms to count.

Forcing core into a union shape would restructure a model that has no correctness defect in its
current shape, enlarging the canonical-parity risk surface (SC-001) for no behavioural gain.

**Alternatives considered**: rewriting core as union-of-arms for symmetry with match. Rejected as
above. The asymmetry is a genuine difference in the domain, not an inconsistency to iron out.

---

## D8 — Core's failure mode is a silent fallback, not a missing row

**Decision**: introduce an explicit `core_rate_source` marker (`'band'` / `'default'`) and abort when
a design whose core family is band-based resolves to `'default'`. Abort likewise on duplicate band
matches, detected before deduplication. Both failures carry the same invocation correlation,
employee/design/year/family context, observed value or multiplicity, and schedule-field resolution
hint as the match guard.

**Rationale**: core cannot produce the zero-arm failure D3 describes, because every band macro ends
in `ELSE {{ flat_rate }}` — see `get_age_banded_core_rate.sql:12` and the `COALESCE(core_schedule.rate,
pdp.employer_core_contribution_rate)` at `int_employer_core_contributions.sql:58`. An employee whose
age or service falls outside every band does not vanish; they are **silently paid the flat default
rate**. For grandfathering this is worse than a missing row: the number is plausible, non-zero, and
indistinguishable downstream from a correctly banded one.

The duplicate case is equally silent. The graded core schedule is joined `LEFT` with a half-open band
predicate (`:356-364`); overlapping bands in a design's schedule produce two rows, and the final
`WHERE rn = 1` (`:423`) discards one arbitrarily — `ORDER BY pop.employee_id` is not deterministic
between duplicate rows of the same employee.

Both cases are the failure class FR-005/FR-006 name, reached by a different route than on the match
side, so the guard is a different mechanism serving the same requirement.

**Scope**: per the 2026-09-02 clarification, the guard applies only to core-**eligible** employee-
years. An employee ineligible for core has their rate zeroed at `:311` (`ELSE 0.00`), so a band gap
cannot corrupt their published number.

**Alternatives considered**: removing the `ELSE flat_rate` fallback from the macros outright.
Rejected — the fallback is correct and load-bearing for the `flat` family and for designs with a
deliberately partial schedule; the defect is that it is indistinguishable from a band hit, not that
it exists.

---

## D9 — Closing the `DBT_VAR_DEFERRED` boundary

**Decision**: add `get_plan_design_core_age_schedule` and `get_plan_design_core_points_schedule`
macros mirroring the existing `get_plan_design_core_graded_schedule`, move
`employer_core_points_schedule` and `employer_core_age_schedule` from `DBT_VAR_DEFERRED` into
`DBT_VAR_PER_DESIGN`, and leave `DBT_VAR_DEFERRED` empty.

**Rationale**: #632 made core rates per-design for `flat` and `graded_by_service` only
(`int_employer_core_contributions.sql:57-61`). The other two families still read run-global Jinja
schedules. This was a deliberate, documented, test-guarded boundary — `DBT_VAR_DEFERRED` at
`planalign_orchestrator/config/export.py:51-53`, with `dbt_var_disposition()` and
`tests/test_dbt_var_coverage.py:195-198` — **not a defect in merged code**. But per-design *family*
selection is meaningless while two of four families cannot carry per-design *rates*: a run where
design A takes `age_banded` core and design B takes `flat` would silently give every design the same
run-global age schedule.

**Note on `DBT_VAR_DEFERRED` becoming empty**: keep the frozenset and `dbt_var_disposition()`'s
three-way return. The taxonomy is the mechanism that made this boundary visible in the first place
(FR-016); an empty deferred set is a meaningful state, not dead code.

**Alternatives considered**: shipping core family selection over the half-per-design layer and
deferring the other two families again. Rejected — it would make two of four families silently
run-global inside a feature whose purpose is eliminating silent per-design wrongness.

---

## D10 — Permitted disparity (integration) moves per-design

**Decision**: move `employer_core_integration_enabled`, `_level_mode`, `_level_value`, and
`_disparity_rate` into the design-keyed parameter relation.

**Rationale**: integration is part of the core formula's shape, not a run control — it changes how the
core rate applies to compensation above the integration level
(`int_employer_core_contributions.sql:369-383`, `get_integrated_core_amounts`). Under the governing
principle recorded in the spec ("a grandfathered cohort keeps the old core"), disparity treatment
travels with the design. Leaving it run-global would let a grandfathered design silently inherit the
new design's disparity settings.

**Cost**: `employer_core_integration_enabled` currently gates the output column list itself
(`:394-422`) — with it per-design, the integration columns must always be projected, with
non-integrated designs producing `NULL`/`0.00` exactly as the `{% else %}` branch does today. That
keeps the output schema stable and is what makes SC-001 checkable.

**Alternatives considered**: keeping it run-global and rejecting configs that vary it. Rejected by
the clarification; recorded here because it remains the smaller change if phase 6 proves expensive.

---

## D11 — The `rn = 1` dedup partition key omits `plan_design_id`

**Decision**: add `plan_design_id` to the `ROW_NUMBER()` partition and re-verify canonical parity.

**Rationale**: `int_employer_core_contributions.sql:328-331` partitions by
`(employee_id, simulation_year)` while every join in the model keys on
`(employee_id, plan_design_id, simulation_year)`. Today this is harmless because #631 makes design
assignment sticky and single-valued per employee, so an employee appears under exactly one design.
It is a latent hazard rather than a live bug — but it is precisely the kind of key omission that
turns into silent row loss the moment a multi-design run does something unanticipated, and this
feature is what makes multi-design runs routine.

**Expected impact on SC-001**: none. With one design per employee the partition is already
equivalent. If the canonical comparison shows any difference here, that difference is itself a
finding worth stopping on.

**Alternatives considered**: leaving it and noting it. Rejected — it is a one-line change inside a
model this feature already modifies, and the invariant it protects is one the feature depends on.

---

## D12 — Canonical per-design family audit metadata

**Decision**: add an additive nullable `design_formula_families_json` column to the existing
append-only `run_metadata` relation. New records contain compact canonical JSON keyed by sorted design
ID, with normalized `match_family` and `core_family` values. Historical rows remain `NULL` and are
never backfilled.

**Rationale**: FR-012 requires the completed run itself to state which families each design used.
The existing `design_set_json` records only identifiers, while the configuration fingerprint proves
that something changed without making the family choices directly inspectable. A neighboring
canonical JSON field provides the missing audit fact without introducing a table, changing row grain,
or weakening append-only history. The effective per-design payload remains in the fingerprint, so
family changes continue to drive drift detection.

**Alternatives considered**:
- *Rely only on the archived effective config.* Rejected because not every direct simulation consumer
  reads the archive, while the database metadata is the common execution audit surface.
- *Add one row per design to a new table.* Rejected because it introduces a second audit grain and a
  new persisted relation for a small deterministic map.
- *Overwrite `design_set_json` with objects.* Rejected because it would break the existing field's
  list contract and historical readers.
