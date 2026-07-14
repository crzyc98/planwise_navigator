# Feature Specification: Run Provenance Report

**Feature Branch**: `[111-run-provenance-report]`
**Created**: 2026-07-13
**Status**: Draft
**Input**: User description: "Create a Run Provenance Report that gives enterprise reviewers a single, tamper-evident audit artifact for any archived PlanAlign simulation run, retrievable from the CLI or Studio API without rerunning the simulation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a Complete Audit Artifact (Priority: P1)

An analyst selects a specific archived simulation run and generates one concise human-readable audit sheet plus one machine-readable representation. Both representations identify the run and contain the evidence captured for that run, allowing an enterprise reviewer to understand which inputs, assumptions, execution context, outcomes, and validation results produced it without rerunning the simulation.

**Why this priority**: This is the core audit need: reviewers require a self-contained artifact that binds execution identity, provenance, summarized outcomes, and validation evidence to one archived run.

**Independent Test**: Using an archived completed run with all required provenance, request the report through either supported access channel and verify that both representations contain the required evidence, agree field-for-field, and identify the report as fully verified.

**Acceptance Scenarios**:

1. **Given** a completed archived run with all required provenance, **When** an analyst generates its report, **Then** the human-readable and machine-readable representations identify the same run, contain the same evidence, and classify the report as fully verified.
2. **Given** a report generated through the command-line interface, **When** the same run is requested through the Studio service interface, **Then** both requests produce equivalent evidence and the same deterministic report digest.
3. **Given** a report for a multi-year run, **When** a reviewer reads its outcome sections, **Then** the reviewer can inspect event counts and workforce reconciliation totals for every simulation year and validation results captured during the run.

---

### User Story 2 - Detect Missing or Unverifiable Provenance (Priority: P2)

An enterprise reviewer generates a report for a legacy, failed, cancelled, or partially completed run and sees exactly which required evidence is available, which fields are unavailable, and why the run cannot be treated as fully verified.

**Why this priority**: Audit confidence depends on honest handling of incomplete archives. Silently filling gaps from current state would misrepresent how the run was produced.

**Independent Test**: Request a report for an archived run with known missing evidence and verify that every missing required field is listed, no current-state substitute appears, available run-bound evidence remains visible, and the overall verification disposition is not fully verified.

**Acceptance Scenarios**:

1. **Given** an archived run missing its captured configuration fingerprint and seed-file fingerprints, **When** its report is generated, **Then** those fields are individually identified as unavailable and the report is not classified as fully verified.
2. **Given** a failed or cancelled run with evidence captured only through its last completed stage, **When** its report is generated, **Then** the report preserves the run's actual status, presents available evidence, identifies missing expected evidence, and does not imply successful completion.
3. **Given** current configuration, source control state, input files, or database contents differ from those used by the archived run, **When** the report is generated, **Then** the report uses only run-bound archived evidence and does not substitute the current values.
4. **Given** the archive cannot establish that a piece of evidence belongs to the selected run, **When** the report is generated, **Then** that evidence is treated as unavailable rather than included by inference.

---

### User Story 3 - Verify Integrity and Record Review Sign-Off (Priority: P3)

An enterprise reviewer independently confirms that a report has not changed and records a human sign-off tied to the verified report digest.

**Why this priority**: A tamper-evident digest and digest-bound review decision turn the report into a practical enterprise audit handoff while avoiding formal electronic-signature scope.

**Independent Test**: Generate a report twice from unchanged archived evidence, verify identical digests, alter one evidence value in a copy and verify the integrity check fails, then complete the sign-off fields with an explicit reference to the original digest.

**Acceptance Scenarios**:

1. **Given** unchanged archived evidence for a run, **When** the report is generated repeatedly or through either supported channel, **Then** the deterministic report digest is identical.
2. **Given** any evidence value in a generated report is altered, removed, or added, **When** a reviewer recomputes or verifies the digest, **Then** the report fails integrity verification.
3. **Given** a reviewer has verified the report, **When** the reviewer completes the sign-off section, **Then** the reviewer name, decision, timestamp, comments, and exact report digest being approved can be recorded.

