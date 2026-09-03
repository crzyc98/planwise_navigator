# Feature Specification: Per-Design Contribution Formula Families

**Feature Branch**: `633-per-design-formula-families`
**Created**: 2026-09-02
**Status**: Draft
**Tracking**: GitHub #633 — sub-issue of #571; depends on #631 (closed) and #632 (closed)
**Input**: User description: "Grandfathering L2 Tier 2: let two plan designs use DIFFERENT formula families in one run"
**Scope decision**: This feature covers both employer match and non-elective core formula families.

## Product Posture

Grandfathering is an uncommon exception path, expected in roughly one out of every 50 to 100 client
projects. The normal product path remains one plan design applied to the full population. A client
that does not need grandfathering must not configure assignments, duplicate a design, answer new
questions, encounter new warnings, or pay a meaningful execution-time cost because this capability
exists.

When the exception is needed, it must be complete: the legacy and new designs may differ in the
formula family and the actual formula parameters for employer match, non-elective core, or both. The
feature is therefore optimized for a simple default path and a fully correct advanced path, not for
making multi-design setup part of every engagement.

## Background

Issue #631 made plan design a real per-employee, sticky dimension: every employee carries a
`plan_design_id` that never changes once assigned. Issue #632 let the *values* of plan parameters
(match cap, core rate, escalation increment, waiting period, tier schedules) vary by design, by
moving them out of Jinja scalars and into design-keyed relations joined at run time.

What remains is the *shape* of the computation. Plan-design configuration still reaches the SQL as
compile-time Jinja scalars in six production models, so only one formula family's branch is ever
compiled into a run:

| Model | Compile-time branches on plan-design vars |
|---|---|
| `int_deferral_match_response_events` | 9 |
| `int_employee_match_calculations` | 8 |
| `int_employer_eligibility` | 7 |
| `int_voluntary_enrollment_decision` | 2 |
| `int_proactive_voluntary_enrollment` | 2 |
| `int_plan_eligibility_override` | 2 |
| `int_employer_core_contributions` | 7 on `employer_core_status`, plus 5 on `employer_core_integration_enabled` |

A grandfathering run where census employees stay on `deferral_based` while post-cutoff hires move to
`tenure_graded` is therefore impossible today: the two branches cannot coexist in one compiled query.
The same is true of a run where one design takes `flat` core and another takes `age_banded`.

> **Scope decision (2026-09-02).** The original survey needs two corrections, and the business
> scope includes both contribution types.
>
> First, `int_employer_eligibility` and `int_plan_eligibility_override` do not branch on formula
> *family*: the former branches on per-design eligibility **rules** (minimum tenure, hours, new-hire
> allowances), the latter on a run-global calibration switch. Both are out of scope, recorded in
> [research.md](./research.md) D4.
>
> Second, the original six-model survey missed `int_employer_core_contributions`, which carries the
> same defect for employer **core** (non-elective) contributions: `employer_core_status` selects one
> of `flat`, `graded_by_service`, `points_based`, or `age_banded` at compile time from a run-global
> Jinja scalar. Grandfathering applies to core exactly as it applies to match — a client whose legacy
> cohort keeps a historical core formula while new hires fall under a different one is the same
> scenario Story 1 describes. Real-world sponsors may grandfather a match formula, a non-elective
> core formula, or both. Core is therefore in scope, and this specification covers **both** match
> and core contribution formula families.

## Prerequisite Absorbed From #632

#632 made core contribution rates per-design for `flat` and `graded_by_service` only. The other two
core families' schedules — `employer_core_points_schedule` and `employer_core_age_schedule` — are
declared run-global in `DBT_VAR_DEFERRED` (`planalign_orchestrator/config/export.py:51-53`), a
deliberate and documented boundary rather than an oversight, guarded by
`tests/test_dbt_var_coverage.py`. Per-design core *family* selection is meaningless while two of the
four core families cannot carry per-design *rates*, so closing that deferral is part of this feature.

## Clarifications

### Working decisions — 2026-09-02

- Grandfathering may apply independently to employer match and non-elective core contributions. A
  design therefore carries one family for each side, and a sponsor may vary either side or both.
- Formula-resolution checks are evaluated against each side's own eligibility flag: match-eligible
  rows on the match side and core-eligible rows on the core side.
- Employer core integration (permitted disparity) follows the assigned design when core formulas
  are grandfathered, including enabled state, level, and disparity rate.

