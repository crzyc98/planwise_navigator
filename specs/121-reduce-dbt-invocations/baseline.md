# Feature 121 — Run-Cost Baseline & Per-Tier Evidence

**Status**: scaffold. Code-level work (Tier A + foundational gates) is complete; the
heavy 60k-census measurement campaigns are **deferred to the maintainer** (per the
implementation-session decision "code + tests, defer heavy runs"). Fill the tables
below by running `specs/121-reduce-dbt-invocations/quickstart.md`.

## Baseline reframing (established, not to be re-measured)

The invocation baseline is **38 dbt commands** for a five-year (2025–2029), 60,040-employee
run — the authoritative figure from feature 120
(`specs/120-unify-orchestrator-construction/work-schedule-baseline.md`). The retained
**"62" is retired**: it counted log/subprocess records with different semantics, not
issued dbt commands. See `research.md` Decision 1.

## Isolated-DB guardrail

- Shared dev DB `dbt/simulation.duckdb` SHA-256 at implementation start:
  `46ef47d6c8b46142d2cb0863d19ba8ba19e2bd6c3fcab2e846cbaacc4bfa5683`
- Re-check after the whole campaign; MUST be byte-identical (SC-008).

## MEASURED (2026-07-21) — reference config, 7,505-employee census, 5-year, isolated DBs

Baseline = HEAD with Tier A+B **stashed**; candidate = Tier A+B applied. Same config, census,
seed, horizon. Single cold run each (see wall-time caveat below).

| Metric | Baseline | Candidate (A+B) | Result |
|---|---:|---:|---|
| **invocation_count** | **38** | **30** | −8 (−21%); ≤32 ✅ |
| **all-mart parity** | — | — | `fct_yearly_events`, `fct_workforce_snapshot`, `fct_employer_match_events` all **0/0** (byte-identical) ✅ |
| **peak RSS** | 584,417,280 B (557.3 MiB) | 584,105,984 B (557.0 MiB) | −0.05%; ≤ +10% ✅ |
| **wall time** (cold, single) | 116.95 s | 106.18 s | −10.77 s (**−9.2%**) — directional only |

- The 3 marts above are the only `fct_*`/`dim_*` marts the `simulate` workflow builds; the other 6
  discovered marts (`fct_compensation_growth`, `fct_policy_optimization`, `fct_payroll_ledger`,
  `dim_payroll_calendar`, `dim_hazard_table`, `fct_workforce_snapshot_gate_c`) are **absent in both**
  DBs (calibration/optional/gate models, not part of the product path) → no behavioral difference.
- Row counts identical: `fct_yearly_events` 94,900 = 94,900; `fct_workforce_snapshot` 43,903 = 43,903;
  `fct_employer_match_events` 33,645 = 33,645.

**Wall-time caveat:** the −9.2% is a **single cold run on a 7,505-employee census**, NOT the
authoritative gate. The ≥20% gate (FR-017) is defined on the **median-of-three warm** wall time at
the **60,040-employee** Studio scale. This directional number is below 20% — consistent with
feature 120's finding that the remaining run cost is mostly model execution, not invocation overhead.
To get the authoritative gate number, run the 60k warm campaign (`scripts.perf_profile.run_matrix`,
`quickstart.md` steps 2–3). Because the invocation saving is fixed (~8 launches), its wall-time share
shrinks as census/computation grows, so the 60k warm figure will likely be ≤ this 9%.

## Invocation count per schedule state (projection)

| Schedule state | invocation_count | Notes |
|---|---:|---|
| HEAD baseline | **38 (measured)** | confirms feature-120 baseline; "62" retired |
| after Tier A+B | **30 (measured)** | −8; already ≤ the issue's 32 ceiling |
| ~~after Tier C~~ | ~~20~~ | **REJECTED** — corrupts multi-year events at 60k scale (see Tier C NO-GO below) |

## Warm wall time / peak RSS (median-of-three, both configs)

| State | Config | warm median (s) | peak RSS (MiB) | Δ wall vs baseline |
|---|---|---:|---:|---:|
| baseline | reference | | | — |
| baseline | studio | | | — |
| after A | reference | | | |
| after A | studio | | | |
| after B | reference | | | |
| after B | studio | | | |
| after C | reference | | | |
| after C | studio | | | |

RSS gate: each state ≤ baseline × 1.10.

## AUTHORITATIVE (2026-07-21) — 60,040-employee Studio config, median-of-three WARM

Baseline = HEAD (A+B stashed); candidate = A+B. Studio scenario config, 60,040-row census,
5-year, isolated DBs, `scripts.perf_profile.run_matrix --reps 3` (1 cold + 3 warm each).

