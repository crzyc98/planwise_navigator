# Implementation Plan: Trustworthy Promotion Rate from a Census Without Job Levels

**Branch**: `130-promotion-fit-bias` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/130-promotion-fit-bias/spec.md`

## Summary

`planalign fit` currently reads a promotion as a move to a higher `level_id`. Without that column level is derived from compensation banding, so any merit raise crossing a band boundary registers as a promotion — a true 6% rate fits at 16.8%.

The fix replaces the band-crossing signal with a **two-component mixture on the per-level compensation-growth distribution**, fitted by a deterministic EM. The ordinary-raise component and the promotion component are identified *simultaneously*, which is what breaks the circularity the issue flagged: promotion is no longer defined in terms of a merit rate that was itself measured off the promotion classification. EM's posterior responsibilities become a **promotion weight** per transition, and that single quantity feeds both estimates — summed it gives the expected promotion events the existing IPF solver turns into age/tenure multipliers (FR-003a), inverted it weights the merit median (FR-008).

A per-level separation test (BIC plus a standardized-distance floor) decides whether the mixture actually resolved two components. Levels that fail retain their configured default; if the levels that separated cover under half the experienced exposure, the whole promotion hazard is reported not fitted (FR-004a). Routing to this path is by **job-level coverage** rather than column presence, which also closes a live silent-mixing bug in the current code.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: numpy ≥1.24 (already declared, `pyproject.toml:20`) for the EM inner loop; DuckDB (in-memory, already used by the fitter); no new dependencies
**Storage**: None. `fit_parameter_pack` runs entirely in an in-memory DuckDB (`runner.py:66`) and never touches a simulation database, shared or isolated. Output is a parameter-pack directory.
**Testing**: pytest; `tests/test_parameter_fitting.py::TestRoundTrip` is the graded harness; `tests/fixtures/synthetic_census.py` generates ground truth
**Target Platform**: macOS/Linux work laptops, offline
**Project Type**: Single project — a library (`planalign_fit`) behind a Typer CLI (`planalign_cli/commands/fit.py`)
**Performance Goals**: EM adds one pass per level over the transition table. At the constitution's 100K-employee bar with 5 levels and a 200-iteration cap this is ~10⁸ float ops in vectorized numpy — well under a second, against a fit that already spends seconds in DuckDB. No user-visible change to fit runtime.
**Constraints**: **Fully deterministic** — no RNG anywhere in the estimator (see Constitution I). Fixed initialization, fixed iteration cap, fixed tolerance. Two runs over identical snapshots must produce byte-identical packs, since the pack fingerprint is a content hash (`pack.py:14`).
**Scale/Scope**: 2–5 annual snapshots, up to ~100K employees per snapshot, 5 job levels

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design. Both passes clean.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Event Sourcing & Immutability** | The fitter reads census files and writes a pack; it creates no events and touches no event store. The binding clause is **reproducibility**: "All simulation outcomes MUST be reproducible given the same random seed and configuration." An EM with random restarts would violate this, since the pack fingerprint is a content hash. Design response: deterministic prior-anchored initialization, no RNG, fixed convergence criteria. A determinism test is a first-class deliverable. | **PASS** |
| **II. Modular Architecture** | Two new modules, each single-purpose, mirroring the existing `ipf.py` (pure solver) / `hazards.py` (domain) split: `mixture.py` (~180 lines, pure numerics, no domain knowledge) and `promotion.py` (~260 lines, routing + separation verdict + weights). Both well under the ~600-line ceiling with ≤8 public functions each. No new layer and no circular imports: `promotion.py` → `mixture.py`, `priors.py`, `transitions.py`, all existing downward edges. | **PASS** |
| **III. Test-First Development** | Every task in the Phase 2 outline pairs a test with its implementation, tests first. The graded round-trip harness already exists and is extended before the estimator is written. Fast-suite budget respected: the EM unit tests run on synthetic arrays in milliseconds; the 9,000-employee round-trip fit stays in the existing module-scoped fixture, outside `-m fast`. | **PASS** |
| **IV. Enterprise Transparency** | This feature is largely *about* transparency — FR-005, FR-006, FR-004b, FR-001d, FR-017 all mandate report disclosure, and FR-010 extends pack provenance so a downstream run records whether promotion was fitted or defaulted. Strictly additive to the audit trail. | **PASS** |
| **V. Type-Safe Configuration** | New thresholds are typed fields on the frozen `FitOptions` dataclass with explicit validation at the CLI boundary (`fit.py` already validates `--credibility-k`/`--min-exposure`). Note: `planalign_fit` deliberately uses frozen dataclasses rather than Pydantic — the principle governs *simulation configuration* (`SimulationConfig`), which this feature does not touch. Following the package's local convention is the right call; introducing Pydantic into one corner of `planalign_fit` would be the inconsistency. | **PASS** |
| **VI. Performance & Scalability** | See Performance Goals. Vectorized numpy, single-threaded, no new memory pressure — the transition table is already fully materialized. | **PASS** |

**No violations. Complexity Tracking table omitted (fill only on violations).**

## Project Structure

### Documentation (this feature)

```text
specs/130-promotion-fit-bias/
├── plan.md              # This file
├── research.md          # Phase 0: estimator choice, separation test, determinism
├── data-model.md        # Phase 1: entities, fields, state transitions
├── quickstart.md        # Phase 1: how to run and grade the change
├── contracts/
│   ├── cli-fit.md       # CLI surface: new flags, exit codes, validation
│   ├── fit-report.md    # fit_report.md sections this feature adds or changes
│   └── pack-provenance.md  # manifest + param_pack provenance additions
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output — NOT created by /speckit.plan
```

### Source Code (repository root)

```text
planalign_fit/
├── mixture.py           # NEW ~180 LOC — deterministic 2-component EM, pure numerics
├── promotion.py         # NEW ~260 LOC — coverage routing, separation verdict, weights
├── transitions.py       # CHANGED — level coverage measurement; promotion_weight column
├── hazards.py           # CHANGED — load_cells takes a weight expression, not a predicate
├── compensation.py      # CHANGED — promotion-weighted median replaces WHERE NOT promoted
├── models.py            # CHANGED — PromotionBasis, LevelSeparation, weighted HazardFit
├── runner.py            # CHANGED — orchestration, replaces the upper-bound warning
├── report.py            # CHANGED — promotion basis section, per-level verdicts, method
├── pack.py              # CHANGED — manifest carries basis + non-default thresholds
├── apply.py             # CHANGED — provenance_block carries promotion basis
└── priors.py            # CHANGED — expose promotion_compensation.base_increase_pct

