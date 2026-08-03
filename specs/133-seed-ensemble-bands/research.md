# Phase 0 Research: Seed Ensembles

**Feature**: 133-seed-ensemble-bands | **Date**: 2026-08-03

All spec-level unknowns were resolved in the clarification session. This phase resolved the *technical* unknowns, and one investigation materially changes the shape of User Story 3. That finding is first.

---

## D1 (headline finding): Only three subsystems are actually seed-variant

**Investigation**: enumerated every randomness site reachable by the production pipeline and checked whether the global seed participates in the hash input.

| Subsystem | Sites | Seed in hash? | Varies across seeds? |
|---|---|---|---|
| Termination | `int_termination_events.sql` (3), `int_new_hire_termination_events.sql` (4), `macros/generate_termination_date.sql` (via call-site arg) | Yes | **Yes** |
| Hiring | `int_hiring_events.sql` (2 — new-hire age, part-time) | Yes | **Yes** |
| Promotion | `int_promotion_events.sql` (1) | Yes | **Yes** |
| Enrollment / opt-out | `int_enrollment_events.sql` (3), `int_voluntary_enrollment_decision.sql` (2), `int_proactive_voluntary_enrollment.sql` (3), `int_deferral_match_response_events.sql` (2) | **No — all 10 sites** | **No** (see below) |
| Merit | `int_merit_events.sql` | No HASH/RANDOM at all | **No** |

**Evidence for enrollment.** Every enrollment hash keys on employee and year only:

```sql
-- int_enrollment_events.sql:168
(ABS(HASH(aw.employee_id || '-enroll-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0 as enrollment_random
```

The seed is absent from the hash input, so the draw for a given employee in a given year is **identical across every seed**. Enrollment outcomes do still differ between seeds, but only because the *population* differs (who was terminated or hired varies) — never because the enrollment draw itself varied.

**Evidence for merit.** `int_merit_events.sql` contains zero `HASH(` or `RANDOM(` calls. Merit is a deterministic formula over band, COLA, and merit rate. There is no draw to freeze.

**Consequences, stated plainly:**

1. **Merit cannot be attributed.** There is no merit randomness. The spec already hedges this (FR-018 says "SHOULD ... where the subsystem's randomness is separable"), so dropping merit from v1 is within scope as written. Reporting merit at 0% would be *correct* but misleading — it reads as "merit doesn't matter" when the truth is "merit is not modeled stochastically."

2. **Enrollment attribution as specified would be vacuous.** Freezing an already-frozen draw is a no-op; the measured variance reduction would be ~0 for reasons that have nothing to do with enrollment's importance. This collides with the issue's exit criterion ("attribution for at least termination/hiring/enrollment").

3. **Making enrollment seed-variant is a behavior change, not an addition.** Adding the seed to those 10 hashes changes which employees enroll in every existing scenario, at every seed including the default. Every stored result and every regression baseline shifts. That is a materially different act from the byte-identical refactor the other three subsystems need.

**Decision**: split the two. Ship attribution for **termination, hiring, and promotion** (all genuinely seed-variant, all convertible byte-identically). Treat **enrollment seeding as a separate, explicitly-flagged decision** with its own before/after evidence, sequenced after the attribution machinery is proven on the three working subsystems. Report enrollment and merit in the attribution table as *not stochastic* rather than as 0% — an honest absence beats a misleading zero.

**Alternatives considered**:
- *Silently report enrollment as 0%.* Rejected — indistinguishable from a real measurement of "enrollment doesn't drive spread," which is exactly the wrong conclusion to hand a client.
- *Seed enrollment as part of this feature.* Rejected as bundled scope: it invalidates existing baselines and deserves its own reviewable change with its own evidence, not to ride along inside an ensembles feature.
- *Substitute promotion for enrollment and call the criterion met.* Partially adopted — promotion genuinely is seed-variant and is worth attributing — but the enrollment gap is reported, not papered over.

---

## D2: Subsystem freezing via per-subsystem seed variables

**Decision**: introduce a macro `subsystem_seed(name)` resolving to `var('random_seed_<name>', var('random_seed', 42))`, and replace the inline `var('random_seed', 42)` at each production draw site with `subsystem_seed('<subsystem>')`.

**Rationale**: freezing a subsystem means holding *its* seed constant while the global seed varies. Because the fallback chain ends at the same `var('random_seed', 42)`, the rendered SQL string is character-identical when no override is passed — so default behavior is provably unchanged, and that provability is what makes the refactor safe to land ahead of the attribution logic.

**Scope**: 10 call sites across 4 production models plus one macro call-site argument (D1 table, first three rows).

**Explicitly excluded**: `macros/utils/generate_event_uuid.sql` (4 sites). UUID generation must stay bound to the global seed — freezing a subsystem should not renumber other subsystems' event identifiers.

**Also excluded**: `macros/utils/rand_uniform.sql` (`hash_rng`, `hash_shard`) and the `models/debug/` tree. `hash_rng` is referenced only by three debug models and is not on the production path; converting it would be churn with no effect on results.

**Verification gate**: compile and run the full pipeline before and after with no overrides; `fct_yearly_events` and `fct_workforce_snapshot` must match exactly. This gate must pass before any attribution code is written.

**Alternatives considered**:
- *Route everything through the existing `hash_rng` macro first.* Rejected for v1 — it is a larger refactor of production SQL whose only benefit here is aesthetic, and it changes hash inputs (different concatenation format), so it cannot be done byte-identically.
- *A separate frozen-draws lookup table joined per subsystem.* Rejected — heavier, and it changes model DAGs rather than just a scalar in a hash.

---

