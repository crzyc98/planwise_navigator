# Phase 1 Data Model: Tenure-Graded Multi-Tier Employer Match Formula

## Entities

### TenureBandMatchTier

A single cumulative deferral-rate step within a tenure band's match schedule. Maps the spec's "Match Tier" entity.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `employee_min` | float | `>= 0`, `<= 1` | Lower bound of deferral % covered by this tier (inclusive). Decimal form (0.02 = 2%). |
| `employee_max` | float | `> employee_min`, `<= 1` | Upper bound of deferral % covered by this tier (exclusive). |
| `match_rate` | float | `>= 0`, `<= 2.0` | Match rate applied to the portion of deferral falling in `[employee_min, employee_max)`. Decimal form (1.00 = 100%). |

**Validation**: Within a single band, the list of `TenureBandMatchTier` MUST start at `employee_min = 0` and be contiguous (no gaps, no overlaps) — enforced via `validate_tier_contiguity()` with `min_key="employee_min"`, `max_key="employee_max"`.

### TenureGradedMatchBand

A tenure range and its associated ordered tier schedule. Maps the spec's "Tenure Band" entity.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `min_years` | int | `>= 0` | Lower bound of years-of-service covered (inclusive). |
| `max_years` | `Optional[int]` | `None` or `> min_years` | Upper bound (exclusive); `None` = unbounded (10+ years case). |
| `tiers` | `List[TenureBandMatchTier]` | non-empty | The band's own independent, ordered, cumulative tier schedule. |

**Validation**:
- `tiers` must be non-empty and internally contiguous starting at 0% (see above).
- Across all bands in a `TenureGradedMatchBand` list, `min_years`/`max_years` must be contiguous starting at 0 and non-overlapping — enforced via the existing `validate_tier_contiguity()` with `min_key="min_years"`, `max_key="max_years"`.
- No upper limit on the number of bands or tiers per band (clarified: no fixed cap).

### TenureGradedMatchFormula (conceptual, not a literal class)

The overall plan design — represented in code simply as `EmployerMatchSettings.tenure_graded_bands: List[TenureGradedMatchBand]`, selected via `employer_match_status = 'tenure_graded'`. No separate wrapper class needed; mirrors how `tenure_match_tiers`/`points_match_tiers` are modeled today as plain list fields on `EmployerMatchSettings`.

## Relationships

```
EmployerMatchSettings
└── tenure_graded_bands: List[TenureGradedMatchBand]   (replaces tenure_match_tiers)
        └── tiers: List[TenureBandMatchTier]
```

- One `EmployerMatchSettings` has zero-or-many `TenureGradedMatchBand` (populated only when `employer_match_status == 'tenure_graded'`).
- One `TenureGradedMatchBand` has one-or-many `TenureBandMatchTier` (always at least one — a single-tier band is the one-element case, satisfying FR-003a backward compatibility).
- An employee is matched against exactly one `TenureGradedMatchBand` per simulation year, determined by `FLOOR(years_of_service)` falling in `[min_years, max_years)`.
- Within that band, an employee's deferral rate is matched against every `TenureBandMatchTier` in that band cumulatively (sum of per-tier matched amounts).

## State / Lifecycle Notes

- No multi-step lifecycle — this is a point-in-time configuration evaluated fresh each simulation year against that year's `years_of_service` and `deferral_rate` (consistent with how `tenure_based`/`points_based`/`graded_by_service` modes already work; no new temporal-state-accumulator pattern needed).
- Mid-year tenure-boundary crossing (Edge Case) is resolved the same way the existing `tenure_based`/`graded_by_service` modes resolve it today: `years_of_service` is computed once per simulation year from the workforce snapshot (`FLOOR(snap.current_tenure)`), so the employee's band for that year is fixed at evaluation time — no new design needed, this is existing, already-tested behavior being extended to a new mode.

## Derived/Computed Values

- **Effective max match % per band** (used in the User Story 2 config-review summary): `SUM(tier.match_rate * (tier.employee_max - tier.employee_min) for tier in band.tiers)`. E.g., under-10-years band: `1.00 * 0.02 + 0.50 * 0.06 = 0.05` (5%).
- **Match amount per employee per year**: `SUM(CASE WHEN deferral_rate > tier.employee_min THEN LEAST(deferral_rate - tier.employee_min, tier.employee_max - tier.employee_min) * tier.match_rate * LEAST(eligible_compensation, irs_401a17_limit) ELSE 0 END for tier in employee's band.tiers)` — identical cumulative-tier formula already used by `deferral_based` mode, scoped to the employee's tenure band.