### User Story 4 - Review and Download from PlanAlign Studio (Priority: P1)

An analyst who launches simulations from PlanAlign Studio opens a terminal run in Run History, reviews its provenance evidence in a dedicated Studio page, and downloads the complete audit report without using the command line.

**Why this priority**: Studio is the primary simulation interface, so report discovery and review must be available in the same workflow that creates archived runs.

**Independent Test**: Open a completed, failed, or cancelled UUID-addressed run in Studio Run History, select **View Provenance**, verify the page displays the report disposition, findings, evidence summaries, validation results, and digest, then select **Download Audit Report** and verify the authenticated ZIP contains the matching JSON and Markdown files.

**Acceptance Scenarios**:

1. **Given** an archived Studio run, **When** an analyst expands it in Run History, **Then** Studio offers **View Provenance** and **Download Audit Report** actions without rerunning the simulation.
2. **Given** a valid report, **When** the analyst opens its Studio view, **Then** the view prominently distinguishes fully verified, incomplete, and unverifiable reports and exposes missing evidence before the detailed audit sections.
3. **Given** API token protection is enabled, **When** the analyst downloads the audit report through Studio, **Then** the existing Studio API credentials are applied to the ZIP request.
4. **Given** a legacy run without a UUID or an active non-terminal run, **When** Run History renders it, **Then** Studio does not offer an action that would imply an archived provenance report is available.

### Edge Cases

