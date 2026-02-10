# Tasks: Gitignore dbt Generated Artifacts

**Input**: Design documents from `/specs/042-gitignore-dbt-artifacts/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md

**Tests**: Not requested — verification is via git commands in the final phase.

**Organization**: Tasks are grouped by user story. Since all changes target `.gitignore` (a single file), tasks within story phases are sequential, not parallel.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: Repository root `.gitignore`
- No `src/`, `tests/`, or other code directories involved

---

## Phase 1: User Story 1 - Clean Diffs Without Generated Artifacts (Priority: P1) MVP

**Goal**: Replace the specific `dbt/target/` entry with a glob pattern `dbt/target*/` that covers all current and future dbt target directories, and add an explicit ignore for the generated performance JSON file.

**Independent Test**: Run `git check-ignore dbt/target/manifest.json dbt/target_perf_test/manifest.json dbt/target_custom/anything.json` — all three paths should be reported as ignored.

### Implementation for User Story 1

- [x] T001 [US1] Replace `dbt/target/` with `dbt/target*/` in the "# dbt specific" section of .gitignore (line 36)
- [x] T002 [US1] Add `dbt/year_processor_performance.json` to the "# dbt specific" section of .gitignore (after `dbt/macros/packages/`)

**Checkpoint**: `git check-ignore dbt/target/x dbt/target_perf_test/x dbt/target_foo/x` all return matches; `git check-ignore dbt/year_processor_performance.json` returns a match.

---

## Phase 2: User Story 2 - Remove Previously Tracked Generated Files (Priority: P2)

**Goal**: Remove `dbt/year_processor_performance.json` from git tracking without deleting the local file.

**Independent Test**: `git ls-files -- dbt/year_processor_performance.json` returns empty; `ls dbt/year_processor_performance.json` confirms file still exists on disk.

### Implementation for User Story 2

- [x] T003 [US2] Run `git rm --cached dbt/year_processor_performance.json` to remove tracked artifact from index

**Checkpoint**: `git ls-files -- dbt/year_processor_performance.json` returns no output. `git status` shows the file as deleted from index. Local file remains on disk.

---

## Phase 3: User Story 3 - Consolidated and Maintainable Ignore Rules (Priority: P3)

**Goal**: Remove misplaced dbt/DuckDB entries from the Cursor section and relocate `simulation.duckdb.zip` to the DuckDB section where it logically belongs.

**Independent Test**: `grep -n 'dbt/target' .gitignore` returns exactly one line (in the "# dbt specific" section). `grep -n 'simulation.duckdb.zip' .gitignore` returns exactly one line (in the "# DuckDB" section).

### Implementation for User Story 3

- [x] T004 [US3] Remove `dbt/target_perf_test/` from line 247 of .gitignore (Cursor section — now covered by glob in dbt section)
- [x] T005 [US3] Remove `simulation.duckdb.zip` from line 248 of .gitignore (Cursor section)
- [x] T006 [US3] Add `simulation.duckdb.zip` to the "# DuckDB" section of .gitignore (after `simulation.duckdb.wal`, before `*.duckdb`)

**Checkpoint**: All dbt-related patterns are in one section. `simulation.duckdb.zip` is in the DuckDB section. No stray entries remain in the Cursor section.

---

## Phase 4: Verification

**Purpose**: Confirm all changes work correctly end-to-end

- [x] T007 Verify glob pattern covers all target directories via `git check-ignore dbt/target/manifest.json dbt/target_perf_test/manifest.json dbt/target_custom/anything.json`
- [x] T008 Verify tracked artifact removed via `git ls-files -- dbt/year_processor_performance.json` (expect empty)
- [x] T009 Verify existing ignore rules preserved via `git check-ignore dbt/logs/dbt.log dbt/dbt_packages/some_package` (expect both matched)
- [x] T010 Verify no scattered dbt target patterns via `grep -n 'dbt/target' .gitignore` (expect exactly one line)
- [x] T011 Verify local file preserved via `ls -la dbt/year_processor_performance.json` (expect file exists)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (US1)**: No dependencies — can start immediately
- **Phase 2 (US2)**: Depends on T002 (ignore rule must exist before removing from index, otherwise `git status` would show it as untracked)
- **Phase 3 (US3)**: Depends on T001 (glob must be in place before removing the specific `dbt/target_perf_test/` entry)
- **Phase 4 (Verification)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: No dependencies — establishes the glob pattern
- **US2 (P2)**: Depends on US1 (T002 adds the ignore rule for the tracked file)
- **US3 (P3)**: Depends on US1 (T001 replaces the glob, making the stray entry redundant)

### Within Each User Story

- US1: T001 then T002 (both edit same file section, sequential)
- US2: T003 only (single git command)
- US3: T004, T005, T006 sequential (edits to same file, line numbers shift)

### Parallel Opportunities

- Limited parallelism due to single-file editing. However:
  - T001 + T003 could theoretically run in parallel (different operations: file edit vs git command) but T003 depends on T002
  - The feature is small enough that sequential execution is the pragmatic choice

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: US1 (glob pattern + performance json ignore)
2. **STOP and VALIDATE**: `git check-ignore` confirms all target dirs are covered
3. This alone solves the original issue (noisy diffs from target artifacts)

### Incremental Delivery

1. US1 → Glob pattern in place → Core problem solved (MVP)
2. US2 → Tracked artifact removed → No more noisy diffs from performance json
3. US3 → `.gitignore` consolidated → Maintainable going forward
4. Verification → All success criteria confirmed

---

## Notes

- All tasks modify a single file (`.gitignore`) except T003 which runs a git command
- Total: 11 tasks (6 implementation + 5 verification)
- Estimated scope: Very small — can be completed in a single session
- Line numbers referenced are from the current `.gitignore` as of 2026-02-10; edits in earlier tasks will shift line numbers for later tasks, so match on content rather than line number
