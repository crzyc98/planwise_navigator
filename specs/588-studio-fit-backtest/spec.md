# Feature Specification: Studio Workflows for Parameter Fit and Backtest

**Feature Branch**: `588-studio-fit-backtest`
**Created**: 2026-09-28
**Status**: Draft
**Input**: Issue #588 — "Add Studio workflows for parameter fit and backtest". Historical parameter fitting and held-out backtesting exist only as command-line workflows. The analyst team works exclusively in Studio and never uses the command line, so today the capability is effectively unavailable to them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fit parameters from census history in Studio (Priority: P1)

An analyst has several years of a client's annual census files. In Studio, they add those files to the workspace. Before running anything, they check what the system found: each year, its file, row count, and content fingerprint. They choose the scenario whose current assumptions should be used as the starting point, then start a fit. Studio stays responsive while the fit runs. When it finishes, the analyst sees what was fitted, how much evidence stands behind each number, which cells were too thin to trust, and what could not be fitted at all.

**Why this priority**: Fitting is the foundation. Without it, the team has no in-Studio path from real client history to simulation assumptions. It also delivers value on its own, because the fit report shows the analyst how the client's history differs from current assumptions.

**Independent Test**: Upload three consecutive synthetic annual snapshots, preview them, run a fit against a chosen scenario, and confirm that the results show the fit summary, the per-cell diagnostics with thin cells flagged, the unfittable groups, and the provenance.

**Acceptance Scenarios**:

1. **Given** a workspace with no history files, **When** the analyst uploads 2–5 consecutive annual snapshots, **Then** Studio lists each snapshot with its year, file name, row count, and content fingerprint, plus one combined fingerprint for the set, before any run is possible.
2. **Given** a valid snapshot set and a chosen base scenario, **When** the analyst reviews the pre-run summary and starts a fit, **Then** the request returns immediately, the job shows as queued and then running, and the rest of Studio stays usable.
3. **Given** a completed fit, **When** the analyst opens its results, **Then** they see:
   - snapshot years, linked-employee count, number of fitted parameters, and number of thin or prior-backed parameters
   - how the promotion rate was obtained (measured, estimated, or kept at the default)
   - unfittable groups and warnings
   - a per-cell table showing fitted value, prior, exposure, events, credibility, and basis, with thin cells highlighted
   - provenance: pack identifier, pack fingerprint, source fingerprint, base assumptions used
   - access to the full written fit report
4. **Given** a snapshot set with a missing year, a duplicated year, or fewer than two snapshots, **When** the analyst previews it, **Then** Studio shows a specific, human-readable reason and does not allow the run to start.

---

### User Story 2 - Backtest a fit against held-out years (Priority: P2)

Before trusting fitted parameters, the analyst wants proof that they predict reality. They choose "fit and backtest", hold out the last one or two years, and pick how many random seeds to run. Before launching, Studio shows which years are used for fitting, which are held out, and the boundary year. The job runs for several minutes. The analyst can watch its progress and cancel it. When it finishes, they get a scorecard that compares predicted and actual results for each metric and period, and gives an overall pass/warn/fail verdict.

**Why this priority**: Backtesting is what makes a fitted pack trustworthy enough to apply. It depends on the fit (P1), and it is the long-running, cancellable part of the feature.

**Independent Test**: Upload four consecutive snapshots, run fit and backtest with a one-year holdout and two seeds, and confirm the scorecard shows each metric and period with predicted, actual, % error, status, verdict, and seed spread. Separately, start a backtest, cancel it, and confirm it stops, is marked cancelled, and leaves no partial pack.

**Acceptance Scenarios**:

1. **Given** four consecutive snapshots and a holdout of 1, **When** the analyst previews, **Then** Studio shows three fit years, one holdout year, the boundary year, and the date the held-out simulation starts from.
2. **Given** three snapshots and a holdout of 2, **When** the analyst previews, **Then** Studio explains that only one year would remain for fitting (at least two are needed) and blocks the run.
3. **Given** a running backtest, **When** the analyst views it, **Then** they see which stage it is in and which seed of how many is running.
4. **Given** a running backtest, **When** the analyst cancels it, **Then** work stops within a short time, the job is marked cancelled, and no partial pack or scratch database is left behind.
5. **Given** a completed backtest, **When** the analyst opens it, **Then** they see:
   - a scorecard with predicted, actual, % error, and pass/warn/fail status for each metric and period
   - the overall verdict and its summary
   - the seed spread, or a note that none was computed for a single seed
   - any thresholds moved off their defaults
   - access to the full written scorecard
