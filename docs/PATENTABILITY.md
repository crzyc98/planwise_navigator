# Patentability Screening: Fidelity PlanAlign Engine

*Updated: August 1, 2026*

## Purpose and limitations

This document is an engineering invention-screening memo. It identifies technical
mechanisms that may justify review by patent counsel; it is not a legal opinion,
patentability determination, freedom-to-operate analysis, or recommendation to
file personally.

Patentability depends on the claims ultimately drafted, the complete prior-art
record, inventorship, ownership, and disclosure history. Because this repository
describes PlanAlign as a Fidelity platform, any employment or contractor
invention-assignment obligations must be resolved before filing.

## Executive summary

Two mechanisms merit counsel review. Neither should presently be described as a
broad or low-risk software patent.

| Rank | Candidate | Key implementation | Preliminary potential | Recommendation |
| --- | --- | --- | --- | --- |
| 1 | Joint promotion/merit estimator with evidence-gated fallback | `planalign_fit/promotion.py`, `planalign_fit/mixture.py`, `planalign_fit/compensation.py` | Medium | Prepare an invention disclosure; search before merging further details |
| 2 | Exact integer workforce solver | `dbt/models/intermediate/int_workforce_needs.sql` | Medium-Low | Resolve the first-public-disclosure date immediately; consider a time-sensitive provisional review |
| 3 | Historical-census parameter pack and provenance chain | `planalign_fit/`, `planalign_fit/pack.py`, `planalign_fit/apply.py` | Low-Medium | Use as supporting claim material for Candidate 1, not a standalone filing |
| 4 | Event-sourced temporal state projections and exactly-once publication | `planalign_orchestrator/pipeline/enrollment_projection.py`, `planalign_orchestrator/workforce_state_projection.py` | Low | Retain as architecture and know-how; do not prioritize for filing |

The February 2026 version of this memo ranked configuration-drift checkpoint
recovery second. Feature 070 subsequently removed that subsystem as unused. It
is no longer an active product candidate and should not drive a filing decision.

## Patentability framework

The preliminary screen considers four practical questions:

1. **Utility and enablement**: Is the mechanism implemented and described well
   enough for a skilled engineer to make and use it?
2. **Novelty**: Does one earlier reference disclose every material element?
3. **Nonobviousness**: Would the differences from known systems have been an
   obvious combination of established techniques?
4. **Subject-matter eligibility**: Is the claim directed to a concrete technical
   implementation or improvement rather than merely mathematics, data analysis,
   or a business rule performed on a generic computer?

USPTO references:

