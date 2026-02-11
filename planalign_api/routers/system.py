"""System health and status endpoints."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends
import yaml

from ..config import APISettings, get_settings
from ..models.system import HealthResponse, SystemStatus

router = APIRouter()


def get_active_simulation_count() -> int:
    """Get count of currently running simulations."""
    # Import here to avoid circular imports
    from .simulations import _active_runs
    return sum(1 for run in _active_runs.values() if run.status == "running")


def get_storage_usage(workspaces_root: Path) -> tuple[float, int, int]:
    """Calculate storage usage and counts."""
    total_size = 0
    workspace_count = 0
    scenario_count = 0

    if workspaces_root.exists():
        for workspace_dir in workspaces_root.iterdir():
            if workspace_dir.is_dir() and not workspace_dir.name.startswith("."):
                workspace_count += 1
                # Count scenarios
                scenarios_dir = workspace_dir / "scenarios"
                if scenarios_dir.exists():
                    for scenario_dir in scenarios_dir.iterdir():
                        if scenario_dir.is_dir():
                            scenario_count += 1
                # Calculate size
                for file_path in workspace_dir.rglob("*"):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size

    return total_size / (1024 * 1024), workspace_count, scenario_count  # Convert to MB


@router.get("/health", response_model=HealthResponse)
async def health_check(settings: APISettings = Depends(get_settings)) -> HealthResponse:
    """
    Check system health.

    Returns healthy status along with any issues or warnings.
    """
    issues = []
    warnings = []

    # Check workspaces directory
    if not settings.workspaces_root.exists():
        try:
            settings.workspaces_root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            issues.append(f"Cannot create workspaces directory: {e}")

    # Check default config exists
    if not settings.default_config_path.exists():
        warnings.append(
            f"Default config not found at {settings.default_config_path}. "
            "New workspaces will use built-in defaults."
        )

    # Check storage usage
    storage_mb, _, _ = get_storage_usage(settings.workspaces_root)
    storage_limit_mb = settings.storage_limit_gb * 1024
    if storage_mb > storage_limit_mb * 0.9:
        warnings.append(
            f"Storage usage at {storage_mb:.1f}MB of {storage_limit_mb:.0f}MB limit (>90%)"
        )

    return HealthResponse(
        healthy=len(issues) == 0,
        issues=issues,
        warnings=warnings,
    )


@router.get("/system/status", response_model=SystemStatus)
async def system_status(settings: APISettings = Depends(get_settings)) -> SystemStatus:
    """
    Get detailed system status.

    Returns comprehensive information about the system state.
    """
    storage_mb, workspace_count, scenario_count = get_storage_usage(
        settings.workspaces_root
    )
    storage_limit_mb = settings.storage_limit_gb * 1024
    storage_percent = (storage_mb / storage_limit_mb * 100) if storage_limit_mb > 0 else 0

    recommendations = []
    if storage_percent > 80:
        recommendations.append("Consider cleaning up old simulation results")
    if workspace_count == 0:
        recommendations.append("Create your first workspace to get started")

    # Get thread count from environment or system
    thread_count = os.cpu_count() or 1

    return SystemStatus(
        system_ready=True,
        system_message="System is ready for simulations",
        timestamp=datetime.utcnow(),
        active_simulations=get_active_simulation_count(),
        queued_simulations=0,
        total_storage_mb=storage_mb,
        storage_limit_mb=storage_limit_mb,
        storage_percent=storage_percent,
        workspace_count=workspace_count,
        scenario_count=scenario_count,
        thread_count=thread_count,
        recommendations=recommendations,
    )


@router.get("/config/defaults", response_model=Dict[str, Any])
async def get_default_config(
    settings: APISettings = Depends(get_settings),
) -> Dict[str, Any]:
    """
    Get the default simulation configuration.

    Returns the base configuration that new workspaces will inherit.
    """
    if settings.default_config_path.exists():
        with open(settings.default_config_path) as f:
            return yaml.safe_load(f)

    # Return built-in defaults if config file doesn't exist
    return {
        "simulation": {
            "start_year": 2025,
            "end_year": 2027,
            "random_seed": 42,
            "target_growth_rate": 0.03,
        },
        "compensation": {
            "cola_rate": 0.02,
            "merit_budget": 0.035,
            "promotion_compensation": {
                "base_increase_pct": 0.125,
            },
        },
        "workforce": {
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
        },
        "enrollment": {
            "auto_enrollment": {
                "enabled": True,
                "default_deferral_rate": 0.06,
            },
        },
        "employer_match": {
            "active_formula": "simple_match",
            "formulas": {
                "simple_match": {
                    "name": "Simple Match",
                    "type": "simple",
                    "match_rate": 0.50,
                    "max_match_percentage": 0.06,
                },
            },
            # E046: New match mode defaults (empty tiers = not configured)
            "tenure_match_tiers": [],
            "points_match_tiers": [],
        },
        "employer_core_contribution": {
            "enabled": True,
            "status": "flat",
            "contribution_rate": 0.03,
        },
        "optimization": {
            "event_generation": {
                "mode": "polars",
            },
        },
    }