6. **Given** a backtest where one seed's simulation fails, **When** the job ends, **Then** it is marked failed and names the seed and simulation year that failed.
7. **Given** a backtest already running in a workspace, **When** the analyst tries to start another backtest in the same workspace, **Then** Studio refuses with a clear message instead of queueing silently.

---

### User Story 3 - Apply an accepted pack to a new scenario (Priority: P2)

The analyst is satisfied with a fit (ideally one that passed backtest). They want to run forward projections with it. From the job's results they choose "Apply to scenario" and pick a source scenario. Studio shows exactly which assumptions will change. It asks the analyst to explicitly acknowledge any thin cells, unfittable groups, or a missing, warning, or failing backtest. It then creates a new scenario. The source scenario is left untouched.

**Why this priority**: This closes the loop from history to projection. It is P2 because a fit and scorecard are useful for review on their own, but the feature is incomplete without it.

**Independent Test**: Apply a completed pack to a source scenario, then confirm:
- a new scenario exists whose assumptions reflect the pack and which records the pack's provenance
- the source scenario's configuration is byte-for-byte unchanged
- a simulation of the new scenario records the pack identifier and fingerprint in its run provenance

**Acceptance Scenarios**:

1. **Given** a completed fit, **When** the analyst starts applying it, **Then** Studio shows the assumption differences between the source scenario and the resulting scenario before anything is created.
2. **Given** a pack with thin cells, unfittable groups, or a backtest verdict of warn, fail, or none, **When** the analyst tries to apply it, **Then** Studio requires an explicit acknowledgement of each condition before the apply action is enabled.
3. **Given** the analyst confirms, **When** the scenario is created, **Then** it is new, it records which pack, job, source scenario, and backtest verdict it came from, and the source scenario is unchanged.
4. **Given** the history files, the pack, or the source scenario changed after the analyst reviewed them, **When** they confirm apply, **Then** Studio refuses, names which item went stale, and creates nothing.
5. **Given** the chosen name matches an existing scenario, **When** the analyst confirms, **Then** Studio refuses and suggests an available name.
6. **Given** a scenario created from a pack, **When** the analyst later edits one of its assumptions in Studio, **Then** the edit takes effect in subsequent runs instead of being overridden by the pack.

---

### User Story 4 - Revisit past fit and backtest jobs (Priority: P3)

An analyst returns days later, possibly after Studio was restarted, and wants to find last week's fit to compare it or apply it. The workspace keeps a list of recent fit and backtest jobs with their status, inputs, and verdicts. Old jobs are removed automatically so the workspace does not grow without limit.

**Why this priority**: Review often spans days, and packs are evidence. Jobs that vanish on restart would force expensive re-runs and would break the review-then-apply flow.

**Independent Test**: Complete a fit, restart the Studio service, confirm the job and its results are still listed and still applicable, then exceed the retention limit and confirm the oldest finished jobs are removed.

**Acceptance Scenarios**:

1. **Given** completed jobs in a workspace, **When** Studio restarts, **Then** the jobs, their results, and their packs are still listed and can still be applied.
2. **Given** a job that was running when Studio stopped, **When** Studio restarts, **Then** that job is shown as failed (interrupted), not as running forever.
3. **Given** more finished jobs than the retention limit, **When** a new job finishes, **Then** the oldest finished jobs and their artifacts are removed.

### Edge Cases

- History files contain more than one year in a single file, or two files carry the same year: the preview rejects them with the offending file named.
- History files change on disk after a job completed: the job's results remain viewable, but it is flagged stale and cannot be applied.
- The base scenario's assumptions change between fit and apply: apply is refused as stale. The analyst can re-fit or choose to apply against the scenario as it now stands, which requires a fresh review.
- A pack's files were modified after fitting (fingerprint mismatch): results show the mismatch and apply is refused.
- A fit where the promotion rate could not be fitted: results and the apply review both show that the default was kept.
- Every seed of a backtest fails: the job fails with the first failing seed and year. No scorecard or pack is produced.
- A job is cancelled after the pack was written but before the scorecard was written: the job is cancelled and all of its artifacts are removed. There is no half-state.
- Uploaded files are not census files (wrong columns or unreadable): the preview shows the specific validation error.
- The analyst deletes the base scenario after a fit: results remain viewable, and apply requires choosing a different, existing source scenario.
- The service stops mid-job: on restart the job shows as interrupted, and its scratch artifacts are eligible for cleanup.

