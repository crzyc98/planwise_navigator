# Implementation Plan: NDT ADP Test

**Branch**: `052-ndt-adp-test` | **Date**: 2026-02-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/052-ndt-adp-test/spec.md`

## Summary

Add an ADP (Actual Deferral Percentage) nondiscrimination test to the existing NDT suite. The ADP test calculates each eligible participant's ratio of elective deferrals (pre-tax + Roth) to plan compensation, classifies participants as HCE/NHCE using prior-year compensation thresholds, and applies the IRS two-prong test (basic 1.25× and alternative min(2×, +2pp)). The implementation mirrors the existing ACP test pattern across the full stack (FastAPI backend, React frontend, pytest suite) with three additions: safe harbor exemption toggle, configurable testing method (current/prior year), and excess HCE deferral calculation on failure.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (API), Pydantic v2 (models), React 18 + Vite (frontend), DuckDB 1.0.0 (queries)
**Storage**: DuckDB (per-scenario `simulation.duckdb` via `DatabasePathResolver`) — read-only access
**Testing**: pytest (backend), manual verification (frontend)
**Target Platform**: Linux server (API), modern browsers (frontend)
**Project Type**: Web application (backend API + frontend SPA)
**Performance Goals**: Parity with existing NDT tests (<2s response for typical scenario)
**Constraints**: Single-threaded DuckDB reads, same data sources as ACP/401(a)(4)
**Scale/Scope**: Same participant volumes as existing NDT tests (up to 100K employees)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | Read-only queries against `fct_workforce_snapshot`; no events created |
| II. Modular Architecture | PASS | New methods added to existing `NDTService` class; new components follow established pattern; no new modules needed |
| III. Test-First Development | PASS | New `test_ndt_adp.py` test file planned; tests written before implementation |
| IV. Enterprise Transparency | PASS | `hce_threshold_used`, `applied_test`, `testing_method` fields provide audit trail |
| V. Type-Safe Configuration | PASS | Pydantic v2 models for all request/response types; TypeScript interfaces for frontend |
| VI. Performance & Scalability | PASS | Same query pattern as ACP; single SQL query per scenario; optional employee detail |

**Post-Phase 1 Re-check**: All gates still pass. No new dependencies, no circular references, no schema mutations.

## Project Structure

### Documentation (this feature)

```text
specs/052-ndt-adp-test/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: Research decisions
├── data-model.md        # Phase 1: Entity definitions
├── quickstart.md        # Phase 1: Quick reference
├── contracts/
│   └── api.yaml         # Phase 1: API contract
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
planalign_api/
├── services/
│   └── ndt_service.py        # ADD: ADPEmployeeDetail, ADPScenarioResult, ADPTestResponse models
│                              # ADD: run_adp_test(), _compute_adp_result() methods
└── routers/
    └── ndt.py                 # ADD: GET /{workspace_id}/analytics/ndt/adp endpoint

planalign_studio/
├── components/
│   └── NDTTesting.tsx         # ADD: 'adp' to TestType, ADPSingleResult, ADPComparisonResults
│                              # ADD: Safe Harbor toggle, testing method selector
└── services/
    └── api.ts                 # ADD: ADP interfaces and runADPTest() function

tests/
└── test_ndt_adp.py            # NEW: ADP test suite (~300 lines)
```

**Structure Decision**: Web application structure (backend + frontend). All changes extend existing files except the new test file. This follows the established pattern where each NDT test type adds to `ndt_service.py`, `ndt.py`, `NDTTesting.tsx`, and `api.ts`.

## Implementation Design

### Backend Service Layer (`ndt_service.py`)

#### New Pydantic Models

```python
class ADPEmployeeDetail(BaseModel):
    employee_id: str
    is_hce: bool
    employee_deferrals: float = 0.0
    plan_compensation: float = 0.0
    individual_adp: float = 0.0
    prior_year_compensation: Optional[float] = None

class ADPScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    simulation_year: int
    test_result: str  # "pass", "fail", "exempt", "error"
    test_message: Optional[str] = None
    hce_count: int = 0
    nhce_count: int = 0
    excluded_count: int = 0
    hce_average_adp: float = 0.0
    nhce_average_adp: float = 0.0
    basic_test_threshold: float = 0.0
    alternative_test_threshold: float = 0.0
    applied_test: str = "basic"
    applied_threshold: float = 0.0
    margin: float = 0.0
    excess_hce_amount: Optional[float] = None
    testing_method: str = "current"
    safe_harbor: bool = False
    hce_threshold_used: int = 0
    employees: Optional[List[ADPEmployeeDetail]] = None

class ADPTestResponse(BaseModel):
    test_type: str = "adp"
    year: int
    results: List[ADPScenarioResult]
