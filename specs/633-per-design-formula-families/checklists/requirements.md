# Specification Quality Checklist: Per-Design Contribution Formula Families

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-02
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

## Validation Notes

Checked each item against the drafted spec. Points worth recording:

1. **Requirements phrased as outcomes, not mechanism.** The `UNION ALL`-over-referenced-families
   restructuring named in issue #633 is an implementation approach; FR-002 and FR-008 state the
   observable outcome instead ("computes each employee's match using the family of their design",
   "excludes unreferenced families from the executed computation"). The approach belongs in plan.md.
2. **Every success criterion carries a number.** SC-005 bounds the single-design performance
   envelope at 5% rather than saying "no measurable slowdown"; SC-002 names a minimum hand-verified
   sample per design rather than leaving "hand-verified per employee" open-ended.
3. **Background retains named models and branch counts.** These are the measured blast radius from
   issue #633 and are the reason the feature exists. They sit in Background as context and do not
   appear in Requirements or Success Criteria.

## Notes

- The requirements are complete enough to plan, but the live GitHub issue still needs to be
  synchronized with the confirmed match-and-core scope before implementation begins.
- The plan already exists; this checklist no longer treats the spec as waiting for `/speckit.plan`.

## Re-validation after the 2026-09-02 scope decision

The spec is intentionally scoped to match **and** core because sponsors may grandfather either
contribution type independently. Re-checked every box above; all still hold subject to tracker
synchronization. Additional notes:

5. **Core is intentional business scope.** A grandfathered cohort may retain a historical
   non-elective core formula independently of its match formula. The original survey simply missed
   `int_employer_core_contributions`.
6. **FR-015 through FR-017 are prerequisite work, not scope creep.** They close the
   `DBT_VAR_DEFERRED` boundary #632 left open by design. They are in the spec because per-design core
   family selection is not meaningful without them, and stating that dependency is what keeps the
   feature honest about its size.
7. **FR-018 is resolved, not deferred.** Permitted disparity travels with the assigned design when
   core formulas are grandfathered, so it is a plain requirement with no placeholder.
8. **Two requirements are no longer symmetric between the sides, deliberately.** FR-005/FR-006 read
   as one rule but discharge differently: match fails by losing or duplicating a row, core by silently
   substituting a fallback rate. The spec states the outcome; research.md D7/D8 carry the mechanism.
9. **One risk remains open and is recorded in plan.md rather than here.** The combined change is
   large for a single review. The plan marks a clean split at the phase-2 boundary so the match half
   can ship first if review load demands it; the spec supports either shipping shape.
10. **Spec corrected after Phase 0 (2026-09-02).** Phase 0 found that core fails differently from
    match — a silent fallback rate rather than a lost row. The spec had described both sides in
    match's vocabulary ("zero-arm", "multi-arm"), which would have produced acceptance tests that
    could not detect the core failure at all. Story 3, the edge cases, FR-005, FR-006, SC-003, and the
    Key Entities entry were restated in outcome language covering both shapes, and FR-019 was added
    for the design-blind deduplication key found at the same time.
11. **Default-path posture corrected (2026-09-02).** Grandfathering is expected in only 1% to 2% of
    client projects. Product Posture, Story 2, FR-020/FR-021, SC-009, and Assumptions now make the
    ordinary single-design workflow the dominant path while retaining complete match/core behavior
    for the uncommon projects that require it.
12. **Post-analysis remediation completed.** Canonical parity now names its sole timestamp exclusion;
    SC-006 is scoped to behavioral validation; formula-resolution diagnostics require correlation and
    remediation context; audit metadata has a concrete compatibility contract; and the constitution's
    100k capacity, full-fast-suite, and checked-in-fixture gates are reflected in the plan and tasks.
