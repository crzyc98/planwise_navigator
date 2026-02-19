"""API route handlers."""

from .system import router as system_router
from .workspaces import router as workspaces_router
from .scenarios import router as scenarios_router
from .simulations import router as simulations_router
from .batch import router as batch_router
from .comparison import router as comparison_router
from .files import router as files_router
from .templates import router as templates_router
from .analytics import router as analytics_router
from .bands import router as bands_router
from .promotion_hazard import router as promotion_hazard_router
from .ndt import router as ndt_router

__all__ = [
    "system_router",
    "workspaces_router",
    "scenarios_router",
    "simulations_router",
    "batch_router",
    "comparison_router",
    "files_router",
    "templates_router",
    "analytics_router",
    "bands_router",
    "promotion_hazard_router",
    "ndt_router",
]