**Governing principle**: a plan design carries its own match formula and its own core formula; an
employee grandfathered onto a design gets that design's match formula and that design's core formula.
Every requirement below is an expression of that rule.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Grandfathered contribution formulas by hire cohort (Priority: P1)

A plan analyst models a client whose legacy population keeps the historical contribution formulas
while employees hired on or after a cutoff date fall under structurally different ones — for example
a deferral-based match plus a flat core for the legacy cohort, and a tenure-graded match plus an
age-banded core for new hires. The analyst configures two plan designs, each naming its own match
formula family and its own core formula family, runs a multi-year simulation, and receives one result
set in which each employee's match **and** core contribution are computed by the formula families of
the design they are assigned to. The two families are chosen independently: a design may differ from
another in match shape, core shape, or both.

**Why this priority**: Although uncommon across the full client portfolio, this is the requirement
the grandfathering capability exists to serve. When a sponsor needs it, approximating the result with
one population-wide formula is not acceptable.

**Independent Test**: Configure a two-design scenario differing in both match family and core family,
run a multi-year simulation in an isolated database, and verify per-employee match amounts and core
amounts against hand-computed expected values for a sample drawn from each design.

**Acceptance Scenarios**:

1. **Given** a run with design A on `deferral_based` match and `flat` core, and design B on
   `tenure_graded` match and `age_banded` core, **When** the simulation completes, **Then** every
   employee assigned to A has a match and a core contribution computed by A's families, and every
   employee assigned to B has both computed by B's families.
2. **Given** the same run, **When** a sample of employees from each design is hand-verified, **Then**
   each computed match amount and each computed core amount equals the value derived by applying that
   design's respective formula family and that design's parameter values to the employee's
   compensation, deferral rate, service, tenure, and age.
3. **Given** the same run across a multi-year horizon, **When** an employee's design assignment is
   inspected in each year, **Then** the assignment and therefore both formula families applied to
   them are unchanged across all years.
4. **Given** a run with two designs on different families, **When** downstream contribution,
   enrollment-response, and snapshot outputs are inspected, **Then** they reflect the per-design match
   and core amounts rather than a single run-wide formula of either kind.

---

### User Story 2 - Existing single-design runs are unchanged (Priority: P1)

An analyst running the normal single-design engagement — expected in roughly 98% to 99% of client
projects — sees the same workflow and results as before. No grandfathering configuration is required,
no second design is created, and the 60k single-design runtime remains within 5% of baseline.

**Why this priority**: This is the overwhelmingly common user path and the primary defense against
silent numerical drift in the most numerically load-bearing logic in the project. The exceptional
capability is not acceptable if it complicates or changes ordinary engagements.

**Independent Test**: For each supported match family and each supported core family, run the same
scenario before and after the change in isolated databases at two census sizes and compare full result
sets in both directions.

**Acceptance Scenarios**:

1. **Given** a single-design scenario on any supported match family and any supported core family,
   **When** its results are compared against the pre-change baseline over the full multi-year horizon,
   **Then** the symmetric difference between the two result sets is empty in both directions.
2. **Given** the canonical deterministic comparison, **When** it is repeated at both the 7.5k and
   the 60k census, **Then** both sizes are empty in both directions and have equal ordered hashes.
3. **Given** an existing saved configuration written before this change, **When** it is loaded and
   run, **Then** it runs without edits and produces the same results as before.
4. **Given** a single-design run, **When** its wall-clock runtime is compared against the pre-change
   baseline at 60k employees, **Then** it is within 5% of the baseline.

---

### User Story 3 - Employees whose formula does not resolve cleanly fail loudly (Priority: P1)

When a configuration or data condition leaves an employee outside every band of their design's
schedule, or inside more than one, the run stops with a diagnostic naming the employee, the design,
the side (match or core), the condition, the run/stage correlation identifier, and the corrective
schedule action — rather than emitting a plausible-looking number that would be indistinguishable
from a correct one in a downstream report.

**Why this priority**: every one of these failures produces a *plausible* number, not an obviously
broken one. On the match side a gap silently drops the employee's match to zero and an overlap
silently doubles it. On the core side a gap silently pays the design's fallback rate and an overlap
silently resolves to whichever band a deduplication step happens to keep. None of the four is
detectable downstream, which makes this a correctness requirement rather than a hardening nicety. It
is P1 because the per-design formula structure introduced by Story 1 is what makes these conditions
reachable.

**Note on the two sides**: the requirement is one rule — an employee's contribution must be
attributable to exactly one formula — but it is violated in two structurally different ways, because
match resolves a formula by producing rows and core resolves one by computing a rate. The
requirements below state the outcome; the mechanisms are in research.md D3, D7, and D8.

