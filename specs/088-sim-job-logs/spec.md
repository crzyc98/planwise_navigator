# Feature Specification: Simulation Job Log Capture

**Feature Branch**: `088-sim-job-logs`
**Created**: 2026-06-03
**Status**: Draft
**Input**: User description: "i deployed this on a unix server and my analysts aren't able to monitor the log files, could you have the log files saved to the job when it is simulation is run?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Logs for a Completed Simulation Run (Priority: P1)

An analyst needs to review what happened during a simulation that has already finished. They open the web interface, navigate to the simulation run record, and can read the full log output from that run — without needing filesystem access or SSH credentials on the server.

**Why this priority**: This is the core ask. Analysts are currently blocked from any log access on the deployed server. Providing read-only log access through the web interface removes that blocker entirely and is the minimum viable deliverable.

**Independent Test**: Navigate to any completed simulation run in PlanAlign Studio, open its detail view, and confirm the full log output is displayed. Delivers immediate value with no further functionality needed.

**Acceptance Scenarios**:

1. **Given** a simulation run has completed successfully, **When** an analyst opens that run's detail view, **Then** the complete log output is visible and readable in the interface.
2. **Given** a simulation run has failed, **When** an analyst opens that run's detail view, **Then** the log output up to and including the point of failure is visible, along with any error details.
3. **Given** a simulation run record exists, **When** an analyst clicks "Download Logs," **Then** the full log file is downloaded to their local machine as a plain text file.

---

### User Story 2 - Monitor a Running Simulation in Real Time (Priority: P2)

An analyst launches a simulation and wants to watch its progress as it runs, without leaving the web interface or polling a server log file via SSH.

**Why this priority**: Important for long-running simulations where analysts need early warning of issues, but completed-run access (US1) already resolves the stated blocker. Real-time monitoring adds proactive visibility.

**Independent Test**: Start a simulation through PlanAlign Studio and confirm log lines appear in the interface as the simulation progresses — each new log entry appears within a few seconds of being produced.

**Acceptance Scenarios**:

1. **Given** a simulation is actively running, **When** an analyst opens the run's detail view, **Then** log lines appear incrementally as the simulation produces them.
2. **Given** a simulation is streaming logs, **When** the simulation completes, **Then** the log view updates to show the final status and stops streaming.
3. **Given** a simulation is streaming logs, **When** an analyst navigates away and returns, **Then** they see all previously captured log lines plus any new ones produced since they left.

---

### User Story 3 - Search and Filter Logs Within a Run (Priority: P3)

An analyst investigating a specific issue within a long simulation run wants to search the log output rather than scrolling through thousands of lines.

**Why this priority**: Useful for large multi-year simulations producing verbose output, but not required for the core access problem. Can be delivered as a follow-on improvement.

**Independent Test**: Open a completed run with a large log and use the search/filter controls to find a known log message — confirm matching lines are highlighted or the view is filtered.

**Acceptance Scenarios**:

1. **Given** a simulation run's log is displayed, **When** an analyst types a search keyword, **Then** matching log lines are highlighted and the view scrolls to the first match.
2. **Given** a simulation run's log is displayed, **When** an analyst filters by severity (error, warning, info), **Then** only log lines at that severity level are visible.

---

### Edge Cases

- What happens to logs if the server crashes mid-simulation — are partial logs still accessible?
- How does the system handle very large log files (e.g., multi-year simulations producing hundreds of MB of output)?
- What happens if an analyst opens the log view for a run that is queued but has not started yet?
- How are logs handled for batch scenario runs — is there a log per scenario or a single aggregated log?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST capture all log output produced during a simulation run and associate it permanently with that run's record.
- **FR-002**: Analysts MUST be able to view the complete log output for any simulation run through the web interface without requiring server filesystem or SSH access.
- **FR-003**: Each log entry MUST include a timestamp and severity level (info, warning, error).
- **FR-004**: The system MUST preserve logs for failed simulation runs, including all output produced up to the point of failure and the failure details.
- **FR-005**: Analysts MUST be able to download the full log output for any completed run as a plain text file.
- **FR-006**: Log records MUST be associated with the specific simulation run (scenario name, year range, and run start time) so analysts can identify which run produced which logs.
- **FR-007**: During an active simulation, the web interface MUST display log output as it is produced without requiring a manual page refresh.
- **FR-008**: The system MUST retain simulation run logs for at least 90 days after run completion.
- **FR-009**: For batch scenario runs, the system MUST maintain separate log records per scenario so analysts can isolate issues to a specific scenario.

### Key Entities

- **Simulation Run**: A single execution of the simulation engine for a given scenario and year range; has a unique identifier, start/end timestamps, status (running/completed/failed), and an associated ordered log archive.
- **Log Entry**: A single line of log output associated with a run, with a timestamp, severity level (info/warning/error), and the message text.
- **Log Archive**: The complete ordered collection of log entries for a simulation run, downloadable as a plain text file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulation runs (successful, failed, and interrupted) have accessible log output viewable through the web interface within 30 seconds of the run completing.
- **SC-002**: Analysts can access full log output for any completed run without requiring server credentials or filesystem access.
- **SC-003**: Log entries for an active simulation appear in the web interface within 5 seconds of being produced by the simulation engine.
- **SC-004**: Analysts can download the complete log file for any run in under 10 seconds regardless of log size.
- **SC-005**: Zero loss of log data for any simulation run, including runs that terminate abnormally.
- **SC-006**: Analysts report being able to diagnose simulation failures without escalating to a system administrator for log access.

## Assumptions

- Analysts have access to PlanAlign Studio (the web interface) from their workstations; the access problem is specifically about server filesystem/SSH access to raw log files on the deployed Unix server.
- Batch scenario runs will expose per-scenario logs individually, each associated with its own run record.
- Log retention of 90 days is sufficient; if compliance requirements mandate longer retention, this should be revisited.
- Very large log files (over 50 MB) will be paginated or lazy-loaded in the web viewer for performance, but remain fully downloadable as a single file.
- Real-time streaming (US2) assumes the web interface remains open; push notifications for analysts not watching the interface are out of scope.

## Out of Scope

- Email or push notifications when a simulation completes or fails.
- Structured log analytics, dashboards, or aggregated metrics derived from log data.
- Log shipping to external monitoring platforms (e.g., Splunk, Datadog, ELK).
- Log access controls beyond what is already enforced by existing workspace membership.
- Cross-run log search (searching logs across multiple simulation runs simultaneously).
