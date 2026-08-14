# Feature Specification: Evidence Packs — Cited Driver Decomposition

**Feature Branch**: `138-evidence-pack`
**Created**: 2026-08-12
**Status**: Draft
**Input**: User description: "Deterministic driver-decomposition evidence packs: explain why a headline metric moved between two years with per-figure citations, populations, and an explicit unexplained residual. Studio panel first, aggregates-only, no model required."

## Clarifications

### Session 2026-08-12

- **Q: Which surface do analysts actually use?**
  A: Studio primarily. The pack is delivered as a Studio panel with an export
  action; a command-line equivalent is secondary and exists for verification
  and scripting, not as the analyst's route in (US1, US4).
- **Q: Which questions does the pack answer?**
  A: Movement in the six canonical headline metrics already agreed by the
  ensemble capability — active headcount, total compensation, employer match
  cost, total employer plan cost, participation rate, average deferral rate.
  Reusing that curated list avoids inventing a second, competing notion of
  "the metrics that matter" (FR-001, A-002).
- **Q: Does this depend on model-service access?**
  A: No. That is the point of the feature. The decomposition is deterministic
  and the pack is complete and readable on its own; a chat assistant is an
  optional consumer of the exported text, never a dependency.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See why a headline number moved, without writing a query (Priority: P1)

An analyst reviewing a finished scenario in Studio sees employer match cost rise
sharply between two years. They select the metric and the two years, and get a
breakdown that attributes the change to named drivers — how much came from
having more employees, how much from those employees earning more, how much
from the plan itself paying out at a different rate — with the size of each
contribution, the population each was computed from, and any portion of the
change the breakdown does not explain.

**Why this priority**: This is the entire feature. It converts the most common
client question ("why did this go up?") from a half-day of ad-hoc querying into
a panel, and it does so with numbers that are correct by construction rather
than correct-if-the-analyst-queried-well.

**Independent Test**: Open a completed scenario in Studio, request a
decomposition of employer match cost between two adjacent years, and verify the
named driver contributions sum to the reported total change within the stated
residual, and that each contribution's cited query reproduces its figure when
run independently.

**Acceptance Scenarios**:

1. **Given** a completed multi-year scenario, **When** the analyst requests a decomposition of a canonical metric between two years, **Then** the result names each driver, gives its contribution in both absolute and percentage-of-change terms, and states the population it was computed from.
2. **Given** a decomposition, **When** the driver contributions are summed, **Then** they equal the total change minus the explicitly reported residual, exactly.
3. **Given** any figure in the pack, **When** a reviewer re-executes that figure's cited query against the same scenario, **Then** the figure reproduces exactly.
4. **Given** two years that are not adjacent, **When** a decomposition is requested, **Then** it is produced for that span with the same guarantees.

---

### User Story 2 - Trust the breakdown, including what it can't explain (Priority: P1)

Anyone presenting these numbers to a client needs to know the breakdown is
honest about its own limits. Any portion of a change that the named drivers do
not account for is reported as an explicit residual rather than absorbed into
whichever driver is largest; the provenance of the underlying run is stated;
and conditions that would make the figures untrustworthy — a partially built
result, a mixed-configuration result — are surfaced on the pack itself.

**Why this priority**: Equal-priority with User Story 1. A decomposition that
silently absorbs its own error is worse than no decomposition, because it is
confidently wrong in front of a client. The residual is the feature's integrity
guarantee and cannot be a follow-up.

**Independent Test**: Construct a scenario where a known portion of a metric's
movement falls outside the modelled drivers, request the decomposition, and
verify the unexplained portion appears as a stated residual of the correct
magnitude rather than being distributed across the named drivers.

**Acceptance Scenarios**:

1. **Given** a decomposition where the named drivers fully account for the change, **When** the pack is produced, **Then** the residual is reported as zero rather than omitted.
2. **Given** a decomposition where drivers do not fully account for the change, **When** the pack is produced, **Then** the unexplained amount is reported as a named residual line with its share of the total change.
3. **Given** a residual exceeding a materiality threshold, **When** the pack is produced, **Then** it is visually flagged as a caution rather than presented as a routine line.
4. **Given** a target result with a configuration-generation mismatch or an incomplete build, **When** a pack is produced from it, **Then** that condition is stated prominently on the pack.
5. **Given** any pack, **When** it is produced, **Then** it states the scenario, the run timestamp, the random seed, and the configuration fingerprint of the run it describes.