**Independent Test**: Construct four configurations — a match band gap, a match band overlap, a core
band gap, and a core band overlap — run each, and confirm every run fails with a diagnostic that
identifies the affected rows and the side.

**Acceptance Scenarios**:

1. **Given** a configuration under which some match-eligible employee falls outside every band of
   their design's match schedule, **When** the run reaches match calculation, **Then** the run fails
   with a diagnostic identifying the affected employees and their designs, and no partial results are
   published.
2. **Given** a configuration under which some match-eligible employee falls inside more than one band
   or family, **When** the run reaches match calculation, **Then** the run fails with a diagnostic
   identifying the affected employees and what they matched.
3. **Given** a configuration under which some core-eligible employee on a band-based core family
   falls outside every band, **When** the run reaches core calculation, **Then** the run fails with a
   diagnostic naming the employee, the design, the value that missed, the run correlation identifier,
   and the resolution action — rather than paying that employee the design's fallback rate.
4. **Given** a configuration under which some core-eligible employee matches more than one core band,
   **When** the run reaches core calculation, **Then** the run fails with a diagnostic — rather than
   silently keeping one of the matched bands.
5. **Given** a design referenced by at least one employee but with no match family or no core family
   configured, **When** the configuration is loaded, **Then** it is rejected before the simulation
   starts, with a message naming the design and the missing side.
6. **Given** a valid run, **When** the formula-resolution assertions execute on both sides, **Then**
   they pass and the run proceeds without warnings.

---

### Edge Cases

- **Match band gap**: a match-eligible employee whose service, tenure, or points value falls outside
  every band of their design's match schedule. Must fail loudly (Story 3), never produce a zero match.
- **Match band overlap**: overlapping or duplicated bands within a design's match schedule, or an
  employee who satisfies the predicates of two families. Must fail loudly, never produce a doubled
  match.
- **Grain divergence across formulas**: the match families aggregate on different keys today. Each
  side's combined output must present one consistent grain per employee-year per design, so that no
  employee gains or loses rows relative to a single-design run.
- **Deduplication that ignores plan design**: any step that collapses duplicate rows must key on the
  design as well as the employee and year. A dedup keyed on employee and year alone would silently
  merge two designs' rows for the same employee, which is exactly the class of silent wrongness this
  feature exists to remove (FR-019).
- **Two designs, same family, different parameter values**: must continue to work exactly as #632
  delivered it, without being routed through a redundant multi-family path.
- **All designs on one family**: only that family is present in the computation; unreferenced
  families are absent, so a single-family run pays no cost for families it does not use.
- **Legacy family alias**: configurations naming the superseded `tenure_based` value continue to load
  and are treated as the family that superseded it.
- **A design with no assigned employees**: contributes no rows and does not cause a failure.
- **Design assignment changing mid-horizon**: prevented upstream by #631's sticky resolver; this
  feature must not introduce a path that recomputes family per year.
- **Employee with no match-eligible compensation or zero deferral**: yields a zero match through the
  normal formula path, which is a computed zero and must remain distinguishable from an unresolved
  formula.
- **Independent match and core families within one design**: a design declares its match family and
  its core family separately; any combination of the two must be expressible, including a design that
  differs from another only in core shape.
- **Core band gap**: a core-eligible employee whose age, service, or points value falls outside every
  band of their design's core schedule. This is the core-side counterpart of a match band gap, but it
  fails differently: core does not lose the employee's row, it pays them the design's fallback rate.
  The result is a plausible non-zero contribution that is indistinguishable downstream from a
  correctly banded one, so it must fail loudly rather than fall back.
- **Core band overlap**: two bands in a design's core schedule covering the same age, service, or
  points value. This must fail loudly rather than resolve to whichever band a deduplication step
  happens to keep — an outcome that is not only wrong but unstable between runs.
- **Match and core disagreeing on eligibility**: match eligibility and core eligibility are separate
  determinations, so an employee may be eligible for one and not the other. Formula-resolution
  enforcement on each side must key off that side's own eligibility flag.
- **Permitted disparity (integration) under multiple designs**: two designs may differ in whether
  integration is enabled, in integration level, or in disparity rate, and each employee's core is
  computed under their own design's settings (FR-018).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow each plan design in a run to declare its own match formula family
  and its own core formula family, each independently of the other and of every other design in the
  same run.
