# Phase 0 Research: Explicit New-Hire Enrollment Rates

**Feature**: 652-flat-newhire-enrollment-rates
**Date**: 2026-09-04

All findings below were verified by direct inspection of the code at the cited locations. Two items (R6, R7) could not be settled by inspection alone and carry a runtime verification task.

---

## R1 — The multiplier is a no-op at its default, so removing it is behavior-preserving when unset

**Decision**: Delete `voluntary_enrollment_rate` from all three demographic-probability expressions rather than special-casing it.

**Evidence**: The variable appears in exactly three probability expressions, always in the identical form `COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)`:

| Location | Path |
|---|---|
| `dbt/models/intermediate/int_voluntary_enrollment_decision.sql:211` | continuing + new hire voluntary |
| `dbt/models/intermediate/int_proactive_voluntary_enrollment.sql:251` | new hire proactive voluntary |
| `dbt/models/intermediate/int_enrollment_events.sql:549,584` | year-over-year conversion |

`dbt/dbt_project.yml:261` sets it to `1.0`. Multiplying by 1.0 changes nothing, so with the value unset every one of these three sites is already inert.

**Consequence**: FR-012 ("unset preserves existing behavior") is satisfied for the continuing-employee and year-over-year paths by deletion alone — no compatibility branch is needed there. Only the new-hire path needs a set/unset branch.

**Alternatives considered**: Keeping the multiplier on the continuing path and branching on whether the new rate is set. Rejected — it preserves the exact confusion the feature exists to remove, and the deletion is provably equivalent at the default.

---

## R2 — Studio ships an explicit default of 30%, which contradicts the "unset by default" assumption

**Decision**: Change the Studio form default to empty (unset), and treat Studio scenarios saved with the old explicit `0.30` as an accepted behavior change under FR-013.

**Evidence**:
- `planalign_studio/components/config/constants.ts:186` — `dcVoluntaryEnrollmentRate: '30'`
- `planalign_studio/components/config/buildConfigPayload.ts:95` — emits the key whenever the field is not `''`

So a Studio scenario created with untouched defaults stores `voluntary_enrollment_rate: 0.30`. Under the old meaning that was a 0.3× multiplier (~17% realized enrollment); under the new meaning it is a flat 30%. **Those scenarios will change behavior.**

**This corrects the assumption recorded during specification.** The Python layer's default is genuinely `None` (`planalign_orchestrator/config/workforce.py:74`) and the export path genuinely omits the variable when unset (`config/export.py:193`, via `_set_if_not_none`) — so YAML-driven and CLI-driven scenarios are unaffected as stated. The gap is Studio-only: its form default was never `''`.

**Consequence**: FR-012's guarantee holds for YAML/CLI scenarios and for Studio scenarios where the analyst cleared the field. It does not hold for Studio scenarios carrying the default `0.30`. This is a scope decision the plan surfaces rather than absorbs — see the Open Decision at the end of this document.

**Alternatives considered**: A one-time migration writing `''` into stored Studio scenarios. Deferred — it requires knowing where Studio scenarios persist and whether they are versioned; a smaller, more honest option is to change the default forward and let the existing scenarios flip visibly under a relabeled field.

---

## R3 — New hires get two independent enrollment draws with different hash seeds

**Decision**: Route the new-hire voluntary decision through a single draw in `int_voluntary_enrollment_decision`, and restrict `int_proactive_voluntary_enrollment` to timing only (or retire its decision entirely) when the flat rate is set.

**Evidence**: Both models compute the same probability from the same demographic inputs but draw against different seeds:

| Model | Seed string |
|---|---|
| `int_voluntary_enrollment_decision.sql:202` | `employee_id \|\| '-voluntary-enroll-' \|\| year` |
| `int_proactive_voluntary_enrollment.sql:243` | `employee_id \|\| '-proactive-voluntary-' \|\| year` |

