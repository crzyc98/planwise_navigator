"""API route handlers."""

from .system import router as system_router
from .workspaces import router as workspaces_router
from .scenarios import router as scenarios_router
from .simulations import router as simulations_router
from .batch import router as batch_router
from .comparison import router as comparison_router

__all__ = [
    "system_router",
    "workspaces_router",
    "scenarios_router",
    "simulations_router",
    "batch_router",
    "comparison_router",
]
