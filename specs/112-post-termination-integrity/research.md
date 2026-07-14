# Research: Post-Termination Event Integrity

## Baseline diagnosis

**Decision**: Treat the supplied archived run as a confirmed generator defect and use its privacy-safe aggregates as the acceptance baseline.

**Rationale**: A read-only query against the archived database reproduced the exact validator totals without returning employee identifiers:

| Year | Eligibility | Enrollment | Enrollment change | Total |
|---:|---:|---:|---:|---:|
| 2026 | 44 | 23 | 6 | 73 |
| 2027 | 70 | 21 | 4 | 95 |
| 2028 | 70 | 29 | 7 | 106 |
| 2029 | 69 | 22 | 3 | 94 |
| 2030 | 62 | 23 | 6 | 91 |
| **Total** | **315** | **118** | **26** | **459** |

The safe causal split is 451 same-year new-hire events and eight experienced-employee events. Event categories are 315 eligibility, 90 auto-enrollment, 27 proactive voluntary enrollment, one year-over-year voluntary enrollment, and 26 enrollment opt-outs. There were no promotion, raise, or deferral-escalation violations in this archive.

A second read-only aggregate query during implementation reconfirmed the full 459-row result without selecting identifiers, dates, compensation, event details, or physical paths. It grouped only by year, normalized event type, and termination cohort. The yearly totals remained 73, 95, 106, 94, and 91; the cohort split remained 451 same-year new hires and eight experienced employees.

Eligibility failures originate from the current-year hire population. Enrollment failures originate from auto-enrollment, proactive voluntary enrollment, the single year-over-year voluntary decision, and enrollment opt-out candidates evaluated from current-year workforce/hire state without intersecting their candidate dates with termination. Contribution and deferral-state events derive solely from the corrected eligibility/enrollment state and therefore sit downstream of the correction boundary; they require no separate generator filter, but remain covered by authoritative sequence validation and multi-year non-resurrection tests.

### Immutable baseline fingerprint

The supplied run archive was fingerprinted before implementation. Only logical artifact names, SHA-256 digests, and modification times are recorded; no employee-level rows were persisted.

| Artifact | SHA-256 | Modified (America/New_York) |
|---|---|---|
| `AE All Elig_results.xlsx` | `6262d9811b008302dca3f75a2d23ba4db1fcff552a66245e507b58e5b603f9b6` | `2026-07-13T18:36:26-0400` |
| `config.yaml` | `2f0e8ebed0350be9b2b919437281d8bbeed01d250160c51365451fff0ac5a64a` | `2026-07-13T18:36:01-0400` |
| `provenance.json` | `fce3808976afe8c915e83c9003c101c3d4888d648872b382d43844921532a47c` | `2026-07-13T18:36:26-0400` |
| `run_metadata.json` | `f1778c828234f7059b2e434cad6d2cd640b1a5a2b996cf98fea5ebd0bf36552e` | `2026-07-13T18:36:01-0400` |
| `simulation.duckdb` | `c6469e6cae6b148129c554c7bf2f373fb235de289a6a36e526cf8c218addac4d` | `2026-07-13T18:35:59-0400` |
| `simulation.log` | `43fa5fca4c2bed571c7b502d188399c0b14670cddea192a160961a10e52fb79e` | `2026-07-13T18:36:01-0400` |

**Alternatives considered**: Treat the failures as another report defect. Rejected because the corrected validator executed successfully, returned numeric counts, and the archived fact rows reconcile exactly to those counts.

## Root cause

**Decision**: Correct active-at-start candidate generation that ignores current-year termination timing.

**Rationale**: Experienced and new-hire terminations are built before eligibility and enrollment. `int_eligibility_events` reads new hires without their termination dates. `int_enrollment_events` labels all current-year hires active and uses annual start-state status for experienced employees. Its auto, proactive, year-over-year, and opt-out dates are never intersected with the already-known termination boundary. The same start-state assumption could affect promotion or a configured later deferral date even though those paths did not fail in the supplied run. `int_merit_events` already demonstrates the desired cutoff behavior.

**Alternatives considered**: Exclude anyone who terminates at any point during the year. Rejected because it would remove valid events before or on termination. Change event priority or sequencing. Rejected because ordering cannot correct an invalid effective date.

## Shared termination boundary

**Decision**: Add one ephemeral `int_employee_termination_dates` relation that unions experienced and new-hire termination outputs and exposes the earliest effective termination date per employee and simulation year.

**Rationale**: Both sources are available earlier in EVENT_GENERATION. A shared `ref()` keeps all producers on identical earliest-date and same-day semantics without reading `fct_yearly_events`, adding persisted cleanup obligations, or duplicating unions across models.

**Alternatives considered**: Duplicate the two-source CTE in every producer. Rejected because semantics can drift; merit already has a local copy. Materialize a new table. Rejected because the relation is small, current-year only, and does not need independent lifecycle state.

## Producer enforcement boundary

**Decision**: Apply `candidate_effective_date <= termination_date OR termination_date IS NULL` within each affected event producer. In enrollment, filter the combined candidates before category prioritization and deduplication.

**Rationale**: Generator-level enforcement prevents invalid activity from influencing event/state consumers while retaining valid earlier activity. Pre-deduplication filtering is essential: removing an invalid higher-priority voluntary event after prioritization could also discard a valid earlier auto-enrollment candidate. Eligibility, enrollment, promotion, merit, and configurable deferral paths will share the invariant. Match-response remains covered by validation and can consume the helper if its fixed January timing becomes configurable.

