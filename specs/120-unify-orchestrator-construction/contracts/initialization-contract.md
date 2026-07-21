# Contract: Fresh-Database Initialization

One explicit rule for preparing a fresh/empty database and reporting failure. Replaces the current swallowed-failure hazard (#467).

## Policies

- **`NONE` (default, canonical/production)**: the canonical seam installs no self-healing initializer. The pipeline's own `_ensure_seeds_loaded` + `_run_start_year_setup` prepare a fresh/empty database — exactly how `planalign simulate` initializes fresh DBs today.
- **`SELF_HEALING` (explicit opt-in)**: `AutoInitializer.ensure_initialized()` runs **before** `execute_multi_year_simulation`, outside any error-isolating hook path.

## Failure semantics (MUST)

1. A **critical** initialization failure (any `SELF_HEALING` step failing, or a `NONE`-path fresh-DB setup failure) MUST raise and **abort the run with zero simulation outputs**. It MUST NOT be logged-and-continued.
2. The error MUST carry attributable context (failing step, correlation id) per constitution IV.
3. #467 is eliminated: the init contract MUST NOT depend on `HookManager.execute_hooks`, which catches every hook exception and continues (`pipeline/hooks.py:175-177`). Either invoke initialization explicitly before the run, or mark the init hook `critical` so `execute_hooks` re-raises it — the former is preferred.

## Equivalence (MUST)

- On an **already-initialized** DB, `NONE` and `SELF_HEALING` produce identical authoritative outputs (self-healing is a no-op there).
- On a **fresh** DB under normal conditions, both policies yield a correctly initialized DB and identical outputs to a pre-initialized run of the same config.
- **Batch gate**: an isolated fresh-DB batch run under `NONE` MUST be byte-identical (events + snapshots) to the same run under today's factory `SELF_HEALING`. If not, repair the missing canonical fresh-DB setup step and repeat the gate; batch MUST NOT retain an entry-point-specific initialization policy.

## Acceptance checks

1. Fresh DB + forced critical init failure → run aborts, clear error, no `fct_yearly_events` rows written.
2. Fresh DB, normal → completes; outputs identical to a pre-initialized run.
3. Batch fresh-DB run under `NONE` == factory `SELF_HEALING` outputs (byte-identical) — or explicit opt-in documented.
