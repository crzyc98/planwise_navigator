# Contract: All-Marts Parity Gate at 60k

**Feature**: 132-collapse-dbt-invocations

**Inherited from** `specs/121-reduce-dbt-invocations/contracts/correctness-parity.md`. That contract's comparison method is adopted unchanged; this document records only what 132 adds or tightens.

## Inherited unchanged

- **Scope**: every `fct_*` and `dim_*` mart. **Enumerated, never hardcoded**:
  ```bash
  cd dbt && dbt ls --select marts --resource-type model --output name
  ```
  `int_*` and staging are out of scope — their materialization may legitimately differ while marts stay identical.
- **Method**: for each mart, both directions must return 0 rows, using `EXCEPT ALL` so duplicate multiplicities count as differences.
- **Coverage as a pass condition**: the compared set must equal the full enumerated set. A silently skipped mart fails the gate.
- **Determinism**: two candidate runs at the same seed and config must themselves compare 0/0.
- **Exclusions**: `created_at`, `snapshot_created_at`, and the per-run provenance tables (`run_metadata`, `run_execution_metadata`).

## Added by this feature

1. **Scale is mandatory, not a parameter** (`FR-008`). The gate runs at **60,040 employees**. Feature 121's Tier C passed at 7,505 and broke at 60,040; a 7.5k result is explicitly **not evidence** and must not be reported as a pass.
2. **`cache_built_at` is added to the exclusion list.** Step 1b changes when hazard caches are built relative to other work; that timestamp is non-deterministic by construction.
3. **Horizon is five years** (`FR-008`), not a single year — cross-year state accumulation is where regrouping damage would surface.
4. **Self-baselined A/B** (`FR-010`). Baseline and candidate are the same revision and configuration, one before the change and one after. The gate does **not** compare against a historical recorded baseline, which removes any dependency on that baseline being current.
5. **Shared census** (research Finding 6). All four runs of a gate use the *same generated census file*, not merely the same generation parameters.
6. **Local execution with committed evidence** (`FR-013`). The gate does not run in CI. Its full output — per-mart counts both directions, the enumerated mart set, the exclusion list applied, and the determinism result — is committed under `specs/132-collapse-dbt-invocations/evidence/` so a reviewer inspects the evidence rather than trusting a claim.

## Runs required per gate

| Run | Purpose |
|---|---|
| baseline | pre-change, isolated DB |
| candidate | post-change, isolated DB |
| candidate′ | same seed and config as candidate — the determinism pair |

Three simulation runs minimum; a fourth if the baseline's own determinism is in question. At ~103s each plus build and census generation, this is why the gate is local rather than per-PR CI.

## Pass criteria

| Check | Requirement |
|---|---|
| Per-mart parity | 0 / 0 for **every** mart. One non-zero fails the step. |
| Coverage | Compared set equals the enumerated mart set. |
| Determinism | candidate vs candidate′ is 0 / 0. |
| Scale | 60,040 employees. |
| Horizon | Full five-year run. |
| Evidence | Output committed under `evidence/`. |

## On failure

`FR-012`: the step is **abandoned or reverted**. It is not adjusted until it passes at a smaller scale or against a narrower mart set. Tier C's history is the reason this is stated as a rule rather than left to judgment.
