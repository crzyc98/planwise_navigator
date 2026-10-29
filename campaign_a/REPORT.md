# Campaign A — blocked by storage capacity

As of 2026-10-29, branch `t3/nh-salary-calibration-campaign` in the existing `t3-e8a89381` worktree. Frozen oracle: `ORACLE.md`; 54 synthetic cells, nine dev and 45 holdout. Each stage requires 63 cell/seed runs (seed 42 for all; seed 101 for dev). No calibration tuning, accepted campaign checkpoint, or stop-rule completion.

Integer-age prerequisite repair **4616f452** is committed. Previously recorded validation: full fast suite **4070 passed** and repository Ruff passed; the final formatting-only repair adjustment had five focused tests pass. These are prior repair checks, not a new full-suite run for this harness change. Whole completed-year age buckets are the prerequisite's domain assumption.

One repaired run is complete: `balanced_h5_c1_low`, seed 42, stage `prerequisite_repair`. Its baseline, calibration/apply, and fresh applied 2026–2030 simulation completed. Lead raw-table scoring exactly agrees with the independent audit:

- Maximum ALL-population compensation error: **2.5057580479438504 pp**.
- Maximum ALL-population headcount error: **1.5847086561131585 pp**.
- Maximum calibration/full-simulation gap: **0.787287098960319 pp**.
- Plausibility failures: **0**; no duplicate employee/year rows.

This cell misses the frozen error/gap thresholds. Zero plausibility failures does not imply acceptance. Primary scoring uses ALL snapshot employees and earned prorated compensation; calibration uses `methodology_a_current` (active continuous/new-hire employees). Active-only results remain secondary diagnostics. Calibration predictions come from the saved **best-candidate outcome**; the calibration database retains the **last evaluation**, whose 2030 methodology-A growth is 2.448557372214904%, and is not the best-candidate prediction source.

Fingerprint discrepancy is explained and verified for both full phases: the harness originally hashed submitted `/tmp/.../census.parquet`; `SimulationService._prepare_simulation` calls `validate_census`, which resolves it to `/private/tmp/...`, before saving config and initializing provenance. Restoring only the source-constructed submitted census path reproduces each original hash exactly. Full configs agree after path resolution; archived config checksums, attested fingerprints, run IDs, DB metadata and frozen census hash agree. Original `config_fingerprint` fields remain intact; explicit `submitted_config_fingerprint` and `attested_config_fingerprint` fields were added. See `fingerprint_reconciliation.json` and rerunnable read-only `reconcile_fingerprints.py`. Future harness runs fail closed on any other config difference or failed attestation.

Counts verified directly from all frozen matrix slots and cell files (`current_status.json`): original `baseline` has **11 failed, 1 interrupted, 51 unrun, 0 completed** runs. At cell level: ten cells have failures, one interrupted, 43 unrun; one failed cell has both seeds recorded. One earlier legacy failed attempt is retained separately outside these 63 slots. The repaired stage has **1 completed, 62 unrun**. All previously committed run records and failed attempts remain unchanged. `baseline_scores.json` is a retained historical partial summary, not the current status authority.

Seed-noise band and numeric campaign scores remain **undefined**: no complete paired dev baseline or full campaign matrix exists. No improvement, infeasibility, acceptance, or checkpoint claim is justified. No campaign stop criterion has been met.

The serial runner defaults to `baseline`. Explicit `--stage prerequisite_repair` selects separate logs under `/tmp/nhcal/matrix_logs/prerequisite_repair/`, skips every existing stage/seed record (including the completed repaired cell), and refuses existing logs or run directories; direct cell execution also refuses existing records. Optional `--limit N` bounds new launches, including failed launches; it does not retry preserved attempts. Baseline log locations stay unchanged. Safe to start the remaining repaired baseline matrix with that explicit stage; it was **not started** by this bounded task.

Current harness verification (no simulations/network/workers): `python3 scripts/dev.py --check`; `python3 scripts/dev.py -- python -m pytest campaign_a/test_run_cell.py campaign_a/test_run_matrix.py campaign_a/test_score.py -q` (**18 passed**); `python3 scripts/dev.py -- ruff check .` (passed). Black/check hooks and whitespace checks are recorded with the evidence commit. Durable audit: `repaired_cell_raw_audit.json`; independent summary: `repaired_cell_audit.json`; lead score: `repaired_cell_lead_score.json`. Historical decimal-age proposal/patch is retained with its historical status labeled. No databases or census files are included.

## Blocked execution checkpoint

Repaired matrix started 2026-10-29T20:08:49Z; stopped after verifying only 5.9 GiB filesystem capacity remained. The completed repaired cell retains 247,738,261 bytes (237 MiB); 62 comparable runs require approximately 14.3 GiB before additional temporary working space. No evidence was deleted. The active balanced_h2_c1_low seed 42 attempt is interrupted, not failed; repaired-stage totals are one completed, one interrupted, 61 unrun. Original baseline failures remain preserved. Runner delegate was cancelled; only the owned matrix process and descendants were terminated. Attached session transfer failed (unknown process ID 8693), so process identity and cell records were checked directly.

Repair and harness commits: 4616f452 and 9a9431a0. No tuning hypotheses have been kept or reverted; no stop criterion has been met. Dev/holdout baseline and final campaign scores and seed noise are undefined (holdout seed 101 N/A). One-cell metrics above are diagnostic only. No analyst default recommendation is validated. Completion requires additional disk capacity on the /tmp filesystem (roughly 15 GiB further retained output plus working margin); then resume preserved unrun slots and explicitly allocate a new attempt for the interrupted cell. No Campaign B, push, or PR.

**CHECKPOINT: awaiting human review** — blocked, original campaign incomplete.
