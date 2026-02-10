# Research: Gitignore dbt Generated Artifacts

**Feature**: 042-gitignore-dbt-artifacts
**Date**: 2026-02-10

## R-001: Current State of dbt Artifact Ignore Rules

**Decision**: Consolidate scattered patterns into the existing "# dbt specific" section and use glob pattern `dbt/target*/` instead of listing individual target directories.

**Rationale**: Investigation revealed:
- `dbt/target/` is correctly placed at line 36 in "# dbt specific" section
- `dbt/target_perf_test/` is misplaced at line 247, buried under "# Cursor" section
- Neither directory was ever committed to git history — the ignore rules are working but disorganized
- A glob pattern `dbt/target*/` covers both and any future target directories without maintenance

**Alternatives considered**:
- Keep individual entries (`dbt/target/`, `dbt/target_perf_test/`): Rejected — requires manual updates for each new profile
- Use `**/target*/`: Rejected — too broad, could match non-dbt directories

## R-002: Tracked Generated Artifacts

**Decision**: Remove `dbt/year_processor_performance.json` from git tracking via `git rm --cached`.

**Rationale**: Investigation confirmed:
- File is 140 bytes, auto-generated (contains `baseline_metrics`, `last_updated` timestamp, `total_queries_analyzed`)
- Created 2025-08-09, no source-of-truth data
- Already partially covered by existing pattern `performance.json` at line 269, but that only matches root-level
- Adding `dbt/year_processor_performance.json` to `.gitignore` ensures it's explicitly ignored

**Alternatives considered**:
- Keep tracked: Rejected — it's auto-generated and changes on every performance test run
- Use broader `dbt/*.json`: Rejected — could catch intentional JSON config files in `dbt/`

## R-003: Misplaced Entries Near Line 247

**Decision**: Move `simulation.duckdb.zip` (line 248) to the "# DuckDB" section alongside the existing `simulation.duckdb` patterns, and remove the now-orphaned `dbt/target_perf_test/` entry entirely (replaced by glob).

**Rationale**: `simulation.duckdb.zip` is logically a DuckDB artifact (compressed database backup), not a Cursor-related file. Grouping it with `simulation.duckdb` and `*.duckdb` patterns makes intent clear.

**Alternatives considered**:
- Leave in place: Rejected — violates the consolidation goal (FR-003)
- Create a new "# Database backups" section: Rejected — the existing "# DuckDB" section is the right home