`int_voluntary_enrollment_decision` includes hire-year new hires (its `new_hires_current_year` CTE, added by Feature 096). `int_proactive_voluntary_enrollment` covers only new hires and is gated on `auto_enrollment_enabled`. So a new hire under auto-enrollment is drawn twice, and `int_enrollment_events.sql:734-748` resolves the collision by priority: `voluntary_enrollment` (1) > `proactive_voluntary` (2) > `year_over_year_voluntary` (3) > `auto_enrollment` (4).

Two independent Bernoulli draws at probability p yield an effective enrollment rate of `1 − (1−p)²`, not `p`. This is a second reason the realized share does not match any configured number, distinct from the demographic-ceiling problem in the issue.

---

## R4 — Enrollment source labels survive deduplication, but the proactive category is already mislabeled

**Decision**: FR-011 needs no new plumbing. It does need one existing alias bug fixed as part of collapsing the paths.

**Evidence**: `event_category` is assigned in each source CTE and passed through the union unchanged; `deduplicated_events` only picks a winning row, it does not rewrite the label. So the four outcomes in the reproduction table are already attributable.

However, `int_proactive_voluntary_enrollment.sql:361` emits `event_category = 'proactive_voluntary'`, while `int_enrollment_state_accumulator.sql:58` maps to `enrollment_method = 'voluntary'` only for `('voluntary_enrollment', 'proactive_enrollment', 'executive_enrollment')` — **`'proactive_voluntary'` is absent from that list.** Proactive enrollees therefore get `enrollment_method = NULL` and reach the `participating - voluntary enrollment` bucket only through the `enrollment_method IS NULL AND enrollment_source LIKE 'event_%'` fallback at `dbt/models/marts/fct_workforce_snapshot.sql:301-303`.

The reported numbers are correct by accident. Collapsing the two paths removes the alias, but the plan must confirm the surviving category is a member of the accumulator's list or the snapshot labeling silently changes.

---

## R5 — The flat opt-out rate needs a new field; it cannot reuse `opt_out_rates.target`

**Decision**: Add a new-hire-scoped opt-out setting alongside the existing `opt_out_rates.target`, which keeps its current demographic meaning.

**Evidence**: `planalign_orchestrator/config/workforce.py:50-55` defines `OptOutRatesSettings.target` as a required float defaulting to `0.09`, expanded into eight demographic dbt vars by `config/export.py:197-206`. Because it is never unset, it cannot carry the unset/set convention from FR-015 without changing meaning for every existing scenario.

More importantly, FR-002 scopes the flat opt-out to **auto-enrolled new hires**. Continuing employees who are auto-enrolled must keep the demographic opt-out model (FR-007). A single field cannot serve both meanings, so the two settings are genuinely distinct concerns and a second field is the correct shape — this does not conflict with FR-014, which forbids only a second *voluntary* control.

**Consequence**: The opt-out CTE at `int_enrollment_events.sql:340-421` must branch on whether the row is a hire-year new hire, which it can already express — the pattern `EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year` is used at line 346.

---

## R6 — RESOLVED: the "not enrolled" bucket is the waiting period, not a defect

**Status**: Verified against the reproduction database (run `9f0780c3`, seed 42, read-only copy). The hypothesis recorded here earlier — that the residual was new hires terminating inside the 45-day auto-enrollment window — was **wrong**.

**Finding**: The residual is entirely explained by plan eligibility and termination, in that order:

| Year | Not enrolled (all new hires) | Still active at year end | Of those, plan-eligible |
|---|---|---|---|
| 2026 | 343 | 197 | **0** |
| 2027 | 369 | 215 | **0** |
| 2028 | 426 | 247 | **0** |
| 2029 | 465 | 283 | **0** |
| 2030 | 459 | 265 | **0** |

Every active new hire in the issue's "not auto enrolled" row is `current_eligibility_status = 'pending'` — inside the config's three-month waiting period (`eligibility_months: 3`). None of them is eligible, so none of them belongs in the denominator the spec defines.

