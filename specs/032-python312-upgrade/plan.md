# Implementation Plan: Python 3.12 Upgrade

**Branch**: `032-python312-upgrade` | **Date**: 2026-02-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/032-python312-upgrade/spec.md`

## Summary

Update the Fidelity PlanAlign Engine project to officially support and recommend Python 3.12.x while maintaining backward compatibility with Python 3.11.x. This involves updating version constraints in `pyproject.toml`, verifying all dependency compatibility, and updating documentation (README.md, CLAUDE.md) to reflect Python 3.12 as the recommended version.

## Technical Context

**Language/Version**: Python 3.12.x (primary), Python 3.11.x (backward compatible)
**Primary Dependencies**: duckdb==1.0.0, dbt-core==1.8.8, dbt-duckdb==1.8.1, pydantic==2.7.4, FastAPI, pytest
**Storage**: DuckDB (dbt/simulation.duckdb) - no changes required
**Testing**: pytest (256+ tests, 87 fast tests)
**Target Platform**: Linux server (on-premises deployment), macOS/Windows for development
**Project Type**: Single project with CLI, API, and orchestrator components
**Performance Goals**: Installation <5 minutes, all tests pass, no deprecation warnings
**Constraints**: Maintain backward compatibility with Python 3.11
**Scale/Scope**: Configuration and documentation changes only; no new features

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ N/A | No event store changes |
| II. Modular Architecture | ✅ Pass | Documentation changes only; no code structure impact |
| III. Test-First Development | ✅ Pass | Existing tests validate Python 3.12 compatibility |
| IV. Enterprise Transparency | ✅ Pass | Version changes documented in CHANGELOG |
| V. Type-Safe Configuration | ✅ Pass | pyproject.toml uses standard PEP 440 version specifiers |
| VI. Performance & Scalability | ✅ Pass | No performance regressions expected |

**Gate Result**: ✅ PASS - All principles satisfied or not applicable.

**Post-Design Re-check**: ✅ PASS - No constitution violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/032-python312-upgrade/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # ✅ Phase 0: Dependency compatibility research
├── quickstart.md        # ✅ Phase 1: Implementation quickstart guide
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
# Files to modify (existing structure, no new directories)
pyproject.toml           # Python version constraint and dependencies
requirements.txt         # Runtime dependency versions (no changes needed)
requirements-dev.txt     # Development dependency versions
CLAUDE.md                # Developer playbook - Technology Stack section
README.md                # Project documentation - Installation section
CHANGELOG.md             # Version history entry
```

**Structure Decision**: No structural changes required. This is a configuration and documentation update affecting existing files only.

## Complexity Tracking

> No violations detected. This feature involves straightforward configuration updates.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |

## Implementation Phases

### Phase 0: Research (Dependency Compatibility) ✅ COMPLETE

Research tasks completed:
1. ✅ Verified all pinned dependencies have Python 3.12 support
2. ✅ Identified 4 dependencies requiring version bumps:
   - black: 23.9.1 → >=24.3.0 (mypyc wheels)
   - mypy: 1.5.1 → >=1.10.0 (PEP 695 support)
   - ipython: 8.14.0 → >=8.18.0 (tokenizer fixes)
   - jupyter: 1.0.0 → >=1.1.1 (outdated package)
3. ✅ Confirmed dbt-core/dbt-duckdb work with Python 3.12

**Output**: [research.md](./research.md)

### Phase 1: Design ✅ COMPLETE

Design deliverables completed:
1. ✅ `research.md` - Dependency compatibility findings with decisions and rationale
2. ✅ `quickstart.md` - Step-by-step implementation guide with validation checklist
3. ✅ Agent context updated via `update-agent-context.sh claude`

**Output**: [quickstart.md](./quickstart.md)

Note: No `data-model.md` or `contracts/` needed as this feature involves no data model or API changes.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Python version constraint | `>=3.11,<3.14` | Maintains 3.11 backward compat, allows 3.12 and future 3.13 |
| black upgrade | >=24.3.0 | Required for mypyc-compiled Python 3.12 wheels |
| mypy upgrade | >=1.10.0 | Full PEP 695 (Python 3.12 type syntax) support |
| ipython upgrade | >=8.18.0 | Python 3.12 tokenizer compatibility fixes |
| jupyter upgrade | >=1.1.1 | Version 1.0.0 is 9 years old, incompatible |

## Next Steps

Run `/speckit.tasks` to generate the task breakdown for implementation.