| Metric | Baseline | Candidate (A+B) | Result |
|---|---:|---:|---|
| **invocation_count** | **38** | **30** | −8 (−21%); ≤32 ✅ |
| **warm wall (median-of-3)** | **132.02 s** | **119.55 s** | **−9.4%** |
| warm reps | 131.88 / 132.02 / 132.82 | 117.58 / 119.55 / 123.57 | |
| **peak RSS (median)** | 1250 MiB | 1265 MiB | +1.2%; ≤ +10% ✅ |
| **all-mart parity (60k)** | — | — | `fct_yearly_events`, `fct_workforce_snapshot`, `fct_employer_match_events` all **0/0 byte-identical** ✅ |

Warm ≈ cold (132 vs 130s baseline) → the run is compute-bound; per-invocation overhead is a small
minority, exactly as feature 120 predicted. The 9.4% here matches the 9.2% cold small-census estimate.

## Ship decision record

- Warm improvement (Studio 60k): **9.4%**  (cold 7.5k reference: 9.2%)
- Gate (≥20%) met? **NO** (9.4% < 20%)
- Correctness / RSS / count gates: **all PASS** (byte-identical at 7.5k AND 60k; RSS +1.2%; 38→30)
- Decision: **`maintainer_ship`** (2026-07-21) — maintainer accepted the 9.4% warm improvement as a proven-safe, memory-neutral, zero-correctness-risk pure win (byte-identical at 7.5k and 60k; 38→30 invocations). The 20% target was aspirational; there is no downside to shipping A+B.
- Tier C (further ~5-invocation collapse) left for a follow-up if a larger wall-time win is later wanted; not required for A+B to ship.
- Evidence: `var/perf_profile/f121-baseline-60k/`, `var/perf_profile/f121-candidate-60k/`; shared dev DB SHA unchanged (`46ef47d6…`)

## Tier C gate finding (T026 — recorded during implementation)

`dbt/models/intermediate/int_workforce_snapshot_optimized.sql` is
`materialized='incremental'`, `incremental_strategy='delete+insert'`,
`on_schema_change='sync_all_columns'`. Its per-year `--full-refresh` is forced by
`year_executor._model_needs_full_refresh` with reason **"schema compatibility"** — i.e.
the model's schema can change across builds in a way delete+insert can't absorb
incrementally. Collapsing the STATE_ACCUMULATION 3-way split therefore requires either
(a) making this model cleanly incremental (removing the full-refresh need) or (b) proving
a reorder keeps a single full-refresh boundary — **both need the multi-year all-mart
parity run to validate** and are gated (T028).

### Tier C — ATTEMPTED and REJECTED (2026-07-21, NO-GO)

Approach (a) was implemented: drop `int_workforce_snapshot_optimized` from
`_model_needs_full_refresh` (its `is_incremental()` predicate is the tautology
`WHERE {{ simulation_year }} = {{ simulation_year }}`, so it *looked* redundant),
collapsing STATE_ACCUMULATION 3→1 (invocations 30→**20**).

**7.5k census: parity 0/0, looked safe.** **60k Studio census: FAILED on all three gates** —
the classic scale-dependent trap (§8 of CLAUDE.md):

| Metric | A+B (baseline) | A+B+C | Result |
|---|---:|---:|---|
| invocation_count | 30 | 20 | −10 |
| warm wall (median-of-3) | 119.55 s | 181.81 s | **+52% SLOWER** ❌ |
| peak RSS | 1265 MiB | 1474 MiB | **+18%** (over ceiling) ❌ |
| fct_yearly_events rows | **645,130** (known-good) | 617,382 | **−27,748 events — WRONG** ❌ |
| fct_employer_match_events | 260,784 | 234,807 | −25,977 ❌ |
| fct_workforce_snapshot parity | — | 50,315 rows differ | **content mismatch** ❌ |

**Root cause:** the `--full-refresh` is **load-bearing, not redundant.** Without it,
`int_workforce_snapshot_optimized` (incremental `delete+insert`) *accumulates prior-year
rows* instead of being wiped to the current year. Downstream multi-year state/event logic
reads the bloated table, changing generated events at scale (and bloating compute + RSS).
The 7.5k census didn't exercise the pathological multi-year pattern, giving a false pass.

**Decision: Tier C reverted; NOT shipped.** Final feature = **A+B (38→30, byte-identical,
−9.4% warm, memory-neutral)**. The gate (T028) worked exactly as designed — the multi-scale
isolated-DB validation caught a correctness regression that a single-scale check missed.