---

### User Story 3 - Take it out of the tool (Priority: P2)

Having read a decomposition, the analyst needs it somewhere else — in a client
deck, in an email, or pasted into a general-purpose chat assistant to draft
prose around it. They export the pack as self-contained text that carries every
figure, every citation, and the provenance line, and remains meaningful with no
access to the product.

**Why this priority**: This is what makes the pack useful today rather than
merely visible. It is P2 only because the decomposition must exist before it
can be exported.

**Independent Test**: Export a pack, open it in a plain text editor with no
access to the product, and verify a reader can identify every figure, its
query, its population, the residual, and which run it came from.

**Acceptance Scenarios**:

1. **Given** a displayed decomposition, **When** the analyst exports it, **Then** the exported text contains every figure, its citation, the residual, and the provenance line.
2. **Given** an exported pack, **When** it is read outside the product, **Then** no figure requires product access to interpret.
3. **Given** an exported pack, **When** its contents are inspected, **Then** it contains only aggregate figures and structural metadata — no individual employee is identifiable from it.

---

### User Story 4 - Verify it from the command line (Priority: P3)

Someone auditing a pack, or scripting a batch of them, produces the same
decomposition from the command line and gets byte-identical figures to the
Studio panel.

**Why this priority**: Valuable for verification and automation, but it is not
how the analyst audience works. It exists so packs are checkable and
scriptable, not as a primary route.

**Independent Test**: Produce the same decomposition through both surfaces
against the same scenario and diff the figures.

**Acceptance Scenarios**:

1. **Given** the same scenario, metric, and year pair, **When** a pack is produced from the command line and from Studio, **Then** every figure is identical.
2. **Given** a scenario path, **When** a pack is requested for a metric the scenario cannot support, **Then** the command explains what is missing and exits non-zero.

---

### Edge Cases

- **Metric absent from the result**: the target result predates a metric's supporting columns — the pack must state the metric is unavailable for that run, not report zero.
- **Year not simulated**: one or both requested years are outside the run's range — refused with the available range stated.
- **Zero denominator**: a driver's base-year value is zero (e.g. no matched participants in the base year), making a ratio-based contribution undefined — must be reported as undefined with the reason, never as zero or infinity.
- **Sign-flipping change**: the metric moves from positive to negative or the total change is near zero, making percentage-of-change shares unstable or enormous — shares must be suppressed or presented as absolute-only rather than printing misleading percentages.
- **Rate metrics vs. stock metrics**: participation rate and average deferral rate are ratios, not sums, so a contribution decomposition must account for population churn (who entered and left the denominator) rather than treating them like totals.
- **Population changed underneath the metric**: employees present in one year and absent in the other — the decomposition must state how the entering and leaving populations were treated.
- **Result store locked by another process**: reported as a conflict, not waited on indefinitely.
- **Very large result**: decomposition must complete within the interactive budget or degrade to an explicit "computing" state, never silently sample.
- **Residual is the largest line**: the pack must not present a decomposition as explanatory when the unexplained portion dominates; it must say the drivers do not explain this movement.

## Requirements *(mandatory)*

### Functional Requirements

#### Producing a decomposition

- **FR-001**: Users MUST be able to request a decomposition of any of the six canonical headline metrics — active headcount, total compensation, employer match cost, total employer plan cost, participation rate, average deferral rate — between two simulation years of a completed scenario.
- **FR-002**: Each decomposition MUST attribute the total change to a fixed, named set of drivers appropriate to that metric, reported in both absolute terms and as a share of the total change.
- **FR-003**: Each driver contribution MUST state the population it was computed from, expressed as a count appropriate to the metric.
- **FR-004**: Each figure MUST carry a citation containing the exact, re-executable query that produced it and the result store it ran against.
- **FR-005**: Decompositions MUST be deterministic — the same scenario, metric, and year pair MUST produce identical figures on every invocation.
- **FR-006**: The system MUST support non-adjacent year spans with the same guarantees as adjacent ones.

#### Honesty

