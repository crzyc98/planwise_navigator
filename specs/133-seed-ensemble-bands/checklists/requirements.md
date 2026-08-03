# Specification Quality Checklist: Seed Ensembles — Distribution Bands, Exceedance Risk, and Variance Attribution

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-03
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

- **Validation iteration 1 findings and fixes:**
  - Initial draft named concrete option flags (`--seeds`, `--attribution-seeds`) in requirements. Replaced with capability language ("request an ensemble of N seeds", FR-001/FR-017) so the spec constrains behavior, not the CLI surface. Flag naming is a planning decision.
  - Initial draft asserted a specific default attribution seed count. Softened to a documented assumption plus a hard disclosure requirement (FR-021), since the right default depends on measured per-run cost from #478.
  - Initial draft left the percentile convention unstated across three output paths — a latent disagreement bug. Added FR-010 requiring one convention applied identically everywhere.

- **Two deliberate deviations from strict technology-agnosticism**, both retained:
  - `fct_metric_distributions` is named in Key Entities because the requesting issue specifies it as a deliverable artifact name.
  - Success criteria reference isolated per-seed databases and worker processes. These are the project's stated correctness invariants (one database per run; no orphaned subprocesses on cancel), not incidental implementation choices, and they are testable as written.

- **Open risk carried into planning, not a spec gap**: the requesting issue assumes per-generator RNG streams already exist; they do not (a single global seed is threaded into hash expressions across many models). See the spec's Concerns section. This is the dominant sizing question for User Story 3 and should be the first thing `/speckit.plan` resolves.

- **Suggested slice order**: US1 → US2 → US4 (export) → US3 (attribution). US3 carries the RNG-plumbing risk and is independently deferrable without devaluing US1/US2.

- **Clarification session 2026-08-03 (5 questions, quota reached)** resolved: employer-cost definition (FR-009a), attribution baseline pairing and reuse (FR-019a/b/c), insufficient-sample handling (FR-013a/b/c), aggregate location (FR-011a/b), percentile convention (FR-010a). All five were Partial/Missing before the session and are now Resolved.

- **One editorial default set without asking** (quota exhausted, low impact, safe default): duplicate seeds in an explicit seed list are **rejected** rather than de-duplicated, on the grounds that a silently shortened seed list breaks the correspondence between requested and actual ensemble size. Flip to de-duplication if that proves annoying in practice.

- **Correction made mid-session, recorded so it does not resurface**: the first recommendation on the attribution baseline argued that reusing the headline ensemble confounds variance reduction with sampling noise because of mismatched sample sizes. That reasoning was wrong — sample variance is unbiased at any N, and a larger baseline sample is strictly more precise. The property that actually matters is *pairing*: frozen and baseline runs must share a seed list so the two runs differ only in the frozen subsystem. Pairing and reuse are compatible, which is why FR-019a requires the attribution seeds to be a subset of the headline seed list.
