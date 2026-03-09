# Feature Specification: Async Streaming for Simulation Progress Display

**Feature Branch**: `065-async-progress-streaming`
**Created**: 2026-03-09
**Status**: Draft
**Input**: User description: "Implement async streaming for simulation progress display (GitHub Issue #213)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-Time Progress Visibility During Simulation (Priority: P1)

A simulation operator runs a multi-year simulation and sees a live-updating progress display showing the current year, current stage, and overall completion percentage. The display updates smoothly without freezing, flickering, or corruption.

**Why this priority**: This is the core value proposition — operators currently see only a static message during simulation, with no visibility into progress or estimated completion time.

**Independent Test**: Can be fully tested by running `planalign simulate 2025-2027` and observing that the terminal shows a live progress bar advancing through years and stages, completing without display corruption.

**Acceptance Scenarios**:

1. **Given** a multi-year simulation is started, **When** each stage completes within a year, **Then** the progress display updates to show the current stage name and a progress bar advancing
2. **Given** a simulation spanning 3 years, **When** the first year completes, **Then** the year-level progress bar advances from 0/3 to 1/3 and an estimated remaining time appears
3. **Given** a simulation is running, **When** dbt subprocess produces stdout output, **Then** the Rich Live display continues rendering cleanly without corruption or freezing

---

### User Story 2 - Verbose Mode with Full dbt Output (Priority: P2)

A developer runs a simulation with `--verbose` flag and sees both the Rich progress display and detailed dbt subprocess output without one interfering with the other.

**Why this priority**: Developers need detailed output for debugging, but the current system forces a choice between progress display and dbt output visibility.

**Independent Test**: Can be tested by running `planalign simulate 2025 --verbose` and verifying that dbt model compilation/execution messages appear alongside the progress display without corruption.

**Acceptance Scenarios**:

1. **Given** a simulation is started with `--verbose`, **When** dbt runs models, **Then** dbt output lines appear in the terminal alongside the progress display without display corruption
2. **Given** a simulation is started with `--verbose`, **When** a dbt model fails, **Then** the error output is visible and not swallowed by the progress display

---

### User Story 3 - Stage-by-Stage Progress Awareness (Priority: P2)

An operator can see which specific pipeline stage is executing (INITIALIZATION, FOUNDATION, EVENT_GENERATION, STATE_ACCUMULATION, VALIDATION, REPORTING) and roughly how far through the current year's stages the simulation has progressed.

**Why this priority**: Knowing the current stage helps operators estimate how long the simulation will take and diagnose if it appears stuck.

**Independent Test**: Can be tested by running a single-year simulation and verifying that each of the 6 pipeline stages is displayed as it begins and completes.

**Acceptance Scenarios**:

1. **Given** a simulation year begins execution, **When** each stage starts, **Then** the progress display shows the stage name (e.g., "INITIALIZATION", "EVENT_GENERATION")
2. **Given** a simulation year is executing, **When** stages complete sequentially, **Then** a stage-level progress indicator advances (e.g., "Stage 3/6")

---

### User Story 4 - Cross-Platform Terminal Compatibility (Priority: P3)

The progress display renders correctly on Linux, macOS, and Windows terminals without platform-specific display issues.

**Why this priority**: The platform runs on analytics servers across different operating systems; display should work everywhere.

**Independent Test**: Can be tested by running a simulation on each target platform and verifying no rendering artifacts appear.

**Acceptance Scenarios**:

1. **Given** a simulation is run on a Linux terminal, **When** progress updates occur, **Then** the display renders without ANSI escape code artifacts
2. **Given** a simulation is run on Windows (ProactorEventLoop), **When** progress updates occur, **Then** the display renders without freezing or encoding errors

---

### Edge Cases

- What happens when the terminal window is resized during simulation? The display should gracefully reflow or continue without crashing.
- What happens when stdout is redirected to a file (non-interactive terminal)? The system should fall back to plain-text progress messages without Rich formatting.
- What happens when a dbt subprocess hangs or produces extremely large output? The progress display should remain responsive and not run out of memory.
- What happens when a simulation is interrupted with Ctrl+C? The progress display should clean up gracefully and restore the terminal state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display a live-updating progress bar during multi-year simulation execution showing overall year completion (e.g., "Year 2/3")
- **FR-002**: System MUST display the current pipeline stage name as each stage begins execution within a year
- **FR-003**: System MUST capture dbt subprocess stdout/stderr through a mechanism that does not interfere with the Rich Live display rendering
- **FR-004**: System MUST display an estimated remaining time after the first simulation year completes
- **FR-005**: System MUST support `--verbose` mode where detailed dbt output is visible alongside the progress display without corruption
- **FR-006**: System MUST restore terminal state cleanly on simulation completion, error, or interruption (Ctrl+C)
- **FR-007**: System MUST fall back to plain-text progress messages when running in a non-interactive terminal (e.g., stdout piped to a file)
- **FR-008**: System MUST wire the existing `progress_callback` parameter (currently set to `None`) to feed year/stage/event updates to the `LiveProgressTracker`
- **FR-009**: System MUST NOT introduce additional latency to the simulation pipeline — progress display overhead should be negligible

### Key Entities

- **LiveProgressTracker**: Existing Rich-based display component that manages Live rendering of progress bars and stage information
- **ProgressAwareOrchestrator**: Existing wrapper around PipelineOrchestrator that intercepts execution flow and feeds progress updates to a callback
- **EnhancedProgressMonitor**: Existing stdout interceptor that captures subprocess output and extracts progress signals
- **Pipeline Stage**: One of six sequential execution phases within each simulation year (INITIALIZATION through REPORTING)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can see real-time progress updates at least once per pipeline stage transition (minimum 6 updates per simulation year)
- **SC-002**: The terminal display remains visually clean (no corruption, flickering, or overlapping text) throughout 100% of simulation runs
- **SC-003**: Estimated remaining time is displayed after the first year completes and is accurate within 30% of actual remaining time
- **SC-004**: Verbose mode shows both progress indicators and dbt output without any lost or garbled output lines
- **SC-005**: Simulation performance is not degraded — total simulation time increases by less than 2% compared to the current non-progress-display mode
- **SC-006**: Terminal state is fully restored after simulation completes, errors, or is interrupted via Ctrl+C in 100% of cases

## Assumptions

- The existing `LiveProgressTracker` class (already implemented in simulate.py) provides the correct Rich display logic and only needs to be wired up with a working output capture mechanism
- The existing `ProgressAwareOrchestrator` and `EnhancedProgressMonitor` classes provide the correct interception logic and primarily need the stdout conflict to be resolved
- Rich's `Live` display context manager handles terminal cleanup on exceptions when used correctly
- The six pipeline stages (INITIALIZATION, FOUNDATION, EVENT_GENERATION, STATE_ACCUMULATION, VALIDATION, REPORTING) are the complete set of stages to track
- dbt subprocess output volume is bounded and will not cause memory issues when buffered during capture

## Scope Boundaries

**In scope**:
- Enabling the existing progress callback wiring
- Implementing dbt stdout/stderr capture that coexists with Rich Live display
- Cross-platform terminal compatibility
- Non-interactive terminal fallback

**Out of scope**:
- Changing the pipeline stage definitions or execution order
- Adding new progress metrics beyond year/stage tracking
- Web-based progress display (PlanAlign Studio already has WebSocket telemetry)
- Persistent progress logging to files (beyond what `--verbose` already provides)
