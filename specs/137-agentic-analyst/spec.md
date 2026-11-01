# Feature Specification: Agentic Analyst (`planalign ask`)

**Feature Branch**: `137-agentic-analyst`
**Created**: 2026-08-12
**Status**: Draft
**Input**: User description: "An LLM analyst layer over the simulation engine and the event stream. Two interaction modes: Explain (decompose a result delta with event-level citations) and Act (write a config delta, run isolated scenarios, report a cited diff). Tool surface, not free-form. On-prem safe: fully disabled when no credentials configured."

## Clarifications

### Session 2026-08-12

- **Q: What is the default egress policy for employee-level result data sent to the model service?**
  A: Aggregates-only by default; row-level egress available behind explicit
  configuration (FR-026, FR-027). Deployment is on the team's own office
  servers reachable only by their analysts, but that governs *inbound* access —
  prompts still cross the network boundary to the model service, so the policy
  is set on what leaves rather than on who can log in. Aggregates-only is also
  the mechanically sound default: a full employee table cannot fit in a model
  context, so row-level reads would rely on arbitrary truncation, which
  FR-019 exists to prevent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explain a result in plain English, with receipts (Priority: P1)

A consultant looking at a finished scenario notices employer cost jumped in 2027 and wants to know why. Instead of writing a chain of ad-hoc queries, they ask the question in natural language and receive a plain-English answer that decomposes the change into its drivers (e.g., headcount growth vs. average compensation vs. match-rate mix), where every quantitative claim in the answer is backed by the specific population of events it was computed from — the number of employees, the number of events, the years involved, and the exact query that produced the figure.

**Why this priority**: This is the demo-defining capability and the lowest-risk slice — it is read-only against an already-completed scenario, requires no new simulation runs, and delivers value on its own. Everything else builds on the same answer-with-citations contract.

**Independent Test**: Point the feature at an existing completed scenario database, ask a "why did X change between year A and year B" question, and verify the answer names the drivers, attaches a citation to each number, and that re-running each cited query independently reproduces the cited figure exactly.

**Acceptance Scenarios**:

1. **Given** a completed multi-year scenario result, **When** the user asks why employer cost changed between two years, **Then** the answer names the contributing drivers, gives a magnitude for each, and attaches to each magnitude the query and the event/employee population it came from.
2. **Given** an answer containing quantitative claims, **When** a reviewer re-executes each cited query against the same result, **Then** every cited figure reproduces exactly.
3. **Given** a question whose answer is not derivable from the available results (e.g., asking about a plan year that was never simulated), **When** the user asks it, **Then** the system states it cannot answer from the available runs and says what is missing, rather than estimating.
4. **Given** a question that mixes simulated output with fitted-from-history parameters, **When** the answer references both, **Then** it labels which figures are simulated projections and which are estimates fitted from client history, including the provenance of the parameter source.

---

### User Story 2 - Never touches anything it shouldn't (Priority: P1)

An administrator must be able to trust that the analyst cannot corrupt existing work. Every data read is read-only and restricted to result stores; the analyst can never modify an existing scenario's results, never writes to the shared development store, and any new work it performs happens in a freshly created isolated result store of its own.

**Why this priority**: Equal-priority with User Story 1 because the feature is not shippable without it. An analyst layer that can mutate a client's completed results is a liability regardless of how good its answers are.

**Independent Test**: Drive the analyst with adversarial instructions (including attempts smuggled into the question text) that try to modify, delete, or write to an existing result store or the shared development store, and verify each attempt is refused at the tool boundary with no side effect on disk.

**Acceptance Scenarios**:

1. **Given** any request the analyst can make, **When** it attempts a data operation that is not a read, **Then** the operation is rejected before execution and the analyst is told the operation is not permitted.
2. **Given** a request targeting the shared development result store, **When** the analyst attempts to read or write it, **Then** the request is rejected and the analyst is directed to an explicit scenario result instead.
3. **Given** the analyst performs new work, **When** that work produces results, **Then** they land in a newly created isolated result store, and the store is retained after the session so the user can verify the answer independently.
4. **Given** a question containing embedded instructions attempting to broaden the analyst's permissions, **When** it is processed, **Then** the enforced permissions are unchanged and the attempt is recorded in the session record.

---

### User Story 3 - Ask for a comparison and get one run for you (Priority: P2)

