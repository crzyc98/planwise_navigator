# Feature Specification: Gitignore dbt Generated Artifacts

**Feature Branch**: `042-gitignore-dbt-artifacts`
**Created**: 2026-02-10
**Status**: Draft
**Input**: User description: "dbt/target_perf_test/manifest.json appears to be a generated dbt artifact and is not covered by .gitignore. This can bloat the repo and cause noisy diffs."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean Diffs Without Generated Artifacts (Priority: P1)

A developer runs a dbt build or performance test locally, which produces generated artifacts (JSON manifests, pickled graphs, message pack files, performance logs). When they run `git status` afterward, these generated files do not appear as untracked or modified. Pull request diffs remain focused on intentional code changes, without noise from large auto-generated files.

**Why this priority**: Generated artifacts in diffs waste reviewer time, inflate repo size, and can mask real changes. Preventing this is the core value of the feature.

**Independent Test**: Can be fully tested by running `dbt build` locally, then verifying `git status` shows no generated dbt artifacts as untracked.

**Acceptance Scenarios**:

1. **Given** a clean working tree, **When** a developer runs `dbt build --threads 1` from the `dbt/` directory, **Then** `git status` shows no new untracked files in `dbt/target/` or any `dbt/target*/` directory.
2. **Given** a clean working tree, **When** a developer runs any dbt command that produces artifacts in a `target`-prefixed directory, **Then** those artifacts are ignored by git.
3. **Given** the repository `.gitignore`, **When** a new `dbt/target_<name>/` directory is created by a custom dbt profile, **Then** it is automatically ignored without requiring a `.gitignore` update.

---

### User Story 2 - Remove Previously Tracked Generated Files (Priority: P2)

A developer notices that a generated file (`dbt/year_processor_performance.json`) is currently tracked in the repository. After this cleanup, the file is removed from git tracking but remains on disk for local use. Future changes to this file will not produce diffs.

**Why this priority**: Removing already-tracked artifacts prevents future noisy diffs and signals to the team that generated files should not be committed.

**Independent Test**: Can be tested by verifying `git ls-files` no longer lists the generated artifact, while the file still exists locally.

**Acceptance Scenarios**:

1. **Given** `dbt/year_processor_performance.json` is currently tracked, **When** the cleanup is applied, **Then** the file is removed from git tracking.
2. **Given** the file is removed from tracking, **When** a developer regenerates the performance file locally, **Then** `git status` does not show it as modified or untracked.

---

### User Story 3 - Consolidated and Maintainable Ignore Rules (Priority: P3)

A developer reviewing `.gitignore` can easily understand which dbt-generated directories and files are excluded. Related ignore patterns are grouped together rather than scattered across different sections of the file, making it easy to audit and maintain.

**Why this priority**: A well-organized `.gitignore` reduces the chance that new generated artifacts slip through in the future and makes the rules easier to audit.

**Independent Test**: Can be tested by reviewing `.gitignore` and confirming all dbt artifact patterns are in a single, clearly labeled section.

**Acceptance Scenarios**:

1. **Given** the current `.gitignore` has dbt target patterns on lines 36 and 247, **When** the consolidation is applied, **Then** all dbt artifact ignore patterns are grouped in a single section.
2. **Given** the consolidated `.gitignore`, **When** a new developer reads the file, **Then** they can identify all dbt-related ignore rules without searching the entire file.

---

### Edge Cases

- What happens if a developer has local uncommitted changes to `dbt/year_processor_performance.json`? The `git rm --cached` operation only affects the index, not the working copy; the local file is preserved.
- What happens if a new dbt profile creates a `dbt/target_custom/` directory? The glob pattern `dbt/target*/` covers any directory starting with `target` under `dbt/`.
- What happens if someone intentionally wants to track a file inside `dbt/target*/`? They can use a negation pattern (e.g., `!dbt/target_perf_test/important_file.txt`) or force-add with `git add -f`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `.gitignore` MUST use a glob pattern (`dbt/target*/`) that covers all current and future dbt target directories under the `dbt/` path.
- **FR-002**: The `.gitignore` MUST ignore `dbt/year_processor_performance.json` (and similar generated performance/benchmark files).
- **FR-003**: All dbt-related ignore patterns MUST be consolidated in a single, clearly labeled section of `.gitignore`.
- **FR-004**: The duplicate/scattered dbt target patterns (currently on lines 36 and 247) MUST be merged into the consolidated section.
- **FR-005**: Any currently tracked generated artifacts MUST be removed from git tracking (via `git rm --cached`) without deleting local copies.
- **FR-006**: The `.gitignore` MUST continue to ignore `dbt/logs/` and `dbt/dbt_packages/` (existing rules preserved during consolidation).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a full `dbt build`, `git status` reports zero untracked files in any `dbt/target*/` directory.
- **SC-002**: `git ls-files` returns zero results for `dbt/year_processor_performance.json` and other generated dbt artifacts.
- **SC-003**: All dbt-related ignore patterns in `.gitignore` are located within a single contiguous section (no scattered duplicates).
- **SC-004**: The repository size does not increase from generated dbt artifacts on any future commit.

## Assumptions

- The `dbt/target_perf_test/` directory was never committed to git history (confirmed: it is already in `.gitignore` at line 247 and has no git history). The primary issue is scattered ignore patterns and one tracked generated file.
- `dbt/year_processor_performance.json` (140 bytes, auto-generated) is safe to remove from tracking — it is regenerated on demand and holds no source-of-truth data.
- The glob pattern `dbt/target*/` is preferable to listing individual `target_*` directories, as it future-proofs against new dbt profiles or test configurations.