- The selected run ID does not exist or is not an archived simulation run.
- Multiple archived runs share scenario or plan design identifiers; selection remains unambiguous by run ID.
- A run has no simulation years completed, or only a subset of its intended years completed.
- A simulation year has zero events, no workforce snapshot, or an incomplete reconciliation.
- A validation check ran more than once, stopped before completion, or has no affected-record count.
- A run records a dirty working tree but lacks evidence that distinguishes the dirty state used during execution.
- Effective configuration or seed-file evidence exists but its archived fingerprint does not match its archived content.
- An event type, validation severity, or run status is unknown to the current software version.
- A fingerprinted input or seed filename contains a path or label that could expose sensitive environment information.
- The archive is readable but one or more evidence records are malformed, duplicated, or cannot be bound uniquely to the run.
- The report is requested while another process is using the archive; report generation remains read-only and either completes from a consistent view or returns a clear failure.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow an authorized analyst to request a provenance report for one archived simulation run by its unique run ID through both the command-line interface and the Studio service interface, without rerunning any simulation stage.
- **FR-002**: The system MUST reject an unknown or non-archived run ID with a clear outcome and MUST NOT fall back to a scenario's latest run.
- **FR-003**: Each report MUST identify the selected run with its run ID, archived status, scenario identifier, plan design identifier, intended simulation-year range, and actually completed simulation years.
- **FR-004**: Each report MUST include the run's captured start and end timestamps, plus available stage or cancellation/failure timing needed to interpret partial execution.
- **FR-005**: Each report MUST include the software version, Git commit SHA, and working-tree state captured for execution. If the working tree was dirty, the report MUST include any archived dirty-state fingerprint or equivalent run-bound evidence available to distinguish the executed code state; otherwise it MUST identify that distinction as unavailable.
- **FR-006**: Each report MUST include the effective configuration used by the run and its captured configuration fingerprint, including scenario and plan-design overrides as resolved for execution.
- **FR-007**: Each report MUST include the random seed captured for the run.
- **FR-008**: Each report MUST include the census input fingerprint and only non-sensitive metadata needed to identify the input, such as a safe logical label and record count when captured.
- **FR-009**: Each report MUST include a fingerprint and safe logical identity for every effective seed file used by the run.
- **FR-010**: Each report MUST show event counts grouped by event type and simulation year for the archived run, including explicit zero totals when the archive proves that a completed year had no events.
- **FR-011**: Each report MUST show annual workforce reconciliation totals for every completed simulation year, including opening workforce, hires, terminations, expected closing workforce, actual closing workforce, and any reconciliation variance when those values were captured.
- **FR-012**: Each report MUST show every validation result captured during the run with the check name, severity, pass/fail outcome, affected-record count, and the run's overall validation disposition.
- **FR-013**: The report MUST preserve validation results as captured during execution and MUST NOT rerun checks or derive replacement results from current data.
- **FR-014**: All evidence included in a report MUST be demonstrably bound to the selected run. Evidence that cannot be uniquely bound to that run MUST be reported as unavailable.
- **FR-015**: Report generation MUST use archived run evidence only and MUST NOT silently substitute current configuration, code state, census or seed files, validation results, or database contents.
- **FR-016**: For every unavailable, malformed, integrity-mismatched, or unbound required field, the report MUST list the field individually with a safe reason and MUST NOT invent a value.
- **FR-017**: Each report MUST state one overall verification disposition: **Fully Verified** when the run completed successfully and all required evidence is present, run-bound, and internally consistent; **Incomplete** when the run did not complete or expected execution evidence was not produced; or **Unverifiable** when required provenance is missing, unbound, malformed, or fails an available integrity check. An incomplete report that is also unverifiable MUST use **Unverifiable** and separately preserve the run's incomplete status.
- **FR-018**: A report MUST NOT present a failed, cancelled, or partially completed run as fully verified. A legacy completed run MUST meet the same evidence requirements as every other fully verified report.
- **FR-019**: Each request MUST produce a concise human-readable audit sheet and a machine-readable representation containing the same provenance evidence, summaries, missing-evidence findings, verification disposition, and report digest.
- **FR-020**: When the same archived evidence is requested repeatedly, the representations MUST preserve equivalent field values and MUST produce the same deterministic report digest regardless of access channel or request time.
- **FR-021**: The report digest MUST cover all reported run evidence, missing-evidence findings, and verification disposition in a defined, reproducible order so an independent reviewer can confirm whether any covered content changed.
- **FR-022**: The report MUST identify the digest method and provide sufficient instructions or structured information for an independent reviewer to recompute and compare the digest.
- **FR-023**: The human-readable audit sheet MUST include a sign-off section for reviewer name, decision, timestamp, comments, and the exact report digest being approved. Empty sign-off fields and later handwritten or external sign-off entries MUST NOT change the digest of the underlying run evidence.
- **FR-024**: The machine-readable representation MUST include the same sign-off field structure and report-digest reference so a completed sign-off can be associated unambiguously with the reviewed report, while identity-backed electronic and cryptographic signing remain outside scope.
- **FR-025**: Reports MUST NOT contain census records, employee identifiers, employee-level events, employee-level validation details, or other employee-level personally identifiable information.
- **FR-026**: Input and seed evidence MUST be limited to fingerprints and safe metadata; physical paths, embedded credentials, user names, and other environment details MUST be omitted or safely generalized.
- **FR-027**: Report generation MUST be read-only and MUST NOT modify simulation results, shared development databases, archived artifacts, run metadata or history, configurations, input files, or seed files.
- **FR-028**: Report generation MUST read a consistent archived view so evidence from concurrent changes or different runs cannot be mixed in one report.
- **FR-029**: Unknown future run statuses, event types, or validation severities MUST be preserved safely as captured rather than discarded or remapped to a misleading known value.
- **FR-030**: If the report cannot safely read a consistent archive or cannot determine the selected run's identity, generation MUST fail clearly without emitting a report that appears valid.
- **FR-031**: Studio MUST expose **View Provenance** and **Download Audit Report** actions for terminal UUID-addressed runs from the existing Run History workflow.
- **FR-032**: The Studio provenance view MUST use the same authenticated report endpoint and display the selected run identity, verification disposition, missing-evidence findings, execution/source/configuration/input evidence, annual aggregates, validation results, digest, and sign-off reference without deriving replacement evidence in the browser.
- **FR-033**: Studio MUST allow authorized users to download the two-file JSON/Markdown ZIP and the individual JSON or Markdown representation while applying the existing Studio API-token mechanism.
- **FR-034**: Studio provenance view or download failures MUST be presented as clear UI errors and MUST NOT modify the archived run or trigger simulation execution.