A consultant asks how the client's current plan design would compare to an alternative (e.g., a safe-harbor basic match). The analyst translates the request into a concrete configuration change, states that change back to the user, runs the alternative in isolation, and reports the headline differences with the same citation discipline as Explain mode — plus the retained result stores so the user can verify the comparison themselves.

**Why this priority**: The highest-leverage capability for sales conversations, but strictly more expensive and slower than Explain mode, and it depends on the same citation and isolation contract. It is deferred to P2 so a shippable read-only slice can land first.

**Independent Test**: Ask for a named plan-design comparison against an existing baseline scenario and verify that (a) the proposed configuration change is stated before anything runs, (b) the alternative executes in its own isolated store, and (c) the reported differences match a manual diff of the two results.

**Acceptance Scenarios**:

1. **Given** a comparison request, **When** the analyst has derived the configuration change, **Then** the change is presented to the user for confirmation before any simulation runs, together with an estimate of how long the run will take.
2. **Given** the user confirms, **When** the comparison completes, **Then** the report states the headline metric differences with citations and names the location of both retained result stores.
3. **Given** the user declines the confirmation, **When** the session ends, **Then** no simulation has run and no new result store was created.
4. **Given** a request the analyst cannot translate into a supported configuration change, **When** it is processed, **Then** it says so plainly and does not run an approximation of the request.

---

### User Story 4 - Safe by default in on-premises deployments (Priority: P2)

Some deployments have no permitted outbound model access at all. In those environments the analyst must be visibly and completely inert: the rest of the product is unaffected, the command explains why it is unavailable and what would enable it, and no attempt is made to reach an external service.

**Why this priority**: A hard deployment constraint. It is P2 only because it is a small amount of work relative to the earlier stories, not because it is optional.

**Independent Test**: Start the product with no model credentials configured and verify every other command behaves identically to today, while the analyst command exits with a clear explanatory message and produces no outbound network activity.

**Acceptance Scenarios**:

1. **Given** no model credentials are configured, **When** the user invokes the analyst, **Then** it reports that the feature is disabled, states what configuration would enable it, and exits without attempting a network call.
2. **Given** credentials are configured for a self-hosted or gateway model endpoint rather than the default one, **When** the analyst runs, **Then** it uses the configured endpoint.
3. **Given** the feature is disabled, **When** any other command runs, **Then** its behavior and output are unchanged from a build without this feature.

---

### Edge Cases

- **Question outside the data**: asked about a year, scenario, or metric not present in the result store — must decline and name what is missing, not extrapolate.
- **Stale or partially built result store**: the target result store was written under a different configuration generation or is mid-build — the analyst must surface the mismatch alongside its answer rather than quietly reporting figures from mixed generations.
- **Empty or zero-row citation**: a driver decomposition yields a population of zero events — the answer must report the absence explicitly rather than presenting a computed figure derived from no observations.
- **Expensive query**: a question whose decomposition requires an unbounded or very large scan — must be bounded and the truncation disclosed, never silently sampled.
- **Analyst reaches its step budget mid-investigation**: must report partial findings, label them as incomplete, and cite what it did establish rather than guessing the remainder.
- **Model service unavailable or rate-limited mid-session**: must fail with a clear message and leave no partially written result store behind.
- **Prompt injection via data**: hostile text stored in a data field (e.g., a scenario name or note) attempting to redirect the analyst — must not alter enforced permissions or the citation requirement.
- **Concurrent access**: the target result store is locked by another process — must report the conflict, not wait indefinitely.
- **Numbers that disagree**: a driver decomposition that does not reconcile to the total being explained — the residual must be reported explicitly rather than absorbed into a named driver.

## Requirements *(mandatory)*

### Functional Requirements

#### Asking and answering

- **FR-001**: Users MUST be able to ask a natural-language question about a specified completed scenario result from the command line and receive a plain-English answer.
- **FR-002**: Every quantitative claim in an answer MUST carry a citation identifying the exact query executed, the result store it ran against, and the size of the population it summarizes (row/event/employee counts as applicable).
- **FR-003**: The system MUST decline to answer any question that cannot be established from the available results, stating what data would be required, and MUST NOT produce an estimated or inferred figure in place of a measured one.
- **FR-004**: Answers MUST distinguish simulated projections from parameters fitted from client history, and MUST surface the provenance of any fitted parameters referenced.
- **FR-005**: The system MUST surface any configuration-generation mismatch or incomplete-build condition detected on the target result store as part of its answer.
- **FR-006**: When a driver decomposition does not fully reconcile to the total being explained, the system MUST report the unexplained residual explicitly.
- **FR-007**: Each session MUST produce a durable record containing the question, every tool call and its arguments, every query executed, and the final answer, retained for later audit.

