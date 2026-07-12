# Feature Specification: Config Drift Detection

**Feature Branch**: `109-config-drift-detection`
**Created**: 2026-07-12
**Status**: Draft
**Input**: User description: "Config drift detection. The engine promises reproducibility, but nothing (that I know of) stops you from re-running against a DB built with a different config and reading mixed-generation results. Stamping a config hash + seed into a metadata table at run start and warning on mismatch would turn a silent contamination class into a loud one — consistent with your \"warnings over migrations\" preference."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Warn When Re-Running Against a Database Built with a Different Configuration (Priority: P1)

An analyst runs a multi-year simulation into a database, later edits the configuration (e.g., changes the growth rate, a match formula, or the random seed), and re-runs against the same database. Today the second run silently mixes generations: years or tables produced under the old configuration coexist with those produced under the new one, and downstream reads return contaminated results with no indication anything is wrong. With this feature, the engine records the effective configuration fingerprint and random seed at the start of every run, and at the start of any subsequent run against the same database it compares the current configuration against what the database was built with. On mismatch, it emits a prominent, unmissable warning that names what changed before proceeding.

**Why this priority**: This is the core value of the feature — it converts a silent data-contamination class into a loud one. Everything else builds on the stamp-and-compare mechanism.

**Independent Test**: Run a simulation into a fresh isolated database, change one configuration value, re-run against the same database, and confirm a clear drift warning is shown identifying the changed value. Re-run with an unchanged configuration and confirm no warning appears.

**Acceptance Scenarios**:

1. **Given** a database previously built by a run with configuration C1, **When** a new run starts against that database with configuration C2 that differs from C1, **Then** the engine displays a prominent warning before simulation work begins, stating that the database was built with a different configuration and identifying the mismatch (at minimum: config changed, seed changed, or both).
2. **Given** a database previously built by a run with configuration C1, **When** a new run starts against that database with an identical configuration and seed, **Then** no drift warning is shown and the run proceeds normally.
3. **Given** a brand-new (empty) database, **When** a run starts, **Then** no drift warning is shown and the run's configuration fingerprint and seed are recorded so future runs can be compared.
4. **Given** a database built before this feature existed (no recorded fingerprint), **When** a run starts against it, **Then** the engine does not fail; it notes that no prior run record exists to compare against, and records the current run's fingerprint for future comparisons.
5. **Given** a drift warning has been emitted, **When** the run continues, **Then** the run completes normally — detection warns, it never blocks by default.

---

### User Story 2 - Seed Changes Are Called Out Distinctly (Priority: P2)

A user re-runs a scenario with the same substantive configuration but a different random seed, expecting to compare stochastic variation. Because the reproducibility promise hinges on the seed, a seed change against an existing database deserves its own explicit call-out — mixed-seed results in one database are just as contaminated as mixed-config results, but the user may not think of the seed as "config."

**Why this priority**: The seed is the most commonly tweaked value and the easiest contamination source to overlook; naming it separately makes the warning actionable.

**Independent Test**: Build a database with seed A, re-run with seed B and an otherwise identical configuration, and confirm the warning specifically states that the random seed differs (old vs. new value).

**Acceptance Scenarios**:

1. **Given** a database built with seed A, **When** a run starts with seed B and otherwise identical configuration, **Then** the warning explicitly says the random seed changed and shows both values.
2. **Given** a database built with seed A and configuration C1, **When** a run starts with seed B and configuration C2, **Then** the warning reports both the seed change and the configuration change.

---

### User Story 3 - Run History Is Auditable After the Fact (Priority: P3)

A user (or a reviewing colleague) opens a database of results days later and wants to know what produced it: which configuration fingerprint, which seed, and when each run happened. The recorded run metadata makes each database self-describing, so mixed-generation state can be diagnosed after the fact even if the warning at run time was missed or the terminal output is gone.

**Why this priority**: Valuable for audit and debugging, but the run-time warning (P1) already prevents most contamination; this extends the value to retrospective inspection.

**Independent Test**: Run twice against the same database with different configurations, then inspect the database's run metadata and confirm both runs appear with distinct fingerprints, seeds, and timestamps.

**Acceptance Scenarios**:

1. **Given** a database that has had one or more runs, **When** a user inspects the run metadata, **Then** each run appears with at least: configuration fingerprint, random seed, run timestamp, and the simulated year range.
2. **Given** a database with runs under two different configurations, **When** the metadata is inspected, **Then** the two generations are distinguishable (different fingerprints on different run records).

