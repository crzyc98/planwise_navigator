# Specification Quality Checklist: Trustworthy Promotion Rate from a Census Without Job Levels

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-01
**Last validated**: 2026-08-01 (post-clarification)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

### Specify-phase validation

- Initial draft named the specific candidate approach (two-component mixture) in FR-003, which is an implementation choice. Reworded to state the required *outcome* — separation of promotion-sized raises from ordinary-raise behavior without circular dependence on the merit estimate — leaving the estimator choice to `/speckit.plan`. Issue #511's four candidate approaches are deliberately not encoded in the spec.
- **Deliberate design call carried into the spec** (issue #511 asked for this call explicitly): a caveated upper bound is treated as *not* useful to an analyst. FR-004 and User Story 2 require an explicit "not fitted, default retained" outcome instead. FR-012 removes the current upper-bound warning.

### Clarify-phase resolutions (5 questions, session 2026-08-01)

All five answers are recorded in the spec's Clarifications section and integrated into requirements:

1. **Hazard shape on the estimated path** → per-level rate, then per-transition promotion weights feeding the existing age/tenure solver. Pack shape identical on both paths. (FR-003a, FR-003b)
2. **Merit pool definition** → one promotion-weighted median on every path; probable promotions down-weighted, not excluded. Generalizes today's ex-promotions behavior rather than branching. (FR-008, FR-008a, FR-008b)
3. **Separation verdict granularity** → per job level, with an overall exposure-coverage gate at half. (FR-004, FR-004a, FR-004b)
4. **Partially populated job-level column** → route by coverage, not presence; default 95% threshold. Closes a silent-mixing bug in the current implementation, where a whole-column presence check coexists with a per-row coalesce to band derivation. (FR-001 through FR-001d)
5. **Threshold adjustability** → the two coverage thresholds are analyst-adjustable; the separation test is fixed. Non-defaults recorded in report and provenance. (FR-015, FR-016, FR-017)

Post-clarification consistency pass: renumbered US2 scenarios (1a/1b would not render as an ordered list), and qualified two scenarios that said "explicit job-level column" where the coverage rule now makes "sufficiently populated" the correct term.

### Remaining, deliberately deferred to planning

- **Tolerance figures** in SC-001/SC-002 (±1.5pp, ±1pp) are proposed against the existing termination tolerance (±0.015) rather than measured. Flagged in Assumptions; confirm once the estimator is chosen.
- **Threshold defaults** (95% job-level coverage, half of exposure) are defensible starting points, not measured optima. Mitigated by FR-015 adjustability.
- **The estimator itself** — issue #511's options (1) mixture and (2) joint identification both remain open. This is the central plan-phase decision.