#### Acting

- **FR-008**: Users MUST be able to request a comparison against an alternative plan design and have the system derive the corresponding configuration change.
- **FR-009**: The system MUST present the derived configuration change and an execution-time estimate to the user, and MUST obtain explicit confirmation before executing any simulation.
- **FR-010**: Any simulation the system runs MUST execute in a newly created isolated result store, which MUST be retained after the session and its location reported to the user.
- **FR-011**: Comparison reports MUST state headline metric differences with the same citation discipline required of explain-mode answers.
- **FR-012**: The system MUST refuse requests it cannot translate into a supported configuration change rather than running an approximation.

#### Boundaries and safety

- **FR-013**: All data access performed on behalf of the analyst MUST be read-only, enforced at the point of execution and not by instruction alone.
- **FR-014**: The system MUST NOT read from or write to the shared development result store.
- **FR-015**: The system MUST NOT modify or delete any pre-existing result store.
- **FR-016**: The system MUST expose a bounded, explicitly defined set of capabilities to the model; capabilities outside that set MUST be unavailable regardless of what the model requests.
- **FR-017**: Enforced permissions MUST be immune to instructions appearing in user questions or in data read from result stores; attempts to broaden them MUST be recorded in the session record.
- **FR-018**: The system MUST bound each session by a maximum number of investigative steps and MUST report partial, explicitly labelled findings when that bound is reached.
- **FR-019**: The system MUST bound the size of any single data read and MUST disclose truncation in the answer when it occurs.

#### Deployment and configuration

- **FR-020**: The feature MUST be disabled by default when no model credentials are configured, exiting with an explanation of what would enable it and performing no outbound network call.
- **FR-021**: The model endpoint MUST be configurable so deployments can direct it at a self-hosted or gateway endpoint.
- **FR-022**: Administrators MUST be able to disable the feature explicitly even when credentials are present.
- **FR-023**: When the feature is disabled, all other product behavior MUST be unchanged.
- **FR-024**: The system MUST report the model-service cost or usage consumed by a session to the user at its conclusion.

#### Data handling

- **FR-025**: The system MUST restrict what leaves the deployment to the model service according to a configured egress policy, and MUST make the active policy visible to the user in the session record.
- **FR-026**: The default egress policy MUST be aggregates-only: grouped counts, sums, averages, distributions, and structural metadata (table and column names) may be transmitted; individual employee rows MUST NOT be, including de-identified ones.
- **FR-027**: Administrators MUST be able to opt in to a row-level egress policy through explicit configuration. When active, this MUST be stated in the session record and surfaced to the user at the start of the session.
- **FR-028**: Under the default policy, an attempted read whose result would transmit individual rows MUST be refused at the point of execution with an explanation, and MUST NOT be silently reduced to an aggregate.

### Key Entities