Restricted to **eligible** new hires, the distribution is:

| Year | Voluntary | Auto | Opted out | Not enrolled |
|---|---|---|---|---|
| 2026 | 73.1% | 20.3% | 3.2% | 3.4% |
| 2027 | 71.8% | 23.5% | 2.3% | 2.3% |
| 2028 | 75.6% | 19.9% | 2.6% | 1.8% |
| 2029 | 72.7% | 20.7% | 3.2% | 1.8% |
| 2030 | 73.5% | 20.8% | 2.4% | 3.3% |

And the small not-enrolled residual is **100% terminated employees, zero still active**, in all five years.

**Consequences**:

1. **SC-004 needs no amendment.** No eligible, active new hire ends the year unenrolled today. The four-outcome guarantee is already met on the population the spec names; the flat rates only need to preserve it. Decision D2 is closed — the answer is "no change required".
2. **The residual to expect is hire-year terminations**, currently 2-3% of eligible new hires. SC-004's 1% threshold should be measured over new hires **active at year end**, where the observed value is already 0%. That is a measurement clarification, not a behavior change.
3. **The realized voluntary share of ~73% independently confirms R3.** A single demographic draw would land near 58%. The excess is the second, independent proactive draw compounding: two draws at p give `1 - (1-p)^2`. This is direct evidence that the double-draw is a real and separate cause of the mismatch, not just a theoretical one.

**Method**: read-only query against a copy of the run's `simulation.duckdb`; the original was not opened for writing. Queries are preserved in `quickstart.md` step 1.

## R7 — Integer rounding behavior for the flat draw

**Decision**: Use the existing hash-modulo idiom, and accept per-cohort rounding rather than forcing an exact count.

**Rationale**: Every deterministic draw in this pipeline is `(ABS(HASH(employee_id || '-<purpose>-' || year)) % 1000) / 1000.0` compared against a threshold. Reusing it for the flat draw keeps the reproducibility guarantee (Constitution I) and the codebase idiom, and it makes `rate = 0.0` and `rate = 1.0` exact at the boundaries because the draw is in `[0, 0.999]`.

It does **not** guarantee that a cohort of 1,000 yields exactly 600 enrollees at `P = 0.6` — the hash is uniform in distribution, not stratified. Expected deviation for a cohort of ~870 new hires is roughly ±1.7 percentage points at one standard deviation, which **exceeds SC-001's stated ±1 point tolerance** in a meaningful fraction of years.

**Options**: (a) widen the SC-001 tolerance to ±2 points, or (b) rank new hires by hash within the cohort and take the top `P × N`, which makes the realized share exact to within one employee. Option (b) is a small change — `PERCENT_RANK() OVER (PARTITION BY simulation_year ORDER BY hash)` in place of a raw threshold — and it delivers what an analyst actually expects from "60%". Recommended, but it is a behavioral choice the spec did not make, so it is listed as an open decision.

**Alternatives considered**: Seeding a per-cohort shuffle in Python. Rejected — it moves a decision out of the dbt layer for no benefit and breaks the single-source-of-truth pattern for event generation.

---

## Open decisions requiring an answer before implementation

| # | Decision | Recommendation |
|---|---|---|
| D1 | Studio scenarios storing the old default `0.30` will flip meaning (R2). Accept, or migrate them to unset? | Accept and relabel. Migration hides a change that the analyst should see, and the field is being renamed anyway. |
| D2 | ~~SC-004 may be unreachable~~ **CLOSED** by the R6 verification: no eligible, active new hire is unenrolled today. | No spec amendment needed. Measure SC-004 over new hires active at year end, where the observed baseline is already 0%. |
| D3 | Exact-count selection versus threshold draw (R7). | Use rank-based selection so the realized share matches the stated rate to within one employee; keeps SC-001 at ±1 point. |
