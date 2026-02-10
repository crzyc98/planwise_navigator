# Implementation Plan: Gitignore dbt Generated Artifacts

**Branch**: `042-gitignore-dbt-artifacts` | **Date**: 2026-02-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/042-gitignore-dbt-artifacts/spec.md`

## Summary

Consolidate scattered dbt artifact ignore patterns in `.gitignore`, replace individual target directory entries with a glob pattern (`dbt/target*/`), remove one tracked generated file from git index, and relocate misplaced entries to their logical sections. This is a config-only change — no source code, APIs, or data models involved.

## Technical Context

**Language/Version**: N/A (configuration files only)
**Primary Dependencies**: Git (`.gitignore` syntax)
**Storage**: N/A
**Testing**: Manual verification via `git status`, `git ls-files`, `git check-ignore`
**Target Platform**: All developer environments (macOS, Linux)
**Project Type**: Single project — configuration change
**Performance Goals**: N/A
**Constraints**: Must not break existing ignore rules; must preserve local files on disk
**Scale/Scope**: 1 file edited (`.gitignore`), 1 file untracked (`git rm --cached`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applicable? | Status | Notes |
|-----------|-------------|--------|-------|
| I. Event Sourcing & Immutability | No | PASS | No events or data affected |
| II. Modular Architecture | No | PASS | No code modules affected |
| III. Test-First Development | No | PASS | Config-only change; verified via git commands |
| IV. Enterprise Transparency | Yes | PASS | Improves repo hygiene and audit clarity |
| V. Type-Safe Configuration | No | PASS | No Pydantic or dbt config changes |
| VI. Performance & Scalability | No | PASS | No runtime performance impact |

All gates pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/042-gitignore-dbt-artifacts/
├── plan.md              # This file
├── research.md          # Phase 0 output (completed)
├── spec.md              # Feature specification
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
.gitignore               # Only file modified
dbt/year_processor_performance.json  # Removed from git tracking (kept on disk)
```

**Structure Decision**: No new directories or files created. This feature modifies a single existing configuration file and removes one file from the git index.

## Implementation Details

### Change 1: Consolidate dbt Section (FR-001, FR-003, FR-004, FR-006)

**Current state** (lines 35-44):
```gitignore
# dbt specific
dbt/target/
dbt/dbt_packages/
dbt/logs/
dbt/.user_*
dbt/.dbt/
dbt/macros/packages/
```

**Target state**:
```gitignore
# dbt specific
dbt/target*/
dbt/dbt_packages/
dbt/logs/
dbt/.user_*
dbt/.dbt/
dbt/macros/packages/
dbt/year_processor_performance.json
```

Changes:
- `dbt/target/` → `dbt/target*/` (glob covers `target/`, `target_perf_test/`, and future dirs)
- Add `dbt/year_processor_performance.json` to this section

### Change 2: Remove Stray Entries from Cursor Section (FR-004)

**Current state** (lines 241-248):
```gitignore
# Cursor
...
.cursorindexingignore
dbt/target_perf_test/
simulation.duckdb.zip
```

**Target state** (lines 241-246):
```gitignore
# Cursor
...
.cursorindexingignore
```

Changes:
- Remove `dbt/target_perf_test/` (now covered by `dbt/target*/` glob in dbt section)
- Move `simulation.duckdb.zip` to the DuckDB section

### Change 3: Add simulation.duckdb.zip to DuckDB Section

**Current state** (lines 6-10):
```gitignore
# DuckDB
simulation.duckdb
simulation.duckdb.wal
*.duckdb
*.duckdb.wal
```

**Target state**:
```gitignore
# DuckDB
simulation.duckdb
simulation.duckdb.wal
simulation.duckdb.zip
*.duckdb
*.duckdb.wal
```

### Change 4: Remove Tracked Artifact (FR-002, FR-005)

```bash
git rm --cached dbt/year_processor_performance.json
```

This removes the file from git tracking without deleting the local copy.

## Verification Plan

After implementation, verify with these commands:

```bash
# 1. Confirm no tracked generated artifacts
git ls-files -- 'dbt/year_processor_performance.json'
# Expected: no output

# 2. Confirm glob pattern works for all target dirs
git check-ignore dbt/target/manifest.json
git check-ignore dbt/target_perf_test/manifest.json
git check-ignore dbt/target_custom/anything.json
# Expected: all three print the matched path

# 3. Confirm existing patterns still work
git check-ignore dbt/logs/dbt.log
git check-ignore dbt/dbt_packages/some_package
# Expected: both print the matched path

# 4. Confirm no scattered dbt patterns remain
grep -n 'dbt/target' .gitignore
# Expected: only one line in the "# dbt specific" section

# 5. Confirm local file preserved
ls -la dbt/year_processor_performance.json
# Expected: file exists on disk
```

## Phase 1 Artifacts: Not Applicable

This feature involves no data models, API contracts, or quickstart guides. The following Phase 1 artifacts are intentionally omitted:

- **data-model.md**: No entities or data changes
- **contracts/**: No API endpoints or interfaces
- **quickstart.md**: No development setup required; changes are self-explanatory