- **Question**: a natural-language request from a user, bound to a target scenario result and a mode of operation (explain or act).
- **Session Record**: the durable audit artifact for one question — the question, ordered tool invocations with arguments, queries executed, results summaries, the final answer, permission-violation attempts, step count, and usage consumed.
- **Citation**: the evidence attached to a quantitative claim — the query text, target result store, population size, and the years/scenario scope the figure covers.
- **Capability**: one of the bounded operations the analyst may perform (read results, inspect a scenario's configuration, run an isolated scenario, compare two results). Each has a fixed contract and enforced restrictions.
- **Isolated Result Store**: a newly created result store produced by an act-mode run, retained for user verification and never shared with a pre-existing scenario.
- **Egress Policy**: the configured rule governing what portion of result data may be transmitted to the model service.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A consultant can go from "this number looks odd" to a cited, driver-level explanation in a single question, in under 2 minutes of wall time, without writing a query.
- **SC-002**: 100% of quantitative claims in answers carry a citation whose re-execution reproduces the cited figure exactly.
- **SC-003**: Across a fixed set of adversarial attempts to write, delete, or reach the shared development store, 100% are refused with zero on-disk side effects.
- **SC-004**: On a benchmark set of at least 15 questions with known correct answers, at least 90% of answers are factually correct and 0% contain an uncited quantitative claim; questions outside the data are declined rather than answered in 100% of cases.
- **SC-005**: An act-mode plan-design comparison completes end-to-end from a single natural-language request, and the reported differences match a manually computed diff of the two retained result stores exactly.
- **SC-006**: With credentials absent, the full existing test suite passes unchanged and the analyst command exits with an explanatory message in under 1 second with no network activity.
- **SC-007**: Every session is fully reconstructible after the fact from its retained record — an auditor can replay each query and reach the same answer.
- **SC-008**: A typical explain-mode question consumes a bounded and reported amount of model usage, with the session's cost visible to the user before they run the next one.

## Assumptions

- **A-001**: v1 targets the command line only. A Studio chat panel is explicitly out of scope for this feature and will be a follow-up built on the same backing service (see Out of Scope).
- **A-002**: Each invocation answers one question. Persisted multi-turn conversation state across invocations is out of scope for v1; the analyst may still take multiple investigative steps within a single invocation.
- **A-003**: The analyst operates against scenario results that already exist. Producing the baseline result is the user's job, not the analyst's.
- **A-004**: Act-mode runs reuse the existing isolated-scenario execution path and its worker-count budgeting; the analyst introduces no new execution mechanism.
- **A-005**: Read-only query enforcement, scenario-result path resolution, result comparison, and configuration diffing already exist as services in the product and are reused rather than reinvented.
- **A-006**: Session records are retained on local disk under the existing runtime-output convention; retention is subject to ordinary disk hygiene, not a new lifecycle policy.
- **A-007**: The single-user, single-workstation deployment model of the existing command line applies; no multi-tenant access control is introduced.
- **A-008**: Cost reporting is per-session and advisory; hard spend caps are out of scope for v1.

## Dependencies

- Completed scenario results produced by the existing simulation engine, including the run-metadata provenance record.
- Fitted-parameter provenance from the parameter-fitting and backtesting capabilities, for distinguishing fitted evidence from simulated output.
- The existing isolated scenario execution path used by batch and optimizer runs.
- An accessible model service, reachable at a configurable endpoint, with credentials supplied by the deployment.

## Deployment Reality (as of 2026-08-12)

No model-service credentials are available to this deployment, and none are
expected on a known date. GenAI API access may become available later. This
does not invalidate the spec, but it does mean **User Stories 1 and 3 are not
buildable today** — both require the model to drive an investigative loop
(ask, query, read result, query again), which cannot be done through a
human-mediated chat window.

What analysts can do today is paste into a general-purpose chat assistant
(e.g. Microsoft Copilot Chat) by hand. That constrains the design in one
important way: the model gets exactly one shot with whatever text the analyst
gives it, and cannot fetch anything itself.

The consequence worth recording: **the defensible part of this feature — the
deterministic driver decomposition and its citations — does not require a
model at all.** Only the plain-English narration does. That suggests a
separable, buildable-now capability:

- **Offline evidence pack**: a command that takes the same question shape
  ("why did employer cost change between year A and year B in scenario X"),
  runs the decomposition deterministically, and emits a self-contained,
  aggregates-only pack — the driver breakdown, each figure's query and
  population size, the residual, and the run's provenance — formatted for an
  analyst to paste into a chat assistant for prose, or to read directly.

This inverts the trust model favourably: the numbers are computed by the
product and are correct by construction, and the model is confined to wording.
It also satisfies FR-026 by construction, since a pack contains only
aggregates. Its main limitation is that the question shapes are fixed rather
than open-ended, which is precisely what the model was buying.

Whether to build the evidence pack now as its own feature, or wait for
credentials and build the full analyst, is an open decision — not settled by
this spec.

## Out of Scope (v1)

- Autonomous multi-step plan-design optimization. The analyst may invoke the existing optimizer and narrate its results, but does not conduct its own search.
- Any write access to configurations or result stores outside the isolated stores it creates.
- A Studio chat panel (follow-up feature).
- Persisted multi-turn conversation history across invocations.
- Scheduled or unattended analyst runs.
- Hard model-spend enforcement.
