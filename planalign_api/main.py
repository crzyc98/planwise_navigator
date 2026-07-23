"""
PlanAlign API - FastAPI application entry point.

Run with:
    uvicorn planalign_api.main:app --reload --port 8000
"""

import asyncio
import logging
import platform
import sys
from contextlib import asynccontextmanager

# Windows requires ProactorEventLoop for asyncio subprocess support
# Must be set before any asyncio operations
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()  # type: ignore[attr-defined]
    )

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from .config import get_settings
from .auth import require_api_token, require_websocket_api_token
from .routers import (
    system_router,
    workspaces_router,
    scenarios_router,
    simulations_router,
    batch_router,
    comparison_router,
    files_router,
    templates_router,
    analytics_router,
    bands_router,
    promotion_hazard_router,
    ndt_router,
    imports_router,
    provenance_router,
    timeline_router,
)
from .routers.vesting import router as vesting_router
from .routers.sync import router as sync_router
from .routers.calibration import router as calibration_router
from .websocket.handlers import simulation_websocket, batch_websocket
from .services.current_result import CurrentResultIntegrityError
from .services.scenario_read_warning import (
    RUN_CONSISTENCY_HEADERS,
    ScenarioReadRef,
    build_scenario_read_headers,
)
from .storage.workspace_storage import WorkspaceStorage

# Configure logging to show in console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Set log level for our modules
logging.getLogger("planalign_api").setLevel(logging.DEBUG)

SCENARIO_READ_ROUTES = {
    "list_scenarios",
    "get_scenario",
    "get_scenario_config",
    "export_scenario_results",
    "get_run_status",
    "get_run_telemetry",
    "list_runs",
    "get_run",
    "get_run_logs",
    "get_results",
    "export_results",
    "get_active_simulations",
    "get_run_details",
    "download_artifact",
    "compare_scenario_configs",
    "compare_scenarios",
    "get_dc_plan_analytics",
    "compare_dc_plan_analytics",
    "get_winners_losers",
    "get_vesting_years",
    "get_ndt_available_years",
    "run_acp_test",
    "run_401a4_test",
    "run_415_test",
    "run_adp_test",
    "search_employees",
    "get_employee_timeline",
}


def _find_workspace(storage: WorkspaceStorage, scenario_id: str) -> str | None:
    for workspace in storage.list_workspaces():
        if storage.get_scenario(workspace.id, scenario_id) is not None:
            return workspace.id
    return None


def _scenario_ids(request: Request) -> list[str]:
    values: list[str] = []
    direct = request.path_params.get("scenario_id") or request.query_params.get(
        "scenario_id"
    )
    if direct:
        values.append(direct)
    for name in ("scenario_a", "scenario_b", "baseline"):
        value = request.query_params.get(name)
        if value:
            values.append(value)
    values.extend(
        item.strip()
        for item in request.query_params.get("scenarios", "").split(",")
        if item.strip()
    )
    return list(dict.fromkeys(values))


def _scenario_refs(
    request: Request, storage: WorkspaceStorage
) -> list[ScenarioReadRef]:
    route = request.scope.get("route")
    if getattr(route, "name", None) not in SCENARIO_READ_ROUTES:
        return []
    workspace_id = request.path_params.get("workspace_id")
    scenario_ids = _scenario_ids(request)
    if getattr(route, "name", None) == "list_scenarios" and workspace_id:
        scenario_ids = [item.id for item in storage.list_scenarios(workspace_id)]
    refs: list[ScenarioReadRef] = []
    for scenario_id in scenario_ids:
        owner = workspace_id or _find_workspace(storage, scenario_id)
        if owner:
            refs.append(ScenarioReadRef(owner, scenario_id))
    return refs


def _install_run_header_openapi(app: FastAPI) -> None:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        header_schema = {"schema": {"type": "string"}}
        for route in app.routes:
            if getattr(route, "name", None) not in SCENARIO_READ_ROUTES:
                continue
            operation = schema["paths"][route.path_format]["get"]
            for response in operation.get("responses", {}).values():
                headers = response.setdefault("headers", {})
                for header in RUN_CONSISTENCY_HEADERS:
                    headers[header] = header_schema
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()

    # Startup: ensure workspaces directory exists
    settings.workspaces_root.mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown: cleanup if needed


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="PlanAlign API",
        description="Backend API for PlanAlign Studio - Workforce Simulation Platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Configure CORS
    app.add_middleware(  # type: ignore[call-arg, arg-type]
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=list(RUN_CONSISTENCY_HEADERS),
    )

    @app.middleware("http")
    async def add_scenario_read_headers(request: Request, call_next):
        response = await call_next(request)
        if request.method != "GET":
            return response
        storage = WorkspaceStorage(settings.workspaces_root)
        try:
            headers = build_scenario_read_headers(
                storage, _scenario_refs(request, storage)
            )
        except CurrentResultIntegrityError as exc:
            return JSONResponse(
                status_code=500,
                content={"detail": f"Current result integrity failure: {exc}"},
            )
        for name, value in headers.items():
            response.headers[name] = value
        return response

    # Include routers. The system router keeps /health public; its non-health
    # endpoints declare require_api_token directly because they expose system data.
    app.include_router(system_router, prefix="/api", tags=["System"])
    protected_dependencies = [Depends(require_api_token)]
    app.include_router(
        workspaces_router,
        prefix="/api/workspaces",
        tags=["Workspaces"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        scenarios_router,
        prefix="/api/workspaces",
        tags=["Scenarios"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        simulations_router,
        prefix="/api/scenarios",
        tags=["Simulations"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        batch_router,
        prefix="/api",
        tags=["Batch Processing"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        comparison_router,
        prefix="/api/workspaces",
        tags=["Comparison"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        files_router,
        prefix="/api/workspaces",
        tags=["Files"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        templates_router,
        prefix="/api/templates",
        tags=["Templates"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        sync_router,
        prefix="/api",
        tags=["Sync"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        analytics_router,
        prefix="/api/workspaces",
        tags=["Analytics"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        bands_router,
        prefix="/api/workspaces",
        tags=["Bands"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        promotion_hazard_router,
        prefix="/api/workspaces",
        tags=["Promotion Hazard"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        vesting_router,
        prefix="/api",
        tags=["Vesting"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        ndt_router,
        prefix="/api/workspaces",
        tags=["NDT Testing"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        imports_router,
        prefix="/api/workspaces",
        tags=["Data Import"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        calibration_router,
        prefix="/api",
        tags=["Calibration"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        provenance_router,
        prefix="/api",
        tags=["Run Provenance"],
        dependencies=protected_dependencies,
    )
    app.include_router(
        timeline_router,
        prefix="/api/workspaces",
        tags=["Timeline"],
        dependencies=protected_dependencies,
    )

    _install_run_header_openapi(app)

    # WebSocket endpoints use an explicit check because HTTP dependencies do not
    # apply to WebSocket routes.
    @app.websocket("/ws/simulation/{run_id}")
    async def websocket_simulation(websocket: WebSocket, run_id: str):
        """WebSocket endpoint for simulation telemetry."""
        if not await require_websocket_api_token(websocket):
            return
        await simulation_websocket(websocket, run_id)

    @app.websocket("/ws/batch/{batch_id}")
    async def websocket_batch(websocket: WebSocket, batch_id: str):
        """WebSocket endpoint for batch processing updates."""
        if not await require_websocket_api_token(websocket):
            return
        await batch_websocket(websocket, batch_id)

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "planalign_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