```

#### `run_adp_test()` Method

Follows the `run_acp_test()` pattern exactly:
1. Resolve database path via `self.db_resolver.resolve()`
2. Short-circuit if `safe_harbor=True` → return exempt result immediately
3. Ensure seed current via `self._ensure_seed_current()`
4. Load HCE threshold from `config_irs_limits` (prior year fallback)
5. Check prior year data existence
6. Execute SQL query (CTE-based, same structure as ACP but using `prorated_annual_contributions`)
7. Loop rows: accumulate HCE/NHCE ADP lists, optionally build employee details
8. Handle edge cases (no NHCE → error, no HCE → auto-pass)
9. Call `_compute_adp_result()` to compute thresholds and pass/fail

**Key SQL difference from ACP**:
```sql
-- ACP uses: COALESCE(employer_match_amount, 0) / prorated_annual_compensation AS individual_acp
-- ADP uses: COALESCE(prorated_annual_contributions, 0) / prorated_annual_compensation AS individual_adp
```

**Prior year testing method**: When `testing_method="prior"`, query prior year snapshot for NHCE participants, compute their average ADP, and use that as the NHCE baseline for the two-prong test instead of current year NHCE average.

#### `_compute_adp_result()` Method

Same math as `_compute_test_result()` but with ADP-specific fields:
- Basic threshold: `nhce_avg × 1.25`
- Alternative threshold: `min(nhce_avg × 2.0, nhce_avg + 0.02)`
- Select more favorable (higher threshold)
- Pass if `hce_avg <= applied_threshold`
- Margin = `applied_threshold - hce_avg`
- **New**: When failing, calculate `excess_hce_amount = (hce_avg - applied_threshold) × sum(hce_compensations)`

### Backend Router Layer (`ndt.py`)

New endpoint following the identical pattern of existing NDT endpoints:

```python
@router.get("/{workspace_id}/analytics/ndt/adp")
async def run_adp_test(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(..., description="Simulation year to analyze"),
    include_employees: bool = Query(False),
    safe_harbor: bool = Query(False, description="Mark plan as safe harbor exempt"),
    testing_method: str = Query("current", description="Testing method: current or prior"),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> ADPTestResponse:
```

Validation and loop pattern identical to existing endpoints.

### Frontend API Layer (`api.ts`)

New TypeScript interfaces mirroring Pydantic models, plus:

```typescript
export async function runADPTest(
  workspaceId: string,
  scenarioIds: string[],
  year: number,
  includeEmployees: boolean = false,
  safeHarbor: boolean = false,
  testingMethod: string = 'current',
): Promise<ADPTestResponse> {
  const params = new URLSearchParams({
    scenarios: scenarioIds.join(','),
    year: year.toString(),
    include_employees: includeEmployees.toString(),
    safe_harbor: safeHarbor.toString(),
    testing_method: testingMethod,
  });
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/analytics/ndt/adp?${params}`
  );
  return handleResponse<ADPTestResponse>(response);
}
```

### Frontend Component Layer (`NDTTesting.tsx`)

#### State Additions
```typescript
type TestType = 'acp' | '401a4' | '415' | 'adp';
const [safeHarbor, setSafeHarbor] = useState(false);
const [testingMethod, setTestingMethod] = useState<'current' | 'prior'>('current');
```

#### UI Additions
- Add `<option value="adp">ADP Test</option>` to test type selector
- Add Safe Harbor toggle (visible when `testType === 'adp'`), following Include Match pattern
- Add Testing Method selector (visible when `testType === 'adp'`)
- Add `ADPSingleResult` component (~100 lines, mirrors `ACPSingleResult`)
- Add `ADPComparisonResults` component (~60 lines, mirrors `ACPComparisonResults`)

#### ADPSingleResult Component
Shows:
- Pass/fail/exempt status card with margin
- HCE/NHCE average ADPs
- Basic and alternative thresholds with applied prong indicator
- **Excess HCE amount** (when failing, prominently displayed)
- Safe harbor badge (when exempt)
- Testing method indicator
- Expandable employee detail table (6 columns: ID, HCE status, Deferrals, Comp, ADP, Prior Comp)

### Test Suite (`test_ndt_adp.py`)

Test categories:
1. **Basic pass/fail**: Simple HCE/NHCE with known ADPs, verify thresholds and result
2. **Two-prong selection**: Scenarios where basic vs alternative prong applies
3. **Excess amount calculation**: Verify dollar amount on failure
4. **Safe harbor exemption**: Toggle on → exempt result, no calculation
5. **Prior year testing**: Verify prior year NHCE baseline is used
6. **Edge cases**: Zero comp (excluded), no HCE (auto-pass), no NHCE (error), zero deferrals (included at 0%)
7. **Employee detail**: Verify individual ADP calculations and field population

## Complexity Tracking

No constitution violations. All changes follow established patterns.