## Requirements *(mandatory)*

### Functional Requirements

**History inputs and preview**

- **FR-001**: Analysts MUST be able to add 2–5 annual census snapshot files (the same file formats already accepted for census upload) to a workspace-scoped history set in Studio.
- **FR-002**: History inputs MUST be limited to files within the workspace. Studio MUST NOT read arbitrary server locations for this feature.
- **FR-003**: Before a run can start, the system MUST show:
  - for each snapshot: year, file name, row count, and content fingerprint
  - the combined source fingerprint
  - the as-of date each snapshot represents
  - for backtests: the fit years, holdout years, boundary year, and the date the held-out simulation starts from
- **FR-004**: The preview MUST reject, with a specific human-readable reason, sets that:
  - have year gaps or duplicate years
  - have fewer snapshots than the chosen mode needs (2 for fit; enough for the holdout plus 2 fit years for a backtest)
  - contain unreadable or non-conforming files

**Configuration and launch**

- **FR-005**: Analysts MUST choose a base scenario. Its effective assumptions (configuration and seed tables) MUST supply the priors for the fit.
- **FR-006**: Analysts MUST choose between fit only, and fit and backtest.
- **FR-007**: For backtests, analysts MUST be able to set the holdout (1 or 2 years) and the seed count (1–5, distinct values).
- **FR-008**: Advanced settings MUST expose the same fitting settings and backtest thresholds available today, pre-filled with the defaults. Any value moved off its default MUST be visibly marked in the configuration, the pre-run summary, and the results.
- **FR-009**: The system MUST present a pre-run summary of every input, hash, boundary, and setting. Launching MUST require the analyst to confirm it.
- **FR-010**: Launching a job MUST return immediately. The job MUST run in the background, and Studio MUST remain usable meanwhile.
- **FR-011**: At most one backtest MUST run per workspace at a time. A second request MUST be refused with an explanatory message.

**Job lifecycle**

- **FR-012**: Jobs MUST move through queued, running, and then exactly one terminal state: completed, failed, or cancelled.
- **FR-013**: Running jobs MUST report their stage (for example: loading history, fitting, simulating seed *i* of *N*, scoring) from structured progress information, not from parsed display text.
- **FR-014**: Analysts MUST be able to cancel a queued or running job. Cancellation MUST actually stop the work and remove that job's partial artifacts and scratch databases.
- **FR-015**: Failed jobs MUST carry a human-readable reason classified as one of:
  - invalid input or rejected history
  - output conflict
  - simulation failure, naming the failing seed and year
  - unexpected error, with internal details not exposed
- **FR-016**: Job records, results, and packs MUST persist across service restarts. Jobs interrupted by a restart MUST be reported as failed (interrupted).
- **FR-017**: Each job MUST run in its own isolated scratch area and databases. It MUST NOT read or write the shared development database or any scenario's simulation results.

**Results**

- **FR-018**: Completed fits MUST show:
  - summary: snapshot years, linked employees, fitted-parameter count, thin or prior-backed count, promotion basis, unfittable groups, and warnings
  - per-cell diagnostics: name/cell, fitted value, prior, exposure, events, credibility, and basis, with thin or prior-backed cells visibly distinguished
  - provenance: pack identifier, pack fingerprint, source fingerprint, base assumptions used, and fit date
- **FR-019**: Per-cell diagnostics MUST come from a machine-readable record produced alongside the pack. Adding that record MUST NOT change the pack's fingerprint or its existing contents.
- **FR-020**: Completed backtests MUST show, in addition to the fit results:
  - per metric and period: predicted, actual, % error, and pass/warn/fail status
  - the overall verdict and its summary
  - seed spread
  - thresholds moved off their defaults
  - the snapshots used, with their fit or holdout role
- **FR-021**: Analysts MUST be able to open the full written fit report and backtest scorecard from Studio.
- **FR-022**: A job's results MUST be flagged stale when its history files, pack files, or base scenario have changed since the job ran.

**Apply**

