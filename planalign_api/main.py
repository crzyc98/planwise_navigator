"""
PlanAlign API - FastAPI application entry point.

Run with:
    uvicorn planalign_api.main:app --reload --port 8000
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import (
    system_router,
    workspaces_router,
    scenarios_router,
    simulations_router,
    batch_router,
    comparison_router,
    files_router,
    templates_router,
)
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
    pass


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

    # Include routers
    app.include_router(system_router, prefix="/api", tags=["System"])
    app.include_router(workspaces_router, prefix="/api/workspaces", tags=["Workspaces"])
    app.include_router(scenarios_router, prefix="/api/workspaces", tags=["Scenarios"])
    app.include_router(simulations_router, prefix="/api/scenarios", tags=["Simulations"])
    app.include_router(batch_router, prefix="/api", tags=["Batch Processing"])
    app.include_router(comparison_router, prefix="/api/workspaces", tags=["Comparison"])
    app.include_router(files_router, prefix="/api/workspaces", tags=["Files"])
    app.include_router(templates_router, prefix="/api/templates", tags=["Templates"])

    # WebSocket endpoints
    @app.websocket("/ws/simulation/{run_id}")
    async def websocket_simulation(websocket: WebSocket, run_id: str):
        """WebSocket endpoint for simulation telemetry."""
        await simulation_websocket(websocket, run_id)

    @app.websocket("/ws/batch/{batch_id}")
    async def websocket_batch(websocket: WebSocket, batch_id: str):
        """WebSocket endpoint for batch processing updates."""
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
