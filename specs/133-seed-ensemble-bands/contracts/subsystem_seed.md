# Contract: `subsystem_seed()` macro and per-subsystem dbt vars

**Feature**: 133-seed-ensemble-bands | **Stage 5 of the implementation sequence**

The mechanism that makes variance attribution possible. It ships as a pure refactor with a byte-identical gate, ahead of and independent of any attribution logic.

---

## The macro

```sql
-- dbt/macros/utils/subsystem_seed.sql
{% macro subsystem_seed(subsystem) %}
  {{ var('random_seed_' ~ subsystem, var('random_seed', 42)) }}
{% endmacro %}
```

**Why this is safe.** When no `random_seed_<subsystem>` var is supplied, the macro resolves to the value of `var('random_seed', 42)` — the exact literal the call site produced before. The rendered SQL string is character-identical, so hash inputs are identical, so results are identical. That property is what makes the refactor landable ahead of its consumer.

## Call sites converted

Only production draw sites. 10 total.

| Subsystem | File | Sites |
|---|---|---|
| `termination` | `int_termination_events.sql` | 3 (selection hash L89; `generate_termination_date` seed argument L101, L110) |
| `termination` | `int_new_hire_termination_events.sql` | 4 |
| `hiring` | `int_hiring_events.sql` | 2 (new-hire age, part-time) |
| `promotion` | `int_promotion_events.sql` | 1 |

`generate_termination_date` takes the seed as a parameter, so converting the two call-site arguments covers the macro without editing it.

## Deliberately NOT converted

| Site | Reason |
|---|---|
| `macros/utils/generate_event_uuid.sql` (4) | UUIDs must stay bound to the **global** seed. Freezing one subsystem must not renumber another's event identifiers. |
| `macros/utils/rand_uniform.sql` — `hash_rng`, `hash_shard` | Referenced only by three `models/debug/` models; not on the production path. |
| `models/debug/**` | Not production. |
| All 10 enrollment hash sites | **Currently unseeded** — converting them changes results for every existing scenario. Separate change, separate evidence (research.md D1). |

## Usage

Default — every subsystem follows the global seed, behavior unchanged:

```bash
dbt build --vars "random_seed: 42"
```

Attribution — freeze terminations while everything else varies with the seed:

```bash
dbt build --vars "random_seed: 1043, random_seed_termination: 42"
```

Across an ensemble, `random_seed` varies per seed while `random_seed_termination` stays pinned. Terminations are then identical in every run; all other stochastic subsystems vary normally. Differencing against the paired baseline at the same seed isolates termination's contribution (FR-019).

## Config export

`to_dbt_vars()` emits `random_seed_<subsystem>` **only when a freeze is requested**. Omitting them by default keeps the emitted var set — and therefore `compute_config_fingerprint` — unchanged for ordinary runs, so this refactor does not perturb drift detection or trip config-drift warnings on existing databases.

## Acceptance gate (blocks Stage 6)

1. **Byte-identical**: build an isolated database before and after the refactor at the same seed and config; `fct_yearly_events` and `fct_workforce_snapshot` must match exactly, row for row.
2. **Freeze is effective**: two runs differing only in `random_seed` produce identical termination events when `random_seed_termination` is pinned, and different ones when it is not.
3. **Freeze is contained**: pinning `random_seed_termination` leaves hiring and promotion events varying exactly as in an unfrozen pair at the same seeds (FR-022).
4. **Fingerprint stable**: a default run's `config_fingerprint` is unchanged from before the refactor.

Gates 1 and 4 must pass before the change lands. Gates 2 and 3 are what Stage 6 builds on.
