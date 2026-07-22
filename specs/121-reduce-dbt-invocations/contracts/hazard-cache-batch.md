# Contract: Batched Hazard-Cache Rebuild (Tier A)

**Feature**: 121-reduce-dbt-invocations
**Seam**: `planalign_orchestrator/hazard_cache_manager.py :: HazardCacheManager.rebuild_hazard_caches`

## Current behavior (baseline — 6 invocations)

```
1. run   --select int_effective_parameters                   --full-refresh   (vars: hazard_params_hash)
2. build --select dim_promotion_hazards                       --full-refresh
3. build --select dim_termination_hazards                     --full-refresh
4. build --select dim_merit_hazards                           --full-refresh
5. build --select dim_enrollment_hazards                      --full-refresh
6. build --select hazard_cache_metadata                       --full-refresh
```

Called once per run via `_ensure_hazard_caches_current` when the parameter hash is stale (fresh isolated DB → year 1 rebuild; later years skip on unchanged hash).

## Target behavior (Tier A — 1–2 invocations)

**Preferred (keeps `int_effective_parameters` test semantics exactly — 6 → 2):**

```
1. run   --select int_effective_parameters                   --full-refresh   (vars: hazard_params_hash)
2. build --select dim_promotion_hazards dim_termination_hazards \
                  dim_merit_hazards dim_enrollment_hazards \
                  hazard_cache_metadata                       --full-refresh   (vars: hazard_params_hash)
```

**Only if proven test-clean (6 → 1):** one combined `build` selection including `int_effective_parameters`. Rejected by default because the existing code intentionally uses `run` for `int_effective_parameters` to avoid executing its schema tests during the hazard rebuild; folding it into a `build` runs those tests.

## Invariants the batched form MUST preserve

| Invariant | Requirement |
|---|---|
| **DAG ordering** | `int_effective_parameters` builds before the `dim_*_hazards` that `ref()` it; `hazard_cache_metadata` builds after the caches. Within the batched `build`, dbt resolves this from ref(); verify with `dbt ls --select +hazard_cache_metadata`. |
| **Full-refresh semantics** | Every cache model is still `--full-refresh` (the batched invocation applies `--full-refresh` to all of them — correct, since all four + metadata want it). |
| **Vars** | `hazard_params_hash` is passed to the batched invocation exactly as today. |
| **Idempotency / currency** | Rebuild still runs only when the hash is stale; later-year skip behavior unchanged. |
| **Failure attribution** | On failure, the error still names the failing cache model (via `_build_rebuild_error` + `extract_dbt_failure_detail` reading `run_results.json`); a batched failure identifies *which* `dim_*_hazards` node failed. |
| **Output parity** | The four `dim_*_hazards` tables + `hazard_cache_metadata` are byte-identical to the pre-batch rebuild (covered by the all-mart parity gate for the `dim_*` marts). |

## Test obligations (before shipping Tier A)

- Unit: assert `rebuild_hazard_caches` issues the batched selection (2 `execute_command` calls, not 6) and passes `--full-refresh` + `hazard_params_hash`.
- Integration (isolated DB): the four `dim_*_hazards` tables and `hazard_cache_metadata` match a baseline rebuild row-for-row.
- Failure injection: a deliberately broken `dim_merit_hazards` still yields an error naming `dim_merit_hazards`.