- **FR-023**: Applying a pack MUST always create a new scenario. It MUST NOT modify the source scenario.
- **FR-024**: Before creating anything, the apply flow MUST show the assumption differences between the source scenario and the resulting scenario.
- **FR-025**: Apply MUST require explicit acknowledgement when the pack has thin cells, has unfittable groups, has no backtest, or has a backtest verdict of warn or fail.
- **FR-026**: At confirmation, the system MUST re-verify that the pack, the history files, and the source scenario match what the analyst reviewed. On any mismatch it MUST refuse, name the stale item, and create nothing.
- **FR-027**: The new scenario MUST record its provenance: pack identifier and fingerprint, job, source scenario, source fingerprint, backtest verdict (if any), which acknowledgements were given, and when.
- **FR-028**: Simulations of the new scenario MUST use the pack's fitted assumptions, including the fitted tables, and MUST record the pack identifier and fingerprint in their run provenance.
- **FR-029**: Assumptions the analyst later edits in Studio on a pack-derived scenario MUST take precedence over the pack's values.
- **FR-030**: A name collision MUST be refused with a suggested available name.

**Retention and compatibility**

- **FR-031**: Finished jobs MUST be retained up to a configurable per-workspace limit, defaulting to 20. The oldest finished jobs beyond the limit MUST be removed together with their artifacts. Running jobs MUST never be removed.
- **FR-032**: The existing disk-cleanup tooling MUST also reclaim leftover scratch databases from fit and backtest jobs, including jobs interrupted by a restart.
- **FR-033**: The existing command-line fit and backtest workflows MUST continue to work with unchanged arguments, outputs, and exit behavior. The only permitted changes are additive: a new diagnostics record and optional structured progress output.

### Key Entities

- **History Set**: The workspace-scoped collection of annual census snapshots. Attributes: files, year per file, row counts, per-file fingerprints, combined source fingerprint.
- **Fit/Backtest Job**: One background run. Attributes: identifier, mode (fit or fit+backtest), status, stage and progress, created/finished times, inputs (history set fingerprint, base scenario and its fingerprint, settings including moved values), error classification and reason, and a stale flag.
- **Parameter Pack**: The job's output. Attributes: identifier, fingerprint, fit date, snapshot years and sources, fitted assumptions (configuration fragment and replacement tables), diagnostics record, written report.
- **Backtest Scorecard**: Attached to a pack when a backtest ran. Attributes: fit/holdout split, seeds, thresholds (moved values marked), per-metric comparisons, verdict and summary, provenance.
- **Pack-Derived Scenario**: A new scenario created by apply. It references its pack, job, and source scenario, carries the acknowledgements given, and keeps the pack's fitted tables so its runs can reproduce them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An analyst can go from uploading history to viewing fit results entirely in Studio, without the command line, in under 5 minutes for a typical 3-snapshot client history.
- **SC-002**: 100% of launch actions return control to the analyst within 2 seconds, regardless of how long the job runs.
- **SC-003**: A cancelled job stops doing work within 10 seconds and leaves zero artifacts or scratch databases behind.
- **SC-004**: In 100% of apply operations, the source scenario's configuration is unchanged, verified by comparing its content before and after apply.
- **SC-005**: 100% of stale-input apply attempts (changed history, changed pack, or changed source scenario) are refused, with the stale item named.
- **SC-006**: Every simulation run of a pack-derived scenario records the pack identifier and fingerprint in its run provenance.
- **SC-007**: Completed jobs and their packs are still viewable and applicable after a service restart. Workspace job storage never exceeds the configured retention limit of finished jobs.
- **SC-008**: Every invalid-history case listed in Edge Cases is rejected at preview with a specific reason, before any job runs.
- **SC-009**: The existing command-line fit and backtest test suites pass unchanged. A fit's pack fingerprint is identical with and without the new diagnostics record.

## Assumptions

- The analyst team uses Studio exclusively. The command-line workflows remain supported and serve as the execution engine behind Studio jobs, but command-line ergonomics do not constrain Studio design.
- Snapshot file formats, required columns, year detection, and the fitting and backtesting methods themselves are unchanged. This feature exposes existing capability; it does not change the statistics.
- Holdout limits (1–2 years), seed limits (1–5), and default thresholds match the existing backtest behavior.
- Studio's existing security model (API token, workspace scoping, loopback-by-default) applies. No new roles or permissions are introduced.
- A default retention limit of 20 finished jobs per workspace matches the retention of other Studio job types.
- A backtest may take several minutes. Progress granularity at the level of "stage / seed i of N" is sufficient.
- Delivery is sliced into three independently reviewable increments:
  1. background jobs, preview, diagnostics record, and retention
  2. apply to a new scenario
  3. the Studio page

## Dependencies

- Existing historical fitting and backtesting capability (the `planalign fit` / `planalign backtest` workflows).
- The existing census upload capability and workspace storage.
- The existing scenario provenance recording and scenario-diff capability used by other promote/apply flows.
- The existing run provenance record that already captures parameter-pack identity for command-line runs.