planalign_cli/commands/
└── fit.py               # CHANGED — two threshold flags, validation, summary line

tests/
├── test_parameter_fitting.py   # CHANGED — TestRoundTrip extended; new test classes
├── test_promotion_mixture.py   # NEW — EM unit tests, separation test, determinism
└── fixtures/
    └── synthetic_census.py     # CHANGED — raise dispersion (see research.md R-7)
```

**Structure Decision**: Single project. All work lands in the existing `planalign_fit` package plus its CLI command and test module. No new package, no new layer, no dbt or database changes — this feature never touches `dbt/` or any `.duckdb` file, so the isolated-database rule in `CLAUDE.md` §8 does not apply and the shared dev DB is never opened.

## Phase 0 — Research

Complete. See [research.md](./research.md). Decisions resolved:

| # | Question | Decision |
|---|---|---|
| R-1 | Which estimator (issue #511 offered four) | Two-component Gaussian mixture on `log(1+g)` per level, EM. Folds option (2)'s joint identification into option (1). |
| R-2 | How to avoid the circularity | The mixture identifies the ordinary and promotion components in one pass; merit is read off the *fitted* ordinary component's responsibilities, not off a prior classification. |
| R-3 | Separation test (fixed per FR-016) | Two-part: BIC must prefer two components over one, **and** standardized separation `abs(mu2 - mu1) / sigma_pooled >= 2.0`. Both constants module-level, non-configurable. |
| R-4 | Determinism | Prior-anchored deterministic initialization; no RNG; `max_iter=200`, `tol=1e-8`. Component identity fixed by construction, so no label switching. |
| R-5 | Degenerate inputs (pay freezes, cuts, top level) | Excluded from the mixture's continuous support, assigned weight 0, retained in exposure. |
| R-6 | numpy vs. pure Python | numpy — already a declared dependency (`pyproject.toml:20`). |
| R-7 | **Grading harness is currently degenerate** | `synthetic_census.py:144` gives every non-promoted survivor exactly `merit+cola` and every promoted one exactly `promotion_raise` — zero variance. Two point masses make the mixture test trivial and can divide by zero. The fixture must gain raise dispersion before it can grade anything. |

## Phase 1 — Design & Contracts

Complete. Artifacts: [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md).

### Design in brief

**One quantity, two consumers.** The whole design turns on `promotion_weight` — per transition, P(promotion | observed raise). On the authoritative path it is the observed 0/1 flag; on the estimated path it is an EM posterior. Everything downstream reads it:

```text
transitions ──> promotion_weight ──┬──> SUM(w) per age x tenure x level cell ──> IPF ──> promotion hazard
                                   └──> weighted median of g, weight (1 - w) ──> merit by level