- **FR-002**: The system MUST compute each employee's employer match using the match formula family,
  and each employee's employer core contribution using the core formula family, of the plan design
  that employee is assigned to, for every year of the horizon.
- **FR-003**: The system MUST apply the same per-design family resolution consistently across every
  in-scope production model — `int_employee_match_calculations`, `int_employer_core_contributions`,
  `int_deferral_match_response_events`, `int_voluntary_enrollment_decision`, and
  `int_proactive_voluntary_enrollment` — so that match calculation, core calculation,
  deferral-response behavior, enrollment decisions, and proactive enrollment all agree on which design
  an employee is on. Per research.md D4, `int_employer_eligibility` and `int_plan_eligibility_override`
  branch on eligibility rules and a run-global calibration switch rather than on formula family, and
  are out of scope.
- **FR-004**: The system MUST produce, for a single-design run on any supported match family and any
  supported core family, canonically identical deterministic results to those produced before this
  feature across the full multi-year horizon. Equality covers every result column except explicitly
  nondeterministic run-timestamp fields such as `created_at`; the permitted exclusions MUST be listed
  by name and compared neither by symmetric difference nor ordered hash.
- **FR-005**: The system MUST fail the run with an actionable diagnostic when an employee's
  contribution cannot be attributed to exactly one formula, on either side, identifying the affected
  employees, their designs, the side that failed, and the value that failed to resolve. The diagnostic
  MUST also carry the current run or stage correlation identifier, enough execution context to locate
  the failing simulation year, and a concrete resolution hint naming the schedule/configuration to
  correct. This covers
  both shapes the failure takes: on the match side, an employee who produces no match row; on the core
  side, a core-eligible employee on a band-based family whose rate falls through to the design's
  fallback. The fallback MUST NOT be silently paid.
  Each side is evaluated against that side's own eligibility determination. Rows ineligible on a side
  are exempt on that side, because their contribution is zeroed regardless of formula.
- **FR-006**: The system MUST fail the run with an actionable diagnostic when an employee's
  contribution could be attributed to more than one formula, on either side, identifying the affected
  employees, what they matched, and which side failed. The diagnostic MUST satisfy the correlation,
  execution-context, and resolution-hint contract in FR-005. On the core side this MUST be detected
  before any deduplication step, since deduplication is what makes an overlapping band invisible.
  Scoped per side by eligibility on the same terms as FR-005.
- **FR-007**: The system MUST reject, before the simulation starts, a configuration in which a design
  that has assigned employees names an unsupported match or core formula family, or omits the schedule
  data either declared family requires.
- **FR-008**: The system MUST exclude formula families not referenced by any design in the run from
  the executed computation, so that run cost scales with families actually used rather than with
  families supported.
- **FR-009**: The system MUST emit one row per employee-year per design at the same grain as a
  single-design run, in both the match and the core outputs, regardless of how many families are in
  use.
- **FR-010**: The system MUST preserve the per-design parameter behavior delivered by #632, including
  the case of two designs sharing a family but differing in parameter values.
- **FR-011**: The system MUST continue to accept configurations that name the superseded legacy
  family alias, treating them as the family that supersedes it.
- **FR-012**: The system MUST record, in the run's audit metadata, which match family and which core
  family each design in the run used as a canonical design-keyed map with normalized family names, so
  that a completed run is self-describing for audit and drift detection. Design keys MUST be ordered
  deterministically; legacy audit records without the map MUST remain readable; changes to either
  family MUST continue to change the effective-configuration fingerprint.
- **FR-013**: Users MUST be able to express a two-design grandfathering scenario that differs in match
  family, core family, or both, entirely through configuration, without code changes.
- **FR-014**: The system MUST provide regression coverage for every currently supported match family
  value and every currently supported core family value, exercised both as a single-design run and as
  one member of a multi-design run.
- **FR-015**: The system MUST make the core age-banded and points-based schedules per-design,
  removing `employer_core_points_schedule` and `employer_core_age_schedule` from `DBT_VAR_DEFERRED`
  and reclassifying them as per-design, so that all four core families can carry per-design rates.
- **FR-016**: The system MUST keep the exported-variable disposition taxonomy
  (`dbt_var_disposition`, `DBT_VAR_PER_DESIGN`, `DBT_VAR_DEFERRED`) accurate and its coverage test
  passing, so that the ownership boundary stays declared rather than implied.
- **FR-017**: The system MUST reject a configuration that supplies per-design values for a core
  schedule the run cannot honor per-design, rather than silently flattening them to a run-global
  value.