- [Patent essentials](https://www.uspto.gov/patents/basics/essentials)
- [Subject-matter eligibility guidance](https://www.uspto.gov/patents/laws/examination-policy/subject-matter-eligibility)
- [Provisional-application and disclosure guidance](https://www.uspto.gov/patents/basics/apply/provisional-application)

## Candidate 1: Joint promotion/merit estimator

### Problem solved

When historical census snapshots do not contain a reliable job-level field,
PlanAlign derives level from compensation bands. An ordinary merit increase can
then cross a band boundary and be misclassified as a promotion. The error is
structural: using a merit estimate to classify promotions is circular when merit
is itself estimated from the population classified as not promoted.

The synthetic recovery harness observed the practical consequence: a true 6%
promotion rate was materially overstated, and the error worsened as additional
history was supplied.

### Potentially inventive combination

The candidate is not "use a Gaussian mixture model." Its stronger formulation is
the complete evidence-routing and dual-use weighting method:

1. Measure job-level observability over linked employee transitions, requiring a
   level at both ends of a transition.
2. When coverage meets a threshold, measure promotions directly from observed
   upward level moves and exclude transitions that cannot support that inference.
3. When coverage is insufficient, fit a deterministic two-component mixture to
   per-level `log(1 + compensation_growth)` values, with fixed initialization and
   component identity.
4. Require both model-improvement evidence and standardized component separation
   before accepting a per-level estimate.
5. Require the accepted levels to cover a minimum share of experienced exposure
   before publishing an overall fitted promotion hazard.
6. Use each transition's posterior promotion probability in two complementary
   calculations:
   - sum the probabilities as expected promotion events for age- and
     tenure-adjusted hazard fitting; and
   - invert the probabilities as ordinary-raise weights for the merit median.
7. When evidence is insufficient, retain configured defaults and record an
   explicit `not_fitted` disposition rather than publishing a forced estimate.
8. Record the classification basis, thresholds, and fitted/defaulted status in a
   content-fingerprinted parameter pack and downstream run provenance.

### Technical effects

- Breaks the circular dependency between promotion classification and merit
  estimation.
- Produces one coherent weighting signal for both hazard and compensation fits.
- Prevents statistically inseparable populations from generating confident but
  unsupported promotion hazards.
- Preserves deterministic, content-addressable parameter packs without random EM
  restarts or component-label switching.
- Degrades safely when the available census cannot identify promotions.

### Novelty and obviousness risks

The individual building blocks are established: expectation-maximization,
two-component mixtures, Bayesian information criteria, standardized-separation
tests, weighted medians, empirical hazards, credibility shrinkage, and provenance
hashes. Research has also long associated promotions with comparatively large
wage increases, providing a motivation an examiner could use when combining
references.

The possible novelty therefore lies in the specific end-to-end arrangement,
especially the coverage-based routing, evidence-gated refusal to fit, and reuse of
one posterior probability as both promotion-event mass and inverse merit weight.
Claims directed only to statistical classification of employees would face a
substantial abstract-idea risk; a stronger disclosure should document the
concrete parameter-pack generation, deterministic execution, downstream
simulation behavior, and measured recovery improvement.

Relevant background:

- [A Theory of Wage and Promotion Dynamics in Internal Labor Markets](https://www.nber.org/papers/w6454)
- Public issue [#511](https://github.com/crzyc98/planwise_navigator/issues/511)

### Disclosure timing

Issue #511 publicly described the compensation-growth mixture, joint
identification, and fallback concept on July 29, 2026. If that was an
inventor-originated public disclosure, counsel should treat July 29, 2027 as the
apparent outer U.S. grace-period date while independently verifying the facts.
Pre-filing disclosure may already have impaired rights in countries without an
equivalent grace period.

### Recommended invention-disclosure focus

An internal disclosure should capture:

- the band-crossing failure mode and why sequential estimation is circular;
- the three routing outcomes: measured, estimated, and not fitted;
- the dual use of posterior responsibility in hazard and merit calculations;
- the separation and population-coverage gates;
- deterministic component identity and pack reproducibility;
- synthetic recovery results for separable and inseparable populations; and
- alternative embodiments, including other component distributions, robust
  location estimators, and workforce-event types with the same identification
  problem.

## Candidate 2: Exact integer workforce solver

### Problem solved

Given a starting workforce, target growth rate, and different attrition rates for
experienced employees and new hires, the solver computes integer hires and
terminations while guaranteeing exact reconciliation to the target ending
headcount.

### Implemented method

```text
target_ending = ROUND(starting_workforce * (1 + growth_rate))
experienced_terms = FLOOR(experienced * experienced_rate
                          + prior_new_hires * new_hire_rate)
survivors = starting_workforce - experienced_terms
net_hires = target_ending - survivors
gross_hires = CEILING(net_hires / (1 - new_hire_rate))
new_hire_terms = gross_hires - net_hires
```

The final quantity is a residual rather than an independently rounded estimate:

```text
starting_workforce + gross_hires - experienced_terms - new_hire_terms
    = target_ending
```

The production implementation also contains feasibility guards and a separate
reduction-in-force branch when the net-hire requirement is non-positive.

### Technical effects

- Produces exact integer reconciliation without iteration or a general-purpose
  optimization solver.
- Incorporates different attrition behavior for experienced and newly hired
  cohorts.
- Preserves the target headcount across multi-year state accumulation.
- Detects infeasible or operationally extreme inputs before event generation.

### Novelty and eligibility risks

The particular ordered rounding and cohort decomposition may be absent from one
earlier reference, but residual balancing is mathematically straightforward once
exact reconciliation is required. Workforce systems have long calculated future
headcount from hiring and attrition, and staffing literature contains numerous
integer-rounding and optimization approaches.

This candidate also has meaningful subject-matter-eligibility risk because its
core can be characterized as algebra and workforce planning on a generic
computer. Any filing should emphasize the database-integrated event-generation
pipeline, feasibility enforcement, multi-year accumulator correctness, and a
demonstrated reduction in computational work compared with iterative integer
optimization—not merely the balance equation.

Relevant prior art for a professional search includes:

- [US7478051B2, Method and apparatus for long-range planning](https://patents.google.com/patent/US7478051B2/en)
- [US8386300B2, Strategic workforce planning model](https://patents.google.com/patent/US8386300B2/en)
- [EP2342631A1, Supply and demand consolidation in employee resources planning](https://patents.google.com/patent/EP2342631A1/en)

### Disclosure timing

Git history dates the solver implementation to October 9, 2025. The repository is
currently public, but the commit date alone does not prove when that implementation
first became publicly accessible. Counsel should determine the first public push,
public use, offer for sale, demonstration, or other disclosure. If October 9,
2025 was the first inventor-originated public disclosure, the apparent U.S.
grace-period deadline is approximately October 9, 2026.

This is the most time-sensitive candidate.

## Candidate 3: Historical-census parameter pack and provenance chain

### Mechanism

`planalign fit` links employees across annual census snapshots, classifies
transitions, estimates hazard and behavioral parameters, applies thin-cell
shrinkage, and emits the same seed CSV and YAML shapes consumed by the simulator.
The pack records source hashes, effective content, fitted and unfittable
parameters, and a fingerprint later stamped into run metadata.

### Assessment

This is valuable supporting material because it closes the loop from historical
evidence to a reproducible simulation. As a standalone patent candidate, however,
it combines familiar calibration, artifact packaging, hashing, and provenance
techniques. Reproducible modeling systems already fingerprint data, code,
configuration, and parameters; see
[US10802822B2](https://patents.google.com/patent/US10802822B2/en).

Recommendation: describe it as the concrete production context and downstream
effect of Candidate 1 rather than pursue broad claims to a "parameter pack."

## Candidate 4: Temporal state projections and exactly-once publication

### Mechanism

PlanAlign reconstructs decision-year inputs from immutable facts and prior-year
domain accumulators. Disposable projections expose strictly earlier state to
current-year event candidates, while canonical accumulators retain authoritative
workforce, enrollment, and deferral state. Fresh run-specific databases and
atomic latest-success selection prevent partial or failed attempts from replacing
trusted results.

### Assessment

The implementation is careful and operationally important, but event replay,
aggregate projections, idempotent publication, prior-state snapshots, and atomic
result promotion are mature techniques. Relevant references include:

- [US11216444B2, Scalable event sourcing datastore](https://patents.google.com/patent/US11216444B2/en)
- [US11275726B1, Distributed data processing with provenance and reproducibility](https://patents.google.com/patent/US11275726B1/en)

The workforce-specific boundaries may be distinctive implementation know-how,
but the current record does not justify a standalone filing. Preserve it through
copyright, architecture documentation, controlled disclosure where appropriate,
and continued regression testing.

## Candidates not recommended for standalone filing

### Configuration-drift checkpoint recovery

The prior memo treated checkpoint recovery as an active candidate. Feature 070
removed `CheckpointManager`, `RecoveryOrchestrator`, their CLI surface, and resume
logic because the system was unused. Removal does not legally erase a past
invention, but it sharply reduces its commercial relevance, and configuration
fingerprinting plus resume refusal is close to established reproducibility and
workflow invalidation techniques.

### Deterministic hash-based RNG and event identifiers

Constructing a key from seed, employee, year, event type, and salt and hashing it
for a reproducible draw is established practice. Domain-specific key fields are
unlikely to supply nonobviousness. The older Python and SQL implementations also
used different hash functions, undermining any broad cross-platform claim.

### Fast compensation calibration

The compensation-only dbt subgraph is a valuable exact acceleration, and the
secant search is an effective operator workflow. Dependency-closed partial builds,
secant root finding, isolated databases, and reuse of production calculations are
individually conventional. Treat the implementation as product know-how unless a
future mechanism produces a materially different technical result.

### Retirement-plan formulas and regulatory validation

Age-banded contributions, points schedules, Social Security integration,
match-response rules, statutory limits, and compliance validation mostly encode
plan or legal rules using conventional computation. They may be differentiating
features but are poor standalone utility-patent candidates without a separate
technical mechanism.

### Studio interface

The current interface is functional and uses common dashboard, comparison, and
configuration patterns. No distinctive ornamental design has been identified for
a design-patent filing.

## Disclosure and ownership inventory

The repository `crzyc98/planwise_navigator` is public as of this review. Public
GitHub issues and commits may qualify as printed publications or otherwise
publicly available disclosures. For each candidate, counsel should establish:

- conception date and the individuals who contributed to the claimed mechanism;
- reduction-to-practice evidence, including commits, tests, design documents, and
  experiment results;
- first public commit, issue, pull request, demonstration, use, offer for sale, or
  customer disclosure;
- whether each disclosure came from an inventor or an independent third party;
- employment, contractor, sponsor, and assignment obligations; and
- desired countries, because U.S. grace-period treatment does not preserve all
  foreign rights.

Do not delete or rewrite historical evidence to improve a filing narrative.
Preserve the existing Git history, issue history, test results, and dated design
artifacts.

## Recommended next steps

1. Prepare a concise internal invention disclosure for the joint promotion/merit
   estimator before publishing additional implementation detail.
2. Ask registered patent counsel to run a claim-focused patent and non-patent
   literature search covering compensation-event inference, mixture-based latent
   promotion classification, joint hazard/location estimation, and evidence-gated
   fallback.
3. Determine the exact first-public-disclosure date for the workforce solver and
   make a filing decision before the earliest plausible October 2026 deadline.
4. Validate inventorship and ownership before any personal or corporate filing.
5. If filing Candidate 1, include Candidate 3's deterministic parameter-pack and
   provenance machinery as implementation context and possible dependent-claim
   material.
6. Prefer trade-secret treatment for future calibration heuristics, client-data
   mappings, thresholds, and operational tuning that cannot be reverse engineered
   from distributed software or public outputs.

## Bottom line

The joint promotion/merit estimator is the strongest current invention-screening
candidate because its value lies in a specific, coherent solution to circular
identification and unreliable evidence. The exact workforce solver remains
plausible but has narrower likely claim scope, greater abstract-mathematics risk,
and a potentially imminent disclosure deadline. The remainder of the repository
is predominantly strong engineering built from established techniques and is
better protected through execution, copyright, documentation, and selective
confidentiality.
