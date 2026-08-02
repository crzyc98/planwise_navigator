# Phase 0 Research: Backtest Scorecard

Decisions taken before design, each grounded in what `planalign_fit` (#458) and `planalign_orchestrator` already do. Line references are to the code as of branch `131-backtest-scorecard`.

---

## R1. Where the holdout split happens

**Decision**: Add `only_years: Optional[tuple[int, ...]]` to `FitOptions`, applied inside `fit_parameter_pack` immediately after `load_snapshots` via a new `SnapshotSet.subset(years)`. The backtest never constructs its own snapshot set for fitting.

**Rationale**: `fit_parameter_pack(snapshots_dir)` takes a *directory* and loads everything in it (`planalign_fit/runner.py:78`). Any caller-side split — filtering afterwards, or passing a curated directory — leaves the fitter's contract unchanged and the guarantee unenforceable. Putting the filter inside the fitter has three consequences that matter:

1. There is exactly one place where fitted-vs-held-out is decided, so one test can prove FR-003.
2. `build_pack` receives the already-subset `SnapshotSet`, so the pack manifest's `snapshot_years` and `source_digest` reflect **only** fitted years. A leak would be visible in the pack's own provenance, not just in the scorecard — this is what satisfies Principle IV.
3. `--params` runs of a backtest-produced pack inherit the correct provenance for free.

`subset()` re-runs `_validate_set` on the retained snapshots, so a subset that breaks year-consecutiveness is rejected by the same rule as any other snapshot set.

**Alternatives rejected**:
- *Stage a temp directory of symlinks to fitting-portion files.* Works, but the fitter would report the temp paths as provenance, and hashes would be of the symlink targets — provenance becomes about a scratch directory rather than the analyst's data. Also fragile across the `.csv`/`.parquet` discovery in `_discover_files`.
- *Split after loading, in the backtest.* Requires duplicating `fit_parameter_pack`'s body, which is the classic way two code paths drift.

---

## R2. Where actual values come from

**Decision**: Build a second, scoring-only `TransitionSet` over the **full** snapshot set (fit + holdout) in a separate in-memory DuckDB connection, and read actuals from it. This connection is created in `planalign_backtest/actuals.py` and is never passed to any estimator.

**Rationale**: Terminations, hires, and promotions are not census columns; they are *inferred* from consecutive snapshots. `build_transitions` (`planalign_fit/transitions.py:218`) already infers them, with documented semantics and band assignment, and the fitter uses the same inference to produce the parameters being scored. Using anything else would compare a model fitted on one definition of "termination" against actuals computed under another — an error that measures the definitional gap, not the model.

The `fit_transitions` table gives directly what FR-011 needs: `terminated`, `promoted` per experienced-cohort row, and `fit_new_hires` gives the hire cohort. Headcount, compensation, and plan metrics come from the banded per-snapshot projection.

**Reading held-out data here is not leakage.** The invariant in FR-003 is about what influences *parameters*. Scoring must read the held-out actuals — that is the entire point. The design makes the distinction structural: the fitting connection is opened inside `fit_parameter_pack` with a subset snapshot set (R1); the scoring connection is opened in `actuals.py` and reaches no estimator. Two connections, two purposes, no shared object.

**Alternatives rejected**:
- *Hand-rolled SQL over the held-out snapshots.* Would drift from the fitter's transition semantics the first time either changed.
- *Treat the held-out census as ground truth only for headcount/comp, skipping flows.* Loses the termination/hire/promotion metrics the spec requires (FR-011), which are exactly the ones a skeptical reviewer probes.

---

## R3. Making predicted and actual comparable

**Decision**: Predicted metrics read `fct_workforce_snapshot` from the isolated run database, using its existing `level_id`, `age_band`, `tenure_band`, `employment_status`, `is_enrolled_flag`, and `current_deferral_rate` columns; predicted event counts read `fct_yearly_events`, and match cost reads `fct_employer_match_events`. Actual metrics band via `BandDefinitions` loaded from the same seed CSVs. A dedicated test asserts the two banding paths agree on an identical employee population.

**Rationale**: Both sides already resolve bands from `config_age_bands.csv` / `config_tenure_bands.csv` — the simulation through the `assign_age_band`/`assign_tenure_band` macros, the fitter through `BandDefinitions` (`planalign_fit/bands.py`), which exists precisely to mirror those seeds in Python. Comparability is therefore free *if* the same seed files are used, and a lie if they are not. The test makes the assumption load-bearing rather than hopeful.

Level assignment has a subtlety worth pinning: `_banded_projection` prefers a census `level_id` and falls back to compensation banding (`transitions.py:150`), mirroring `int_baseline_workforce`. When a census supplies no level column, predicted and actual both derive level from compensation, so the by-level headcount comparison stays meaningful — but it is measuring a compensation-derived stratification. The scorecard states which basis was used, reusing the `promotion_basis` idea #511 introduced.

**Alternatives rejected**:
- *Re-band the simulation output in Python.* Duplicates the macro logic in a third place.
- *Compare only totals, skipping breakdowns.* FR-009 requires the breakdowns, and they are where a model most often fails while totals look fine.

---

## R4. Compensation basis

**Decision**: Score the **annualized compensation rate** on both sides. Actual = `employee_gross_compensation` from the census. Predicted = `current_compensation` from `fct_workforce_snapshot`, restricted to employees active at year end. `prorated_annual_compensation` is explicitly **not** used for the headline comparison.

**Rationale**: A census row states an employee's annual salary rate, not what they were paid across a partial year. `prorated_annual_compensation` answers a different question — cash actually earned, reduced for mid-year hires and terminations. Comparing a rate against a prorated amount produces a systematic negative error proportional to hiring volume, which would be misread as the model under-predicting pay.

The active-at-year-end restriction matches the census population: a snapshot of active employees. The scorecard names the basis explicitly (FR-017's spirit), so a reviewer never has to guess which of the two compensation columns a number came from.

**Alternatives rejected**:
- *Prorated on both sides.* Not derivable from a census that carries only a rate.
- *Report both.* Doubles the metric count for a distinction most readers would not act on; the guide documents the difference instead.

---

## R5. Reducing multiple seeds to one headline number

**Decision**: The **lower median** across seeds is the headline predicted value for every metric, per Assumption 4. For odd seed counts (including the default 3) this is the ordinary median; for even counts it is the lower of the two central values. The spread is reported as min–max across seeds.

**Rationale**: The median resists a single unlucky run in a way the mean does not, which is the whole reason to run multiple seeds. Choosing the *lower* median for even counts rather than averaging the two central values keeps count metrics integral (a headcount of 1042.5 is not a headcount) and keeps the result independent of floating-point averaging — supporting the byte-identical rerun requirement (SC-005).

The median is taken **per metric independently**, not by picking one "median seed" and reading all metrics from it. Per-metric is what the spread question actually asks; a single representative seed would be a different, weaker statistic and would leave some metrics' headline values arbitrary.

**Alternatives rejected**:
- *Mean across seeds.* Non-integral counts, and one outlier run moves it.
- *A designated representative seed.* Simpler to explain, but discards the robustness the multi-seed run was paying for.

---

## R6. How the backtest simulation is launched

**Decision**: In-process via `build_orchestrator(ConstructionSpec(...))` with a new `entry_point="backtest"`, one isolated database per seed under `var/backtests/<timestamp>-<pack_id>/seed_<n>.duckdb`, and a per-run `dbt_artifacts_dir`. Seeds run serially.

**Rationale**: `ConstructionSpec` is the single canonical construction seam (Feature 120), and `entry_point` is a closed `Literal` (`planalign_orchestrator/construction/spec.py:40`) that already carries harness values `invariant_test` and `perf_harness`. Adding `backtest` follows that precedent and makes backtest runs identifiable in `run_metadata` without inference. Shelling out to the CLI would lose the typed spec, structured errors, and in-process progress reporting FR-033 needs.

Per-run `dbt_artifacts_dir` is set even though runs are serial: it costs nothing, prevents a concurrent unrelated dbt run from corrupting attribution, and means adopting the #457 pool later is a substitution rather than a redesign.

`var/backtests/` is under the existing git-ignored `var/` tree, so isolated databases never risk being committed and never collide with `dbt/simulation.duckdb` (FR-006).

**Alternatives rejected**:
- *Subprocess `planalign simulate --params`.* Loses typed errors and progress; makes failure attribution (FR-032) a matter of parsing stdout.
- *One shared database across seeds.* Destroys per-seed isolation and makes determinism dependent on execution order.

---

## R7. Setting the starting census and the per-seed random seed

**Decision**: The backtest writes an effective config per seed, derived from `apply_pack`'s effective config, overriding two values: `setup.census_parquet_path` (the last fitted snapshot, converted to parquet in the workdir if the source is CSV) and `simulation.random_seed`.

**Rationale**: `apply_pack` already produces the effective config and overlay dbt project a pack-backed run needs (`planalign_fit/apply.py:92`), including the `param_pack` provenance block. The backtest needs exactly two further overrides, both existing config fields — no new configuration surface.

Census conversion follows the precedent set by the invariants harness (Feature 113), which converts a checked-in CSV census to parquet at session setup. Conversion output lands in the run workdir, leaving the analyst's snapshot directory untouched.

Varying `random_seed` changes the config fingerprint per seed run. This is correct and desirable: `run_metadata` will show distinct fingerprints for distinct seeds, which is what a reviewer auditing a multi-seed backtest should see. Config-drift warnings are not triggered because each seed writes a fresh isolated database.

**Alternatives rejected**:
- *Reuse one config and pass the seed as a dbt var directly.* Bypasses `to_dbt_vars` and would leave `run_metadata`'s recorded seed inconsistent with the seed actually used.

---

## R8. Where the scorecard lives and how staleness is detected

**Decision**: `<pack>/backtest/scorecard.json` and `<pack>/backtest/scorecard.md`. The scorecard records the pack fingerprint it scored. Reading a scorecard re-verifies it against the pack's current fingerprint and marks a mismatch as stale (FR-026).

**Rationale**: `_fingerprint` covers only the config fragment, seed file contents, and source digest (`planalign_fit/pack.py:471`), so a `backtest/` subdirectory is invisible to `verify_pack`. Writing a score therefore cannot change the pack's identity — FR-028 holds structurally, not by convention, and no future edit to the backtest artifacts can accidentally violate it.

Staleness detection is the mirror image: because the scorecard stores the fingerprint it scored, and the pack can recompute its own, a pack edited after backtesting is detectable by comparison. This reuses the existing warning pattern `apply_pack` already applies to edited packs (`apply.py:100`).

**Alternatives rejected**:
- *Store scorecards in a central `var/backtests/` registry.* The score would not travel with the pack, defeating the provenance goal.
- *Add the score to `manifest.json`.* Would change the manifest and invite a future fingerprint definition that covers it — precisely the coupling FR-028 forbids.

---

## R9. Closing the provenance chain to `run_metadata`

**Decision**: Add one nullable `backtest_score_ref` column to `run_metadata`, populated from a `param_pack.backtest` sub-block that `apply_pack` includes in the effective config when the pack carries a scorecard. The value identifies the scorecard (pack id + scorecard fingerprint + overall verdict).

**Rationale**: #458 established exactly this mechanism: the `param_pack` block is an untyped config extra that `to_dbt_vars` ignores, so it reaches `run_metadata` without perturbing the config fingerprint (`planalign_fit/apply.py:70`). Extending that block is additive and needs no new plumbing. `_evolve_provenance_schema` already adds columns idempotently with `ADD COLUMN IF NOT EXISTS` (`planalign_orchestrator/run_metadata.py:376`), so no migration is required and old databases converge on read.

This satisfies FR-027 and SC-006: from a run row, a reviewer reads the pack id and the scorecard reference, opens the scorecard, and reads the source snapshot hashes.

**Alternatives rejected**:
- *Store the full scorecard in `run_metadata`.* Bloats an append-only table with a document that already lives with the pack.
- *Infer the scorecard by convention from the pack path.* Breaks as soon as a pack is moved or copied — the reference must be data, not a naming rule.

---

## Resolved unknowns summary

| # | Question | Resolution |
|---|---|---|
| R1 | Where does the fit/holdout split happen? | Inside the fitter, via `FitOptions.only_years` |
| R2 | Where do actual values come from? | A scoring-only `TransitionSet` over the full snapshot set |
| R3 | How are predicted and actual made comparable? | Shared band seeds, verified by test |
| R4 | Which compensation basis? | Annualized rate on both sides, active at year end |
| R5 | How do multiple seeds reduce to one number? | Per-metric lower median; min–max spread |
| R6 | How is the simulation launched? | `ConstructionSpec` with `entry_point="backtest"`, serial, isolated DBs |
| R7 | How are starting census and seed set? | Effective-config overrides on top of `apply_pack` |
| R8 | Where does the scorecard live? | `<pack>/backtest/`, outside the fingerprint |
| R9 | How does the chain reach `run_metadata`? | Additive nullable column via the `param_pack` block |

No NEEDS CLARIFICATION markers remain.
