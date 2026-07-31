"""System health and status endpoints."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends
import yaml  # type: ignore[import]  # types-PyYAML not in CI deps

from ..auth import require_api_token
from ..config import APISettings, get_settings
from ..models.system import HealthResponse, SystemStatus
from ..services.storage_usage import workspace_totals

router = APIRouter()


def get_active_simulation_count() -> int:
    """Get count of currently running simulations."""
    # Import here to avoid circular imports
    from .simulations import _active_runs

    return sum(1 for run in _active_runs.values() if run.status == "running")


def get_storage_usage(workspaces_root: Path) -> tuple[float, int, int]:
    """Calculate storage usage and counts (MB, workspaces, scenarios)."""
    totals = workspace_totals(workspaces_root)
    assert totals is not None  # allow_scan defaults True, so never None here
    return totals.total_mb, totals.workspace_count, totals.scenario_count


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

    # Check storage usage. Health is polled and must stay fast, so this reads
    # cached totals only; when the cache is cold the warning is omitted rather
    # than walking multi-gigabyte workspace trees. /api/system/status does the
    # scan and warms the cache for subsequent health checks.
    totals = workspace_totals(settings.workspaces_root, allow_scan=False)
    storage_limit_mb = settings.storage_limit_gb * 1024
    if totals is not None and totals.total_mb > storage_limit_mb * 0.9:
        warnings.append(
            f"Storage usage at {totals.total_mb:.1f}MB of "
            f"{storage_limit_mb:.0f}MB limit (>90%)"
        )

    return HealthResponse(
        healthy=len(issues) == 0,
        issues=issues,
        warnings=warnings,
    )


@router.get(
    "/system/status",
    response_model=SystemStatus,
    dependencies=[Depends(require_api_token)],
)
async def system_status(settings: APISettings = Depends(get_settings)) -> SystemStatus:
    """
    Get detailed system status.

    Returns comprehensive information about the system state.
    """
    storage_mb, workspace_count, scenario_count = get_storage_usage(
        settings.workspaces_root
    )
    storage_limit_mb = settings.storage_limit_gb * 1024
    storage_percent = (
        (storage_mb / storage_limit_mb * 100) if storage_limit_mb > 0 else 0
    )

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
        timestamp=datetime.now(timezone.utc),
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


@router.get(
    "/config/defaults",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_api_token)],
)
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
                "opt_out_rates": {
                    "by_age": {
                        "young": 0.35,
                        "mid_career": 0.20,
                        "mature": 0.15,
                        "senior": 0.10,
                    },
                    "by_income": {
                        "low_income": 0.40,
                        "moderate": 0.25,
                        "high": 0.15,
                        "executive": 0.05,
                    },
                },
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