**Alternatives considered**: Filter only in `fct_yearly_events`. Rejected because the authoritative result would look clean while defective intermediate generators remain hidden and could influence downstream candidate logic. Post-build deletion is rejected because it conflicts with immutability. Validator exclusions or severity changes are explicitly rejected.

## Validation semantics

**Decision**: Validate each candidate year against the employee's earliest termination across all years in the same scenario and plan design. Continue to count non-termination event records strictly later than termination, preserve ERROR severity, and allow same-day events.

**Rationale**: The current Python rule correctly uses `MIN(effective_date)`, strict `>`, and exact affected counts, but limits termination lookup to the candidate year. The feature requires protection against events in later years after an earlier termination. Production scope columns prevent cross-scenario or cross-plan contamination. No explicit rehire/reinstatement event exists, so later activity must not silently start a new employment period.

Missing or invalid dates remain a separate completeness failure. Duplicate termination rows use the earliest date and do not multiply candidate counts. Event type comparisons are case-normalized. The active dbt integrity test will use the same semantics.

**Alternatives considered**: Infer rehire from a later hire or active snapshot. Rejected because no authoritative rehire event exists. Join every termination row. Rejected because duplicate terms multiply violations. Keep the current same-year-only rule. Rejected because it cannot enforce prior-year termination state.

## Privacy-safe diagnostic contract

**Decision**: Persist only aggregates with `simulation_year`, `event_type`, `termination_cohort`, `generation_path`, `state_source`, and `affected_event_count`, sorted deterministically.

**Rationale**: These dimensions can reconcile yearly and grand totals while identifying the faulty generator and state source. Diagnostics must not include employee ID, SSN, compensation, exact dates, event details, physical paths, or pseudonymous employee keys. Employee-level inspection may occur transiently inside the isolated diagnostic database only.

**Alternatives considered**: Reuse existing violation-detail models or hash employee IDs. Rejected because both preserve unnecessary employee-level linkage and the existing detail models expose direct identifiers and dates.

## Provenance disposition

**Decision**: Recompute the manifest's overall validation disposition from every captured yearly result after each ingestion, using failed-error precedence, then failed-warning, then passed.

**Rationale**: Current ingestion replaces the manifest disposition with the latest year's value. A later passing year can therefore mask an earlier failure even though per-year results remain present. The report must express the complete run disposition monotonically while preserving every exact yearly row.

**Alternatives considered**: Let report rendering rediscover the aggregate every time. Rejected because the execution manifest itself would remain internally inconsistent and other consumers could trust the wrong field.

## Event-mode scope

**Decision**: Implement and validate the supported SQL path and retain a compatibility test proving legacy Polars configuration resolves to SQL.

**Rationale**: The orchestrator and configuration exporter force SQL event generation; legacy Polars fields remain for configuration compatibility, but no supported Polars execution implementation remains. Dual-engine work would invent scope unrelated to the production failure.

**Alternatives considered**: Modify the dormant Polars branch in the fact model. Rejected because it is unreachable in supported execution and a fact-level filter would conceal generator errors.

## Build-order integration

**Decision**: Keep termination, hiring, and new-hire termination first; make all cutoff consumers depend on the ephemeral boundary; explicitly align workflow and executor model lists, including eligibility and match-response entries that currently differ.

**Rationale**: All work remains in EVENT_GENERATION. `fct_yearly_events` remains first in STATE_ACCUMULATION, followed by temporal state accumulators and the workforce snapshot. Explicit parity avoids an alternate execution path reusing stale materialized event rows.

**Alternatives considered**: Move cleanup into STATE_ACCUMULATION. Rejected because invalid events would already have entered the event stream and may affect accumulators.

## Verification strategy

**Decision**: Use test-first synthetic fixtures, an isolated five-year reproduction, a second deterministic repeat, and a copied-workspace Studio acceptance run.

**Rationale**: Synthetic cases cover before/same-day/after termination, experienced and new-hire cohorts, duplicate terms, prior-year termination, scenario/plan isolation, missing dates, and affected event families. Full simulations prove annual reconciliation and downstream behavior. Determinism compares ordered event/reconciliation/validation aggregates rather than timestamps or UUID audit fields. Performance compares equivalent isolated runs and allows no more than 10% regression.

All behavioral writes target disposable databases under `/tmp`; the supplied archive, live scenario database, and shared development database are read-only throughout.

**Alternatives considered**: Validate a few dbt models in the shared database or run only one simulation year. Rejected because both can hide temporal accumulator and later-year state defects.

## Corrected aggregate delta

Two complete corrected runs produced identical ordered year/type event counts and closing-workforce aggregates. Compared with the archived baseline, only the diagnosed families changed:

| Year | Eligibility delta | Enrollment delta | Enrollment-change delta |
|---:|---:|---:|---:|
| 2026 | -44 | -22 | -6 |
| 2027 | -70 | -21 | -4 |
| 2028 | -70 | -29 | -7 |
| 2029 | -69 | -22 | -3 |
| 2030 | -62 | -23 | -6 |
| **Total** | **-315** | **-117** | **-26** |

The event-count delta is 458 rather than 459 because one invalid higher-priority enrollment candidate is removed before prioritization, allowing a valid earlier enrollment candidate for the same employee/year to survive. Thus all 459 invalid candidates are prevented while one employee retains a valid replacement event. No unrelated event family changed.