- **FR-018**: The system MUST resolve employer core integration (permitted disparity) per design —
  whether integration is enabled, the integration level mode and value, and the disparity rate — so
  that a grandfathered cohort retains the disparity treatment of the design it is assigned to.
- **FR-019**: Every deduplication, aggregation, and uniqueness key in the in-scope models MUST include
  the plan design alongside the employee and simulation year, so that no step can merge or discard
  rows belonging to different designs. Compliance MUST be inspected across all five in-scope models,
  not inferred from the final match and core grains alone.
- **FR-020**: Grandfathering configuration MUST remain optional. In its absence, the system MUST use
  the existing single-design configuration path without requiring a design map, assignment rule,
  duplicated formula, or additional analyst decision.
- **FR-021**: On the normal single-design path, multi-design-only resolution validation MUST NOT run
  unless the selected family's own exactly-one-resolution invariant requires it. Family-computation
  exclusion itself is governed by FR-008.

### Key Entities

- **Plan design**: a named plan configuration within a run. Established by #631 as a per-employee,
  sticky dimension. Gains two new attributes here: the match formula family and the core formula
  family it uses.
- **Formula family**: the structural shape of a contribution calculation — the set of inputs it reads
  and the way it maps them to a contribution amount. Two independent axes:
  - **Match formula family**: deferral-based, service-graded, tenure-graded, and points-based, plus
    one legacy alias of tenure-graded.
  - **Core formula family**: flat, service-graded, points-based, and age-banded.
- **Formula schedule**: the per-design band and tier data a family consumes. On the match side, fully
  exposed as a design-keyed relation by #632, carrying a family label per row. On the core side,
  exposed for flat and service-graded only; extending it to points-based and age-banded is FR-015.
- **Design assignment**: the sticky mapping from employee to plan design, owned by #631. This
  feature consumes it and must not alter it.
- **Formula-resolution assertion**: the run-time check that each eligible employee-year's
  contribution is attributable to exactly one formula, applied independently on the match side and the
  core side; the guard behind FR-005 and FR-006. It takes a different form on each side — counting
  produced rows on the match side, checking rate provenance and band multiplicity on the core side —
  because the two sides resolve a formula differently (research.md D7, D8).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every supported match family and every supported core family, a single-design run's
  full multi-year deterministic result columns differ from the pre-change baseline by zero rows in
  both directions and have the same ordered hash at both the 7.5k and the 60k census. The comparison
  excludes only the explicitly listed nondeterministic timestamp columns permitted by FR-004.
- **SC-002**: A run configured with two designs differing in both match family and core family
  completes successfully and produces per-employee match amounts and core amounts that match
  hand-computed expected values for a sample of at least ten employees drawn from each design.
- **SC-003**: In any successful run, 100% of match-eligible employee-years have their match
  attributable to exactly one formula and 100% of core-eligible employee-years have their core rate
  attributable to exactly one formula, with zero core-eligible rows on a band-based family resolving
  to the fallback rate. Any run in which this does not hold terminates with a diagnostic instead of
  publishing results.
- **SC-004**: Every supported match family value and every supported core family value has regression
  coverage in both single-design and multi-design configurations, with no family left untested.
- **SC-005**: A single-design run's wall-clock time is within 5% of the pre-change baseline at the
  60k census.
- **SC-006**: All behavioral acceptance, parity, failure-publication, and performance validation is
  performed in isolated per-scenario databases over full multi-year simulations, not single-year
  partial builds. Focused unit, configuration, compilation, and relation-contract tests remain valid
  earlier gates; any such test that opens DuckDB uses its own isolated fixture database.
- **SC-007**: An analyst can configure and run a grandfathered scenario whose designs differ in match
  family, core family, or both, using configuration alone, with no changes to simulation logic.
- **SC-008**: All four core formula families accept per-design rate and schedule data, and
  `DBT_VAR_DEFERRED` contains no core schedule variable.
- **SC-009**: Existing single-design configurations require zero new fields and zero additional user
  decisions, and complete within the SC-005 performance boundary.
- **SC-010**: A full multi-year run with at least 100,000 employees completes without a memory error
  on the default single-threaded execution path.

## Assumptions

- **Usage frequency**: approximately 1% to 2% of client projects require grandfathering. This
  estimate determines product posture and default-path priorities, not correctness requirements for
  the projects that use it.