- **FR-007**: The system MUST compute and report the portion of the total change not attributable to any named driver as an explicit residual line, including when it is zero.
- **FR-008**: The system MUST NOT distribute unexplained change across named drivers under any circumstance.
- **FR-009**: The system MUST flag a residual exceeding a materiality threshold as a caution, and MUST state that the drivers do not explain the movement when the residual is the largest single contribution.
- **FR-010**: Every pack MUST state the provenance of the run it describes — scenario identity, run timestamp, random seed, and configuration fingerprint.
- **FR-011**: The system MUST surface configuration-generation mismatch or incomplete-build conditions detected on the target result as a prominent warning on the pack.
- **FR-012**: Where a driver contribution is mathematically undefined, the system MUST report it as undefined with the reason, and MUST NOT substitute zero.
- **FR-013**: Where the total change is near zero or changes sign, the system MUST suppress percentage-of-change shares rather than present unstable values.
- **FR-014**: For ratio metrics, the pack MUST state how employees entering and leaving the population between the two years were treated.

#### Delivery

- **FR-015**: Studio MUST present decompositions for a selected scenario, metric, and year pair, showing drivers, shares, populations, residual, warnings, and provenance.
- **FR-016**: Studio MUST allow the displayed pack to be exported as self-contained text that retains every figure, citation, residual, and the provenance line.
- **FR-017**: Exported packs MUST be interpretable with no access to the product.
- **FR-018**: A command-line equivalent MUST produce figures identical to the Studio panel for the same inputs.
- **FR-019**: The system MUST reject requests for metrics or years the target result cannot support, stating what is missing.

#### Data handling

- **FR-020**: Packs MUST contain only aggregate figures and structural metadata; no individual employee may be identifiable from a pack or its export.
- **FR-021**: All result access MUST be read-only, and the system MUST NOT write to any result store.

### Key Entities

- **Evidence Pack**: the complete answer to one "why did this metric move" question — the metric, the year span, the ordered driver contributions, the residual, warnings, and provenance.
- **Driver**: one named component of a metric's change, carrying an absolute contribution, a share of the total, the population it summarizes, and its citation.
- **Residual**: the portion of the total change not attributable to any named driver, always present, never redistributed.
- **Citation**: the re-executable query and target result store behind a single figure.
- **Provenance Line**: the identity of the run a pack describes — scenario, timestamp, seed, configuration fingerprint — plus any trust warnings detected on it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst can go from noticing an unexpected headline number to a named, quantified driver breakdown in under 30 seconds, without writing a query.
- **SC-002**: For every canonical metric, named drivers plus the reported residual reconcile to the total change exactly, verified across a matrix of scenarios and year spans.
- **SC-003**: 100% of figures in a pack reproduce exactly when their cited query is re-executed independently.
- **SC-004**: Repeated production of the same pack yields byte-identical figures, and the Studio and command-line surfaces agree exactly.
- **SC-005**: No pack or export contains a figure traceable to an individual employee, verified across the full metric matrix.
- **SC-006**: A decomposition over a result of at least 60,000 employee-years completes within the interactive budget.
- **SC-007**: An analyst unfamiliar with the product can read an exported pack and correctly state what drove the change and what portion was unexplained.
- **SC-008**: Every degenerate case in Edge Cases produces a stated explanation rather than a misleading number, verified by test.

## Assumptions

- **A-001**: Packs describe completed scenario results that already exist. Producing results is out of scope.
- **A-002**: The six canonical headline metrics are taken as given from the existing ensemble capability rather than redefined here, so the product has one notion of "headline metric".
- **A-003**: Driver sets are fixed per metric and defined during design, not user-configurable in v1.
- **A-004**: Read-only result access, scenario path resolution, and run provenance already exist as services and are reused rather than reinvented.
- **A-005**: Decomposition for sum-like metrics uses an exact factor attribution, so a correct implementation yields a zero residual; the residual line exists to detect implementation error and to carry genuine unexplained movement in metrics where exact attribution is not available.
- **A-006**: The shared development result store is a valid read target for a pack, since packs never write. Isolation rules constrain writes, and packs perform none.
- **A-007**: Single-user deployment; no per-user access control is introduced.

## Dependencies

- Completed scenario results with run provenance metadata.
- The existing canonical headline metric definitions.
- The existing Studio scenario selection and result-path resolution.

## Out of Scope (v1)

- Cross-scenario decomposition (explaining why scenario A differs from scenario B rather than why one scenario moved across years).
- Natural-language questions or generated prose — a pack is structured output; narration is [137-agentic-analyst](../137-agentic-analyst/spec.md).
- User-defined or configurable driver sets.
- Decomposition of metrics outside the canonical six.
- Attribution of movement to stochastic variation, which is the ensemble capability's job.
- Scheduled or automated pack generation.
