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
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

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

# Configure logging to show in console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Set log level for our modules
logging.getLogger("planalign_api").setLevel(logging.DEBUG)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