- **Scope of "formula family"**: five production models are in scope —
  `int_employee_match_calculations`, `int_employer_core_contributions`,
  `int_deferral_match_response_events`, `int_voluntary_enrollment_decision`, and
  `int_proactive_voluntary_enrollment`. Per research.md D4, `int_employer_eligibility` and
  `int_plan_eligibility_override` branch on something else and are not. Debug and analysis models
  outside the production path are not in scope either.
- **Number of designs**: the design is not limited to two. Two is the scenario that must be
  demonstrated and hand-verified, but nothing in the requirements caps the count.
- **Supported families**: this feature makes the four existing match families and the four existing
  core families selectable per design. It adds no new formula family on either side.
- **Design assignment**: employee-to-design assignment, its stickiness, and its multi-year stability
  are owned by #631 and are treated here as a working input, not as something to re-verify beyond
  confirming this feature does not disturb it.
- **Per-design parameter values**: the design-keyed parameter and schedule relations delivered by
  #632 are the source of per-design values; this feature adds shape selection on top of them rather
  than introducing a parallel mechanism. On the core side those relations cover only two of the four
  families, so this feature extends them (FR-015) before layering shape selection on top.
- **Reporting grain**: existing marts keep the aggregation grain settled in #631. Breaking marts out
  by design is not introduced here.
- **Baseline for canonical parity**: the pre-change baseline is the tip of `main` at the time this
  feature branches, run under the same seed and configuration. Equality covers all deterministic
  columns; only explicitly named run timestamps such as `created_at` are excluded.
- **Shipping shape**: the requirements describe one feature, but implementation may be reviewed as
  stacked pull requests. A match-dispatch PR may be reviewed first, but it is not independently
  releasable until its resolution guard and the complete P1 acceptance gates are present. plan.md
  marks the review split point.
- **Performance**: single-design runs are expected to be within noise of baseline because unused
  families are excluded (FR-008). Multi-design runs may cost more in proportion to the number of
  families referenced; that increase is accepted and not budgeted here.
- **Failure mode**: formula-resolution violations abort the run rather than warning, on the grounds
  that the resulting numbers are plausible and would otherwise propagate undetected.
- **Match and core independence**: the two family axes are orthogonal. Nothing requires a design's
  match family and core family to be the same shape, and no requirement here constrains their
  combination.
- **Resolution guard follows eligibility**: the guard exists to stop a wrong published number, so it
  is scoped to rows whose contribution can be non-zero on that side. A row ineligible for core is
  exempt from the core guard even if it is match-eligible, and vice versa.
- **The two sides fail differently**: FR-005 and FR-006 read as one rule but are violated in two
  structurally different ways, because match resolves a formula by producing rows and core by
  computing a rate. A match failure loses or duplicates a row; a core failure substitutes a fallback
  rate or silently keeps one of two overlapping bands. Both are plausible, non-zero, and invisible
  downstream, which is why one requirement covers both. The mechanisms differ and are recorded in
  research.md D3, D7, and D8.
- **Existing dedup keys are in scope for FR-019**: at least one in-scope model deduplicates on
  employee and year without the design. This is currently harmless because #631 makes assignment
  single-valued per employee, but this feature makes multi-design runs possible, so the key is
  corrected here rather than left as a latent hazard.
- **#632 was correct**: the `DBT_VAR_DEFERRED` classification of the core age and points schedules was
  a deliberate, documented, test-guarded scope boundary, not a defect. FR-015 closes it as planned
  follow-on work; it is not a fix to previously merged behavior.

## Dependencies

- **#631** (closed): per-employee sticky `plan_design_id`. Supplies the design assignment this
  feature keys on.
- **#632** (closed): per-design plan parameters via design-keyed relations, including the per-design
  match schedule relation that already carries a family label per row, and the per-design core rate
  for the `flat` and `graded_by_service` families. Its deliberate `DBT_VAR_DEFERRED` boundary is
  closed here by FR-015.
- **#571**: the parent grandfathering epic this completes a tier of.

## Out of Scope

- New match or core formula families beyond the four of each currently supported.
- Varying non-plan-design behavior (hazard tables, compensation logic, workforce dynamics) by design.
- Assignment rules other than those delivered by #631.
- Breaking reporting marts out by plan design.
- Removing compile-time branching from debug and analysis models outside the production path.
- Formula families beyond selection: no change to how any individual family computes its amount.
- Per-design employer eligibility **rules** (`int_employer_eligibility`) — a Tier 1-style follow-up
  worth filing as its own sub-issue of #571.
- Studio or CLI surfaces for authoring multi-family designs beyond what configuration already allows.
