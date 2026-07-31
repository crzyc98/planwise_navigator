# Phase 0 Research: Social Security Integrated Employer Core Contribution

**Feature**: `126-ss-integrated-core` | **Date**: 2026-07-30

All decisions below were resolved against the repository; no NEEDS CLARIFICATION remains. Findings that contradict the source issue are marked **⚠ correction**.

---

## R1 — How to guarantee byte-identical output when integration is disabled

**Decision**: When `integration.enabled` is false, the Jinja template emits **exactly today's amount expression, character for character**. The disparity term is not emitted as `+ 0`, and the amount is not restructured into `base + disparity`. The five audit columns are emitted as typed constants (`NULL` for the level, `0` for excess and disparity, the base amount echoing the total, the wage base as read).

When integration is enabled, the amount becomes `ROUND(base_amt, 2) + ROUND(disparity_amt, 2)`, and the two audit components are those same two rounded expressions — so FR-018 (components sum to total) holds by construction rather than by luck.

**Rationale**: FR-007 sets byte-identical as the acceptance bar. Today's expression is a single `ROUND(LEAST(comp, cap) * rate, 2)`. Any restructuring — even one that is algebraically equivalent — changes where rounding happens and can move a cent on some rows. Textual identity is the only form of this guarantee that cannot be argued with, and it costs one `{% if %}`.

The corollary is that enabling integration changes the rounding structure (two rounded terms instead of one). That is correct and intended: the split is the deliverable, and a plan document states the two pieces separately, so each is rounded as administered.

**Alternatives considered**:
- *Always emit `base + disparity`, with disparity constant-zero when disabled* — simpler template, but `ROUND(x,2) + ROUND(0,2)` vs `ROUND(x,2)` is only *probably* identical, and the requirement says byte-identical. Rejected.
- *Round once on the total when enabled* — makes FR-018 an approximate equality requiring a tolerance in tests. Rejected; the whole point of the split is that it reconciles exactly.

---

## R2 — Where the §401(l) legality check runs, and how it reaches the wage base

**Decision**: In Python, at config load, in `planalign_orchestrator/config/workforce.py`, invoked from the existing `@model_validator(mode="after")` on `SimulationConfig` (`config/loader.py:71-81`). The wage base is read from the **seed CSV** `dbt/seeds/config_irs_limits.csv` with the standard library, never from DuckDB.

The wage base is needed for less than the whole check:

| Level mode | Wage base needed to derive the factor? |
|---|---|
| `ss_wage_base` | No — the level *is* the wage base, so the ratio is 1.0 and the factor is 5.7% |
| `percent_of_ss_wage_base` | Only for the `$10,000` floor clause; the configured percentage is itself the ratio |
| `fixed_dollar` | Yes — the ratio is level ÷ wage base, which moves year to year |

**Rationale**: FR-012 requires the failure *before any simulation work begins*, and Assumption 8 promises the check is testable without a database. Reading a checked-in CSV satisfies both: it is a file read of ~12 rows, it works before any database exists, and it keeps these tests in the `pytest -m fast` suite where Constitution Principle III wants them.

This also means the check cannot be a dbt test or a SQL assertion — by the time dbt runs, simulation work has begun and the run has already cost minutes.

**Alternatives considered**:
- *Query `config_irs_limits` in DuckDB* — the table may not exist yet on a cold start (that is precisely what `drop_seed_tables_with_schema_mismatch` and `_ensure_seed_current` exist to repair), so validation would be unreliable exactly when it matters. Rejected.
- *Hardcode the wage base in Python* — creates a second source of truth that will drift from the seed. Rejected.
- *Validate in SQL and fail the model* — violates "before any simulation work" and produces a dbt stack trace instead of a named limit. Rejected.

---

## R3 — Which year the legality check is evaluated against

**Decision**: Every year in `[start_year, end_year]`. The validator iterates the simulated range, resolves the integration level and wage base for each year, derives that year's factor, and reports the **first** violating year, naming the year in the message.

**Rationale**: Under `fixed_dollar`, the ratio of level to wage base changes every year because the wage base changes. A fixed $150,000 level might sit above 80% of the wage base in an early year (5.4% factor) and drop into the 4.3% band later, so a disparity rate of 5% is legal in one year of the same run and illegal in another. Checking only the first year would let an illegal later year through silently — the exact failure FR-015 forbids.

Under `ss_wage_base` mode the factor is 5.7% in every year, so the loop is trivially satisfied; the cost of the loop is a dozen iterations of arithmetic.

**Alternatives considered**:
- *Check the first simulation year only* — cheap, and wrong for `fixed_dollar` in any multi-year run, which is the normal case. Rejected.
- *Check the most restrictive year only* — equivalent in outcome but requires deriving which year is most restrictive, which is the same loop with worse error messages. Rejected.

---

## R4 — ⚠ Correction: `_ensure_seed_current`'s fixed-tuple check is sound

**Decision**: Add `social_security_wage_base` to the `required_columns` tuple in `planalign_api/services/ndt_service.py:258-261`. No structural change is needed.

**Finding**: The issue asks to "confirm `_ensure_seed_current`'s `required_columns` check still behaves — it currently asserts an exact count match against a fixed tuple." Reading the code, the count is compared to `len(required_columns)`, not to a hardcoded number:

```python
required_columns = ("hce_compensation_threshold", "super_catch_up_limit", "annual_additions_limit")
# ... SELECT COUNT(*) ... WHERE column_name IN (?, ?, ?)
if column_count == len(required_columns):
    return  # already up to date
```

The `IN (?, ?, ?)` placeholder list is generated from the same tuple. Adding a member widens both sides together, so the check continues to behave. The concern in the issue does not reproduce.

