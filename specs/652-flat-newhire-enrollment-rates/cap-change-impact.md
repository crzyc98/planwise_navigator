# Measured Impact: Raising the Voluntary Deferral Cap 10% → 15%

**Feature**: 652-flat-newhire-enrollment-rates | **Decision**: D7 | **Task**: T058/T059
**Measured**: 2026-09-04, isolated 2026–2030 run, seed 42, both new-hire rates unset, spread disabled

## Why this is recorded separately

The cap raise moves results **on its own**, independently of the deferral spread it enables. Bundling the two would let the spread take the blame for a shift it did not cause. This run isolates the cap: everything else is at baseline settings.

## Result

| Metric | Value |
|---|---|
| Employee-years compared | 43,903 |
| Employee-years changed | **295 (0.67%)** |
| Average deferral rate before | 7.340% |
| Average deferral rate after | 7.354% |
| Change | **+0.014 pp** |

### Every affected employee, by movement

| Before | After | Employee-years | Demographic cell |
|---|---|---|---|
| 10% | 12% | 282 | mature/executive and senior/high (table value 0.12) |
| 10% | 15% | 13 | senior/executive (table value 0.15) |

No other movement occurred. This matches the pre-implementation analysis exactly: three table cells are written above the old 10% cap and were being clamped down to it.

## What this does not include

The spread's own effect on average deferral rates is larger and is measured separately. This document covers only the un-clamping.

## Implementation note worth carrying forward

The cap's effective default does **not** live in `dbt/dbt_project.yml`. `_export_match_magnet` in `planalign_orchestrator/config/export.py` writes `voluntary_max_deferral_rate` unconditionally from `MatchMagnetSettings.max_deferral_rate`, so the dbt-side default is dead on any orchestrator run. Changing only `dbt_project.yml` produced **zero** measured change; the Pydantic default had to be raised as well. Both were updated for consistency, but the Python value is the one that takes effect.

## Changelog wording

> The maximum voluntary deferral rate now defaults to 15%, raised from 10%. Three demographic cells (mature/executive, senior/high, senior/executive) carry table values above 10% and were previously clamped down; they now apply as written. Measured effect on an unchanged 2026–2030 scenario: 295 of 43,903 employee-years (0.67%) move, raising the average deferral rate by 0.014 percentage points. This applies whether or not the deferral spread is enabled.

---

# Measured Impact: The Deferral Spread (separate change)

**Measured**: isolated 2026–2030 run, seed 42, `deferral_spread_max_lift: 4`, compared against the **cap-adjusted** baseline so the two changes stay attributable.

| Metric | Value |
|---|---|
| Employee-years changed | 7,910 (18.0%) |
| Average deferral rate before | 7.354% |
| Average deferral rate after | 7.659% |
| Change | **+0.305 pp** |

Only 18% of employee-years move because the spread applies to demographically-assigned rates; census employees carry their own rates from the input file and are untouched by design.

Illustrative cell — mid-career / moderate income, 2026, table value 6%:

| | 6% | 7% | 8% | 9% | 10% |
|---|---|---|---|---|---|
| Before | 421 | – | – | – | – |
| After | 164 | 109 | 74 | 50 | 24 |

That is 39 / 26 / 18 / 12 / 6 percent against the configured 40 / 30 / 15 / 10 / 5 weights.
