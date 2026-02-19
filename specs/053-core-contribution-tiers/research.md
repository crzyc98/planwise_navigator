# Research: Core Contribution Tier Validation & Points-Based Mode

**Branch**: `053-core-contribution-tiers` | **Date**: 2026-02-19

## Research Summary

All technical unknowns resolved through codebase analysis. No external research required — this feature extends existing, well-established patterns.

---

## R1: Tier Validation Reusability

**Decision**: Reuse existing `validateMatchTiers()` function as-is for graded-by-service core tiers.

**Rationale**: The function signature `validateMatchTiers(tiers: Array<{min: number; max: number | null}>, label: string)` is fully generic. It accepts any tier array with `min`/`max` fields and a label string for warning messages. The graded-by-service core tiers have `serviceYearsMin`/`serviceYearsMax` fields that can be mapped to `min`/`max` with a simple inline transform (identical to how tenure match tiers are mapped at line 198 of DCPlanSection.tsx).

**Alternatives considered**:
- Creating a separate `validateCoreTiers()` function — rejected because the logic is identical
- Extracting to a shared utility file — unnecessary; function is already at module scope in DCPlanSection.tsx

---

## R2: Points-Based Core Tier Data Model

**Decision**: Create a `PointsCoreTier` interface with fields `minPoints`, `maxPoints`, and `rate` (no `maxDeferralPct`).

**Rationale**: Unlike match tiers where `maxDeferralPct` caps the deferral percentage eligible for matching, core contributions are non-elective (employer pays regardless of employee deferral). There is no deferral cap to configure. The tier only needs: point range and contribution rate.

**Alternatives considered**:
- Reusing `PointsMatchTier` directly — rejected because `maxDeferralPct` field is meaningless for core contributions and would confuse users
- Adding `maxDeferralPct` as optional — rejected for same reason; simpler is better

---

## R3: dbt Macro Strategy

**Decision**: Reuse existing `get_points_based_match_rate` macro for points-based core rate lookup. No new macro needed.

**Rationale**: The `get_points_based_match_rate(points_col, points_schedule, default_rate)` macro generates a CASE expression from tier data with `min_points` and `rate` fields — exactly what points-based core needs. The macro is generic: it takes any SQL expression for points, any schedule list, and any default. The core model can call it with `employer_core_contribution_rate` as the fallback.

**Alternatives considered**:
- Creating `get_points_based_core_rate` macro — rejected because it would be an identical copy of the match rate macro
- Renaming the existing macro to `get_points_based_tier_rate` — unnecessary churn; the macro name is descriptive enough

---

## R4: Config Export Pipeline

**Decision**: Extend `_export_core_contribution_vars()` in `export.py` to handle `points_based` core status and export `employer_core_points_schedule` dbt variable.

**Rationale**: The export function already handles `core_status`, `core_graded_schedule`, and rate conversion (UI percentage → decimal → dbt percentage). Adding points-based follows the identical pattern used for `points_match_tiers` export in `_export_employer_match_vars()`. The transformation is: `{minPoints, maxPoints, rate}` (UI) → `{min_points, max_points, contribution_rate}` (API) → `{min_points, max_points, rate}` (dbt, rate as percentage for macro).

**Alternatives considered**:
- Passing points schedule through the `employer_core_contribution` nested dict — rejected because the flat dbt vars pattern (`employer_core_points_schedule`) is consistent with `employer_core_graded_schedule`

---

## R5: Points Calculation in Core Model

**Decision**: Use `FLOOR(COALESCE(snap.age_as_of_december_31, 0))::INT + FLOOR(COALESCE(snap.current_tenure, 0))::INT` as the points expression in `int_employer_core_contributions.sql`.

**Rationale**: This matches the formula used in `int_employee_match_calculations.sql` (line 228). The model already has access to `age_as_of_december_31` and `current_tenure`/`years_of_service` from the snapshot join. COALESCE handles null values per edge case requirements.

**Alternatives considered**:
- Using a derived `applied_points` column in a CTE — possible but adds complexity for a single CASE expression; inline is cleaner