```

This is why FR-008a can insist there is *one* merit definition rather than a per-path variant: on the authoritative path the weights collapse to today's `WHERE NOT promoted` behavior exactly, so the clean path is unchanged by construction (SC-005, US3 scenario 3).

**Generalizing the existing solver costs almost nothing.** `hazards.load_cells` already aggregates `SUM(CASE WHEN <predicate> THEN 1 ELSE 0)` into a `float` events field, and `ipf.FactorCell.events` is already a float. Swapping the predicate for a weight expression is a one-line change that both paths share; the IPF solver needs no modification at all to accept fractional events.

**Routing precedes estimation.** `has_explicit_level` (`transitions.py:202`) becomes a coverage measurement rather than a column-presence check. This is also a bug fix: today line 202 checks the whole column while line 141 coalesces per row, so a census with one populated `level_id` claims to be directly measured and silently band-derives the rest.

**Three states, one enum.** `PromotionBasis` in {`measured`, `estimated`, `not_fitted`} is threaded through `FitResult`, the report, the manifest, and the `param_pack` provenance block, satisfying FR-005 and FR-010 with a single value rather than a set of inferred conditions.

### Agent context

No new technology to record — numpy, DuckDB, and pytest are already listed for this repo, and this feature introduces no new stack element. `update-agent-context.sh` is therefore a no-op for the technology section.

## Phase 2 — Task planning approach

*Not executed by `/speckit.plan`. `/speckit.tasks` will generate `tasks.md`.*

Expected shape: ~18 tasks in five dependency-ordered groups, test-first within each.

1. **Foundations** — fixture dispersion (R-7) and its own assertions; `PromotionBasis`/`LevelSeparation` types. Everything else depends on a harness that can actually grade.
2. **Estimator** — `mixture.py` EM with unit tests on synthetic arrays (known mu, sigma, pi), separation-test tests, determinism test. Pure numerics, independently testable, no fitter integration.
3. **Routing and weights** — coverage measurement in `transitions.py`, `promotion.py` orchestration, the silent-mixing bug fix and its regression test.
4. **Consumers** — weighted `load_cells`, weighted merit median, `runner.py` wiring, removal of the upper-bound warning. Clean-path parity tests gate this group.
5. **Surfaces** — report sections, manifest and provenance, CLI flags and validation, `TestRoundTrip` extensions, docs (`docs/guides/parameter_fitting.md`).

User-story mapping: groups 1–4 deliver User Story 1 (P1) and User Story 2 (P1); group 4 delivers User Story 3 (P2); User Story 4 (P3) is one independent task against the anonymizer plus a report-wording assertion, and can ship in any order.

## Risks

| Risk | Mitigation |
|---|---|
| EM fails to separate on a real client census whose raise practice is messier than the model assumes | This is the designed outcome, not a failure — FR-004 routes it to per-level not-fitted with the default retained. The risk is *frequency*, not correctness; the report surfaces it either way. |
| Prior-anchored initialization biases the result toward the prior when the client's true merit is far from the configured value | Explicit test: run the round trip with a truth merit well away from the seeded prior and assert recovery. If EM cannot escape the prior, the initialization is wrong, not the tolerance. |
| Gaussian on `log(1+g)` mis-describes a real raise distribution (multi-modal comp structures, off-cycle bands) | The existing `MIN/MAX_PLAUSIBLE_GROWTH` filter (`compensation.py:30`) already trims the extreme tails. Beyond that, the separation test is the guard: a distribution the model describes badly will not clear BIC and will resolve to not-fitted. |
| Fixture dispersion values are themselves an assumption about client behavior | The fixture grades the estimator, not the world. Choose dispersion that makes the test *harder* than the degenerate current state, and add the deliberately-overlapping negative case (US2) so both outcomes are exercised. |
| Tolerances in SC-001/SC-002 prove unreachable | Flagged in the spec's Assumptions as unmeasured. Group 2 produces real numbers early; if ±1.5pp is not achievable the spec's success criteria get revised with evidence, before the surfaces are built on top. |