**Consequence for the plan**: this is a one-line change, not a refactor. The generic orchestrator path needs nothing at all — `DataCleanupManager.drop_seed_tables_with_schema_mismatch` (`planalign_orchestrator/pipeline/data_cleanup.py:479`) globs `dbt/seeds/*.csv` and compares live table schemas against CSV headers, so it detects the new column automatically for every database. FR-004 is therefore satisfied by existing machinery on the orchestrator path and by one tuple entry on the NDT path.

---

## R5 — ⚠ Correction: the two seed type declarations already disagree

**Decision**: Add `social_security_wage_base: integer` to both `dbt/seeds/schema.yml` and `dbt/dbt_project.yml`, as the issue asks — but treat this as convention, not as a correctness requirement, and do not attempt to reconcile the pre-existing divergence.

**Finding**: The issue states the column type "must be declared in **both** places … or DuckDB CSV sniffing will disagree with the declared schema." The current state contradicts the premise that both lists are complete:

- `config_irs_limits.csv` has **11** columns.
- `dbt/seeds/schema.yml` types **10** of them (omits `annual_additions_limit`).
- `dbt/dbt_project.yml` types **5** of them (`limit_year`, `base_limit`, `catch_up_limit`, `catch_up_age_threshold`, `compensation_limit`).

Six columns — including `hce_compensation_threshold` and `annual_additions_limit`, both of which are actively used — are typed in only one place or neither, and the seed loads correctly today. Sniffing an unambiguous integer column is not a real hazard here.

**Rationale for following the instruction anyway**: declaring it in both places is free, matches what a reader of either file would expect, and removes any argument about the new column specifically. Reconciling the other six is unrelated cleanup and is listed as out of scope in `plan.md`.

---

## R6 — ⚠ Data smell: the 2026 seed row is marked published but duplicates 2025

**Decision**: Source the 2026 wage base from the SSA announcement and set `is_estimated` for that row according to what the announcement supports. Do **not** infer the 2026 wage base by copying the 2025 value the way the neighbouring columns in that row do.

**Finding**: In `config_irs_limits.csv`, the 2026 row carries `is_estimated=false` while every one of its limit values is byte-identical to 2025:

```
2025,23500,31000,50,350000,160000,34750,60,63,false,70000
2026,23500,31000,50,350000,160000,34750,60,63,false,70000
2027,24000,31500,50,355000,165000,35250,60,63,true,71000
```

A row flagged as published but carrying the prior year's figures is either a placeholder that was never updated or a mislabelled estimate. Either way it is not a pattern to imitate, and a 2026 wage base copied from 2025 in the same spirit would be wrong and would be *labelled* as published.

**Scope note**: correcting the other 2026 values is a separate data fix, out of scope here (recorded in `plan.md`). This research entry exists so the implementer does not read the neighbouring cells as precedent.

**Projection convention for 2027+** (FR-003): the estimated rows use a flat per-year dollar step per column (`base_limit` +500, `compensation_limit` +5,000, `hce_compensation_threshold` +5,000). The wage base follows the same *form* — a constant annual dollar increment, chosen to approximate the historical growth of the taxable wage base — and the rows keep `is_estimated=true`. The specific increment is set at implementation from the verified published anchor, not from a figure in this document.

---

## R7 — Rounding of a derived integration level

**Decision**: For `percent_of_ss_wage_base`, the integration level is the wage base times the percentage, **rounded half-up to whole dollars**. The identical rule is applied in the Python validator and in the SQL, and it is stated once in `data-model.md` so the two cannot drift.

**Rationale**: Plan documents express integration levels in whole dollars, and administration follows the document. Leaving the product unrounded would make the `integration_level_applied` audit column display cents that appear in no plan document, and would make boundary tests (an employee earning "exactly the integration level") depend on floating-point equality at the cent level.

Half-up rather than banker's rounding matches the `ROUND` semantics already used for money throughout the model.

**Alternatives considered**:
- *No rounding* — simplest, but produces audit values that cannot be reconciled to a document and makes the FR-013 boundary tests fragile. Rejected.
- *Round in SQL only* — Python validation would compute a slightly different ratio near a factor boundary, so a configuration could pass validation and then be administered at a different level. Rejected as a drift hazard.

---

## R8 — Which base rate the "lesser of" test uses when the rate varies

**Decision**: Validation compares the disparity rate against the **minimum rate in the resolved schedule** — the flat rate for `flat`, and the lowest tier rate for `graded_by_service`, `points_based`, and `age_banded`. Recorded in the spec as Assumption 6 / FR-016.

**Rationale**: §401(l) constrains each employee's allocation, and the disparity rate is a single plan-wide rate (Assumption 5). If any employee's base rate is below the disparity rate, that employee's allocation is illegal. Validating against the schedule minimum is the only static check that guarantees no employee is in violation, and it is checkable at config load, which is where FR-012 requires the failure.

The cost is that a schedule whose lowest band is 1% cannot carry a 3% disparity even if only the 1% band's members are below the wage base and therefore receive no disparity at all. That is a conservative refusal of a configuration that *might* be legal for a particular census. Refusing it is consistent with FR-015's stance that a wrong-but-plausible number is the worst outcome, and the user can express the intended design by raising the floor band.

**Alternatives considered**:
- *Per-employee runtime enforcement in SQL* — exact, but moves the failure into the run, contradicting FR-012, and yields a dbt error rather than a named limit. Rejected.
- *Validate against the maximum tier rate* — would permit configurations that are illegal for employees in the lower bands. Rejected outright; it inverts the safety property.
- *Validate against the population-weighted rate* — requires the census at config-validation time and makes legality depend on who happens to be employed. Rejected.
