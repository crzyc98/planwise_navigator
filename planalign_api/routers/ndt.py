"""NDT (Non-Discrimination Testing) endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import APISettings, get_settings
from ..services.ndt_service import (
    ACPTestResponse,
    ADPTestResponse,
    AvailableYearsResponse,
    NDTService,
    Section401a4TestResponse,
    Section415TestResponse,
)
from ..services.scenario_read_warning import has_selected_result
from ..storage.workspace_storage import WorkspaceStorage
from ..models.compliance import ComplianceResponse, ComplianceEmployeePage, MetricName
from ..services.compliance_metrics import LimitStatus
from ..services.compliance_service import (
    ComplianceService,
    ComplianceEvidenceChangedError,
)
import duckdb

router = APIRouter()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


def get_ndt_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> NDTService:
    """Dependency to get NDT service."""
    return NDTService(storage)


def get_compliance_service(
    storage: WorkspaceStorage = Depends(get_storage),
) -> ComplianceService:
    return ComplianceService(storage)


def _validate_compliance_scenario(
    storage: WorkspaceStorage, workspace_id: str, scenario_id: str
) -> str:
    if not storage.get_workspace(workspace_id):
        raise HTTPException(404, "Workspace not found")
    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(404, "Scenario not found")
    if not has_selected_result(storage, workspace_id, scenario_id, scenario.status):
        raise HTTPException(400, "Scenario has no successful result")
    return scenario.name


@router.get(
    "/{workspace_id}/analytics/ndt/compliance", response_model=ComplianceResponse
)
def get_compliance_summary(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(...),
    warning_threshold: float = Query(0.95, gt=0.0, le=1.0),
    storage: WorkspaceStorage = Depends(get_storage),
    service: ComplianceService = Depends(get_compliance_service),
) -> ComplianceResponse:
    ids = list(dict.fromkeys(s.strip() for s in scenarios.split(",") if s.strip()))
    if not ids or len(ids) > 6:
        raise HTTPException(400, "Select between one and six scenarios")
    names = {s: _validate_compliance_scenario(storage, workspace_id, s) for s in ids}
    try:
        results = [
            service.summary(workspace_id, s, names[s], year, warning_threshold)
            for s in ids
        ]
        return ComplianceResponse(year=year, results=results)
    except ComplianceEvidenceChangedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except duckdb.Error as exc:
        raise HTTPException(
            422, "The selected archive lacks required compliance reporting data"
        ) from exc


@router.get(
    "/{workspace_id}/analytics/ndt/compliance/employees",
    response_model=ComplianceEmployeePage,
)
def get_compliance_employees(
    workspace_id: str,
    scenario_id: str = Query(...),
    year: int = Query(...),
    evidence: str = Query(..., min_length=64, max_length=64),
    metric: MetricName = Query(...),
    limit_status: LimitStatus | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    warning_threshold: float = Query(0.95, gt=0.0, le=1.0),
    storage: WorkspaceStorage = Depends(get_storage),
    service: ComplianceService = Depends(get_compliance_service),
) -> ComplianceEmployeePage:
    _validate_compliance_scenario(storage, workspace_id, scenario_id)
    try:
        return service.employees(
            workspace_id,
            scenario_id,
            year,
            evidence,
            metric,
            limit_status,
            offset,
            limit,
            warning_threshold,
        )
    except ComplianceEvidenceChangedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except duckdb.Error as exc:
        raise HTTPException(
            422, "The selected archive lacks required compliance reporting data"
        ) from exc


@router.get(
    "/{workspace_id}/analytics/ndt/available-years",
    response_model=AvailableYearsResponse,
)
def get_ndt_available_years(
    workspace_id: str,
    scenario_id: str = Query(..., description="Scenario ID"),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> AvailableYearsResponse:
    """Get available simulation years for NDT testing."""
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    scenario = storage.get_scenario(workspace_id, scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id} not found",
        )

    return ndt_service.get_available_years(workspace_id, scenario_id)


@router.get(
    "/{workspace_id}/analytics/ndt/acp",
    response_model=ACPTestResponse,
)
def run_acp_test(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(..., description="Simulation year to analyze"),
    include_employees: bool = Query(False, description="Include per-employee detail"),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> ACPTestResponse:
    """Run ACP non-discrimination test for one or more scenarios."""
    # Validate workspace
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    # Parse scenario IDs
    scenario_ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not scenario_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scenario ID is required",
        )

    # Validate all scenarios exist and are completed
    scenario_names = {}
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if not has_selected_result(storage, workspace_id, scenario_id, scenario.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        scenario_names[scenario_id] = scenario.name

    # Run ACP test for each scenario
    results = []
    for scenario_id in scenario_ids:
        result = ndt_service.run_acp_test(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            scenario_name=scenario_names[scenario_id],
            year=year,
            include_employees=include_employees,
        )
        results.append(result)

    return ACPTestResponse(
        test_type="acp",
        year=year,
        results=results,
    )


@router.get(
    "/{workspace_id}/analytics/ndt/401a4",
    response_model=Section401a4TestResponse,
)
def run_401a4_test(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(..., description="Simulation year to analyze"),
    include_employees: bool = Query(False, description="Include per-employee detail"),
    include_match: bool = Query(
        False, description="Include employer match in contribution rate"
    ),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> Section401a4TestResponse:
    """Run 401(a)(4) general nondiscrimination test for one or more scenarios."""
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    scenario_ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not scenario_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scenario ID is required",
        )

    scenario_names = {}
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if not has_selected_result(storage, workspace_id, scenario_id, scenario.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        scenario_names[scenario_id] = scenario.name

    results = []
    for scenario_id in scenario_ids:
        result = ndt_service.run_401a4_test(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            scenario_name=scenario_names[scenario_id],
            year=year,
            include_employees=include_employees,
            include_match=include_match,
        )
        results.append(result)

    return Section401a4TestResponse(
        test_type="401a4",
        year=year,
        results=results,
    )


@router.get(
    "/{workspace_id}/analytics/ndt/415",
    response_model=Section415TestResponse,
)
def run_415_test(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(..., description="Simulation year to analyze"),
    include_employees: bool = Query(False, description="Include per-employee detail"),
    warning_threshold: float = Query(
        0.95, description="At-risk threshold (0.0-1.0)", ge=0.0, le=1.0
    ),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> Section415TestResponse:
    """Run Section 415 annual additions limit test for one or more scenarios."""
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    scenario_ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not scenario_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scenario ID is required",
        )

    scenario_names = {}
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if not has_selected_result(storage, workspace_id, scenario_id, scenario.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        scenario_names[scenario_id] = scenario.name

    results = []
    for scenario_id in scenario_ids:
        result = ndt_service.run_415_test(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            scenario_name=scenario_names[scenario_id],
            year=year,
            include_employees=include_employees,
            warning_threshold=warning_threshold,
        )
        results.append(result)

    return Section415TestResponse(
        test_type="415",
        year=year,
        results=results,
    )


@router.get(
    "/{workspace_id}/analytics/ndt/adp",
    response_model=ADPTestResponse,
)
def run_adp_test(
    workspace_id: str,
    scenarios: str = Query(..., description="Comma-separated scenario IDs"),
    year: int = Query(..., description="Simulation year to analyze"),
    include_employees: bool = Query(False, description="Include per-employee detail"),
    safe_harbor: bool = Query(
        False, description="Mark plan as safe harbor (returns exempt)"
    ),
    testing_method: str = Query(
        "current", description="Testing method: current or prior"
    ),
    storage: WorkspaceStorage = Depends(get_storage),
    ndt_service: NDTService = Depends(get_ndt_service),
) -> ADPTestResponse:
    """Run ADP non-discrimination test for one or more scenarios."""
    workspace = storage.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found",
        )

    scenario_ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not scenario_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scenario ID is required",
        )

    if testing_method not in ("current", "prior"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="testing_method must be 'current' or 'prior'",
        )

    scenario_names = {}
    for scenario_id in scenario_ids:
        scenario = storage.get_scenario(workspace_id, scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )
        if not has_selected_result(storage, workspace_id, scenario_id, scenario.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scenario {scenario_id} has not completed successfully",
            )
        scenario_names[scenario_id] = scenario.name

    results = []
    for scenario_id in scenario_ids:
        result = ndt_service.run_adp_test(
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            scenario_name=scenario_names[scenario_id],
            year=year,
            include_employees=include_employees,
            safe_harbor=safe_harbor,
            testing_method=testing_method,
        )
        results.append(result)

    return ADPTestResponse(
        test_type="adp",
        year=year,
        results=results,
    )
