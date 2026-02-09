# Research: Vesting Year Selector

**Feature**: 040-vesting-year-selector
**Date**: 2026-02-09

## Research Findings

### R1: Backend `simulation_year` Support

**Decision**: Leverage existing backend support — no changes to analysis logic needed.

**Rationale**: The `VestingAnalysisRequest` model already defines `simulation_year: Optional[int] = Field(default=None, ge=2020, le=2050)`. The `VestingService.analyze_vesting()` method at line 420 uses `year = request.simulation_year or self._get_final_year(conn)`. The frontend TypeScript interface also already includes `simulation_year?: number`. Only the UI control and wiring are missing.

**Alternatives considered**:
- Rebuilding backend support: Unnecessary — already fully implemented and tested.

### R2: Retrieving Available Simulation Years

**Decision**: Add a lightweight `GET` endpoint to the vesting router that queries `SELECT DISTINCT simulation_year FROM fct_workforce_snapshot ORDER BY simulation_year ASC`.

**Rationale**: The `fct_workforce_snapshot` table is the same table the vesting service already queries for terminated employees. Using `DISTINCT simulation_year` is a single-column index scan on a table that typically has <500K rows, ensuring sub-100ms response times. The endpoint reuses the existing `DatabasePathResolver` pattern and `VestingService` dependency injection.

**Alternatives considered**:
- Deriving years from scenario config (start_year/end_year): Rejected — the config may not reflect actual simulation results if a run was partial or failed mid-way. Querying the actual data is the source of truth.
- Adding a generic "scenario metadata" endpoint: Over-engineering for a single-use case. Can be generalized later if needed.

### R3: Frontend Year Selector Placement

**Decision**: Add the year selector as a new row below the existing 4-column grid (Workspace, Scenario, Current Schedule, Proposed Schedule), placed inline with the Analyze button.

**Rationale**: The current 4-column grid is already dense with the hours toggle sub-controls under each schedule selector. Adding a 5th column would compress all elements. A separate row keeps the existing layout intact and pairs the year selector logically with the action button — both are "analysis parameters" rather than "data selectors."

**Alternatives considered**:
- 5-column grid: Rejected — too cramped, especially on medium screens where it wraps to 2 columns.
- Replacing the analysis year display in the results banner: Rejected — that's output display, not input selection.

### R4: Scenario Change Behavior

**Decision**: When the scenario changes, fetch the new year list and auto-select the final (most recent) year.

**Rationale**: This matches the existing pattern where changing workspace resets the scenario selector. It preserves backward compatibility (default = final year) and prevents stale year selections from a previous scenario.

**Alternatives considered**:
- Keep the previous year selection if it exists in the new scenario: Adds complexity for marginal benefit. Users switching scenarios typically want fresh analysis.

### R5: Database Connection Pattern

**Decision**: Reuse the existing `DatabasePathResolver` + read-only DuckDB connection pattern from `VestingService`.

**Rationale**: The `analyze_vesting` method already demonstrates the correct pattern: resolve database path via `self.db_resolver.resolve(workspace_id, scenario_id)`, open read-only connection, query, close in `finally` block. The years endpoint follows the same pattern.

**Alternatives considered**:
- Creating a separate service class: Over-engineering for a single query.