---

### Edge Cases

- **Legacy database with results but no run record**: must not error; treated as "unknown provenance" — informational note, current run recorded (US1 scenario 4).
- **Configuration differences that don't affect results** (e.g., purely cosmetic/reporting settings): the fingerprint SHOULD cover the settings that influence simulation output; if the fingerprint covers more than that, occasional false-positive warnings are acceptable — false negatives are not.
- **Interrupted run**: a run that stamps its metadata and then fails partway must still leave a record, so the next run can warn that the database may be in a partial state from a run with a given fingerprint.
- **Isolated per-scenario databases** (batch/Studio): each scenario database carries its own run records; comparison is always against the same database being written, never across databases.
- **Intentional drift**: a user who deliberately changes config and wants to overwrite must not be blocked — the warning states the recommended remedies (start from a fresh/isolated database or perform a clean rerun) but the run proceeds.
- **Metadata table absent or unreadable**: detection degrades gracefully to a note; it never prevents the simulation from running.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The engine MUST record, at the start of every simulation run, a fingerprint of the effective configuration, the random seed, a timestamp, and the simulated year range, persisted inside the target database itself.
- **FR-002**: At the start of every run against a database containing prior run records, the engine MUST compare the current configuration fingerprint and seed against the most recent recorded run.
- **FR-003**: On mismatch, the engine MUST emit a prominent warning before simulation work begins, stating that the database was built under a different configuration and/or seed and that existing results may be mixed-generation.
- **FR-004**: The warning MUST distinguish a seed change from a configuration change, and when the seed changed MUST show the prior and current seed values.
- **FR-005**: Drift detection MUST be non-blocking by default: after warning, the run proceeds. Detection failures (missing/corrupt metadata) MUST also never block a run.
- **FR-006**: A database with no prior run record (new or legacy) MUST NOT trigger a drift warning; the engine records the current run so future comparisons are possible.
- **FR-007**: The configuration fingerprint MUST be deterministic: identical effective configurations produce identical fingerprints across runs and machines, and any change to a result-affecting setting produces a different fingerprint.
- **FR-008**: Run records MUST be append-only — each run adds a record; prior records are never overwritten — so the database retains an auditable run history.
- **FR-009**: Drift detection MUST apply to all run entry points that write simulation results into a database (single/multi-year simulation, batch scenario runs, and calibration runs), comparing each target database only against its own history.
- **FR-010**: The warning MUST include actionable guidance: how to obtain clean results (fresh or isolated database, or a clean rerun) if the drift was unintentional.

### Key Entities

- **Run Record**: One row per simulation run, stored in the target database: configuration fingerprint, random seed, run timestamp, simulated year range, and run type (simulate / batch scenario / calibration). Append-only.
- **Configuration Fingerprint**: A compact, deterministic digest of the effective, result-affecting simulation configuration, used for equality comparison between the current run and prior runs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of re-runs against a database whose last run used a different result-affecting configuration or seed produce a visible drift warning before any results are written.
- **SC-002**: 0 false-negative outcomes in verification: no scenario exists where a result-affecting configuration or seed change against an existing database proceeds silently.
- **SC-003**: Re-running with an unchanged configuration and seed produces no drift warning (no warning fatigue on legitimate reproducible re-runs).
- **SC-004**: Runs against databases created before this feature complete without error, and their next run becomes comparable (a run record exists afterward).
- **SC-005**: A user inspecting any database produced after this feature can answer "what configuration and seed produced this?" from the database alone, without terminal logs.
- **SC-006**: Detection adds no perceptible delay to run startup (well under one second of overhead).

## Assumptions

- **Non-blocking by default**: consistent with the project's "warnings over migrations / warnings over blocking" preference, drift warns loudly but never stops a run. A strict/fail-on-drift mode is out of scope for this spec and can be layered later if wanted.
- **Comparison target**: drift is evaluated against the *most recent* prior run record (the state the database was last written under), not against every historical record; the full history remains available for audit.
- **Fingerprint scope**: the fingerprint covers the effective simulation configuration that influences results (including the random seed, tracked separately for messaging). Erring toward including too much (occasional false positives) is preferred over missing a result-affecting setting (false negatives).
- **Scope of entry points**: all writers of simulation results (simulate, batch, calibration) participate; read-only commands (status, analyze, health) do not stamp records.
- **No retroactive backfill**: databases created before this feature simply lack history until their next run; no migration or backfill is performed.
