# Contract: Timing Data & Report Interface

This feature's external interface is small but real: the JSON sample files are the contract between the measurement scripts and the report builder (SC-006 regeneration depends on it), and the report's table set is the contract with the human decision-maker and with issue #456.

## 1. Sample file contract (`var/perf_profile/samples/*.json`)

- One file per repetition: `{size}-{rep}.json` (e.g. `large-1.json`); probe result as `probe.json`.
- **Repetition semantics**: `--reps N` means N **warm** (headline) repetitions; the harness always prepends one extra cold run per size, saved as `{size}-0.json` with `repetition: 0, warm: false`. Warm files are numbered from 1.
- The campaign-end SC-007 hash verification is written to `campaign.json` (campaign-level summary: before/after SHA-256, sizes run, floor stats); per-sample `EnvNote` carries only the *before* hash, since the after-hash cannot exist until the campaign ends.
- Schema: `TimingSample` / `ProbeResult` exactly as defined in [data-model.md](../data-model.md). Pydantic models in `scripts/perf_profile/profile_config.py` are the single source of truth; `build_report.py` MUST fail loudly on schema mismatch, never coerce silently.
- Samples are append-only within a campaign: re-running a repetition writes a new file with an incremented `rep`; `build_report.py` uses the latest complete set and lists which files it consumed in the report footer.
- `completed=false` samples are excluded from stats but MUST be listed in the report footer (no silent drops).

## 2. Report contract (`docs/perf/run_cost_profile.md`)

While the campaign is incomplete, sections may render as an explicit "NOT YET MEASURED" placeholder and the recommendation as "INSUFFICIENT DATA"; the final committed report must contain none of either. Required sections, in order (User Story 1 acceptance depends on this ordering — criteria before results):

1. **Decision criteria** — FR-007 verbatim.
2. **Environment** — EnvNote fields (FR-010).
3. **Wall-time by census size** — table: size, n (warm reps), min/median/max total wall.
4. **Decomposition** — per size: computation vs overhead vs residue (absolute + % of total); residue ≤ 10% asserted.
5. **Overhead share vs size curve** — the decision-grade table; `large` row highlighted.
6. **Fixed-cost cross-check** — invocations/year, measured floor, product vs M2 overhead, ratio.
7. **Direct-execution probe** — both wall times, speedup, equivalence verdict (+ diffs if any).
8. **Projection** — full-run speedup range + enumerated assumptions (GO) or top-3 hotspots (NO-GO).
9. **Recommendation** — exactly one GO/NO-GO evaluated at `large`; per-scale note if verdicts differ.
10. **Reproduction** — commands to regenerate every table (FR-008) + consumed sample list.

## 3. CLI contract (harness scripts)

```
python -m scripts.perf_profile.make_large_census  --out var/perf_profile/census_large.parquet [--factor 8]
python -m scripts.perf_profile.run_matrix         [--sizes tiny,dev,large] [--reps 3] [--horizon 2025-2027]
python -m scripts.perf_profile.probe_direct_execution [--year 2025]
python -m scripts.perf_profile.build_report       [--samples var/perf_profile/samples] [--out docs/perf/run_cost_profile.md]
```

Guarantees: every script is idempotent-safe to re-run; `run_matrix` refuses to start if the resolved DB path is `dbt/simulation.duckdb`; exit codes nonzero on any guardrail violation (SC-007 hash mismatch, schema mismatch, residue > 10%).

## 4. Downstream consumers

- **Issue #456** consumes sections 5, 7, 8 as its acceptance baseline (spec SC-005).
- **Issue #457** consumes section 3 (absolute per-run cost per size) for pool sizing.
- The roadmap tracking issue #463 checklist item for #455 is closed by linking the merged report.