## D3: Ensemble execution reuses `ScenarioRunPool` unchanged

**Decision**: build `ScenarioJob` instances (one per seed) and submit them to the existing pool. No new concurrency mechanism.

**Rationale**: `ScenarioJob` already carries exactly what a seed run needs — `name`, `config`, `db_path`, `seed`, `threads`, `dbt_artifacts_dir`, and a free-form `payload`. The pool already provides bounded workers sized on memory (`resolve_worker_count`, ~1296 MiB/worker), `setsid`-based group termination on Ctrl+C (FR-007), dbt artifact isolation per worker, and inline execution at `max_workers == 1` for a pickle-free serial path. FR-002/003/006/007 are satisfied by adoption rather than construction.

**Constraint inherited**: the worker function must be module-level (jobs cross the process boundary by pickle).

**Precedent**: `planalign_backtest/simulate.py` already runs per-seed isolated simulations (`configure_seed`, `run_seed`) via `ConstructionSpec`/`build_orchestrator`, writing `seed_<n>.duckdb` per seed. The ensemble runner follows that structure and adds the pool for concurrency.

---

## D4: Aggregate by extraction, not by attaching databases

**Decision**: query each per-seed database in turn for its per-year metric row, collect the results in memory, compute percentiles in Python, and write the aggregate to the dedicated ensemble database.

**Rationale**: the data is tiny — 6 metrics × 5 years × 25 seeds is 750 values — so the aggregation is memory-trivial and needs no SQL gymnastics. Reading each seed database with its own short-lived read-only connection honors the constitution's connection rules and keeps FR-011a (per-seed databases are read-only inputs, never mutated) structurally true rather than merely intended.

**Alternatives considered**:
- *`ATTACH` all N seed databases and aggregate in one query.* Rejected — 25 attached DuckDB files to compute 750 numbers, and attaching read-write by accident is precisely the FR-011a violation we want made impossible.
- *A dbt model computing the distributions.* Rejected — a dbt model cannot span N sibling databases, and the aggregate is not part of any per-seed DAG.

---

## D5: Percentiles via NumPy linear interpolation

**Decision**: `numpy.percentile(values, q)` with default `method="linear"`, over seed values sorted by seed id.

**Rationale**: matches FR-010 exactly (linear interpolation between bracketing order statistics) and matches what an analyst spot-checking in a spreadsheet or pandas will compute. NumPy ≥1.24 is already a declared dependency. Fixing the input order by seed id makes the floating-point result bit-stable across runs, which is what SC-002's byte-identical requirement needs.

---

## D6: Metric extraction reuses existing definitions

**Decision**: source all six headline metrics from `fct_workforce_snapshot`, reusing the aggregate expressions already used by `excel_exporter._calculate_summary_metrics`.

**Grounding** (columns confirmed present):

| Metric | Source |
|---|---|
| Active headcount | count of active rows |
| Total compensation | `SUM(prorated_annual_compensation)` |
| Employer match cost | `SUM(employer_match_amount)` |
| Total employer plan cost | `SUM(total_employer_contributions)` — match + core, per FR-009a |
| Participation rate | share by `participation_status` |
| Average deferral rate | `AVG(current_deferral_rate)` |

`total_employer_contributions` already exists as a materialized column, so FR-009a is satisfied by reuse — no new cost definition is invented (per the spec's inherited-definitions assumption).

**Absent metrics** (FR-016, edge case): the extractor probes for column presence the way the exporter already does, and reports a metric as absent rather than substituting zero.

---

## D7: Provenance via the existing `run_metadata` mechanism

**Decision**: record ensemble provenance in the ensemble database using `run_metadata`, extended with ensemble columns through the established `_evolve_provenance_schema` additive pattern.

**Key reuse**: `compute_config_fingerprint()` already canonicalizes `to_dbt_vars(config)` **with `random_seed` removed**. That is exactly the predicate FR-019b needs — "same configuration, different seed" — so the baseline-reuse guard is a fingerprint equality check against an existing helper rather than new comparison logic.

---

## D8: CLI surface

**Decision**: add `--seeds N`, `--seed-list`, `--attribution`, and `--discard-seed-dbs` to `planalign simulate`, and the equivalent to `planalign batch`.

**Implementation note**: `planalign_cli/commands/simulate.py` defines the options **twice** — once on the `run` subcommand and once on the hidden `default` command that backs the bare `planalign simulate 2025-2029` form. Both must receive the new options or the documented invocation silently ignores them. Extracting the shared option set is preferable to duplicating it a third time.

---

## D9: Excel export

**Decision**: extend `planalign_orchestrator/excel_exporter.py` with a distribution sheet and an attribution sheet, following the existing `_write_*_sheets` + `_format_worksheet` pattern, added only when an ensemble aggregate exists (FR-025).

---

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Do per-subsystem RNG streams exist? | No. D1/D2 — three subsystems convertible byte-identically; two are not stochastic at all. |
| Can enrollment be attributed? | Not without a behavior change. D1 — deferred to its own decision, reported as not-stochastic meanwhile. |
| Concurrency mechanism | D3 — existing `ScenarioRunPool`, unchanged. |
| Cross-database aggregation | D4 — extract per seed, aggregate in Python. |
| Percentile convention | D5 — NumPy linear, seed-ordered for bit-stability. |
| Metric definitions | D6 — reuse exporter's existing expressions; `total_employer_contributions` for FR-009a. |
| Config-match guard for reuse | D7 — existing `compute_config_fingerprint` (already seed-independent). |
| CLI wiring | D8 — dual command definition must both be updated. |

**No NEEDS CLARIFICATION markers remain.**