### Key Entities

- **Archived Run**: The immutable identity and lifecycle record of one simulation execution, including run ID, status, scenario, plan design, intended and completed years, and execution timestamps.
- **Run Provenance Evidence**: Run-bound execution context and inputs, including software and source state, effective configuration, random seed, census fingerprint, and effective seed-file fingerprints.
- **Run Outcome Summary**: Aggregated event counts, annual workforce reconciliation totals, and captured validation results for the archived run, with no employee-level records.
- **Missing Evidence Finding**: One required field that is unavailable, malformed, inconsistent, or not provably bound to the run, plus a safe reason.
- **Provenance Report**: The complete evidence set, outcome summaries, missing-evidence findings, verification disposition, and deterministic digest for one archived run.
- **Review Sign-Off**: Reviewer name, decision, timestamp, comments, and the exact report digest to which the human decision applies; it is an attestation reference rather than a formal electronic signature.

### Assumptions

- Existing authorization rules for viewing archived runs also govern access to their provenance reports; this feature does not introduce a new permissions model.
- An archived run is a retained run record addressable by a unique run ID, regardless of whether its execution completed, failed, or was cancelled.
- Fully verified status requires successful completion because failed, cancelled, and partial executions did not produce a complete simulation outcome, even when their captured provenance is otherwise intact.
- The annual workforce reconciliation uses opening workforce plus hires minus terminations as the expected closing workforce and compares that value with the captured actual closing workforce; unavailable components are reported individually rather than reconstructed from current data.
- The deterministic digest applies to the normalized report evidence and verification findings. The sign-off records the digest it approves and can be completed later without changing the underlying evidence digest.
- Report creation is an on-demand read of already archived evidence. Persisting a newly generated report or sign-off into run history is outside the initial scope.
- Formal identity verification, electronic signature workflows, cryptographic signing, timestamp authorities, and approval workflow enforcement are outside the initial scope.
- Safe metadata may include logical labels, sizes, counts, and timestamps only when captured for the run and when they do not reveal employee-level or sensitive environment information.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of completed test runs with complete captured provenance, a reviewer can retrieve both report representations and identify the run, its effective inputs and assumptions, yearly outcomes, validation disposition, and integrity digest without rerunning the simulation.
- **SC-002**: For 100% of test runs with intentionally missing, malformed, mismatched, or unbound required evidence, the report identifies every affected required field and never classifies the report as fully verified.
- **SC-003**: Repeated report generation from unchanged archived evidence, including generation through both supported access channels, produces the same digest in 100% of test cases.
- **SC-004**: Altering, adding, or removing any covered evidence field causes independent digest verification to fail in 100% of tampering tests.
- **SC-005**: Human-readable and machine-readable representations agree on 100% of required evidence values, missing-evidence findings, dispositions, and digest values in cross-format tests.
- **SC-006**: Reports contain zero employee-level census records, employee identifiers, employee-level events, or employee-level validation details across automated privacy scans of all test fixtures.
- **SC-007**: A reviewer can locate the run identity, verification disposition, missing evidence, yearly event counts, workforce reconciliation, validation results, digest, and sign-off section within 5 minutes using only the human-readable audit sheet.
- **SC-008**: Generating a report for an archived run leaves all monitored simulation results, archives, shared databases, run history, configuration, and input artifacts byte-for-byte or record-for-record unchanged in 100% of read-only behavior tests.
- **SC-009**: At least 90% of enterprise-review usability-test participants correctly distinguish a fully verified completed run from an incomplete or unverifiable run on their first review.
- **SC-010**: A Studio user can navigate from an archived run in Run History to its provenance view and initiate the matching audit-report download in no more than two actions, without using the CLI.
