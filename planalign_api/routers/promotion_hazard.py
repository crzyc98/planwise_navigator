"""Promotion hazard configuration management router.

API endpoints for viewing promotion hazard parameters
(base rate, level dampener, age/tenure multipliers) in PlanAlign Studio.

Note: PUT endpoint removed in 039-per-scenario-seed-config.
Promotion hazard saves now go through the unified scenario/workspace update endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..models.promotion_hazard import (
    PromotionHazardAgeMultiplier,
    PromotionHazardBase,
    PromotionHazardConfig,
    PromotionHazardTenureMultiplier,
)
from ..services.promotion_hazard_service import PromotionHazardService
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

router = APIRouter()


def get_promotion_hazard_service() -> PromotionHazardService:
    """Get promotion hazard service instance."""
    return PromotionHazardService()


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


@router.get(
    "/{workspace_id}/config/promotion-hazards",
    response_model=PromotionHazardConfig,
    summary="Get promotion hazard configuration",
    description="Retrieve current promotion hazard parameters from dbt seed files",
)
async def get_promotion_hazard_config(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> PromotionHazardConfig:
    """
    Get current promotion hazard configuration.

    Follows the fallback chain: workspace base_config > global CSV defaults.
    """
    # Try workspace base_config first
    workspace = storage.get_workspace(workspace_id)

    if workspace is not None and workspace.base_config:
        ph = workspace.base_config.get("promotion_hazard")
        if ph is not None:
            try:
                config = PromotionHazardConfig(
                    base=PromotionHazardBase(
                        base_rate=ph["base_rate"],
                        level_dampener_factor=ph["level_dampener_factor"],
                    ),
                    age_multipliers=[
                        PromotionHazardAgeMultiplier(**m)
                        for m in ph["age_multipliers"]
                    ],
                    tenure_multipliers=[
                        PromotionHazardTenureMultiplier(**m)
                        for m in ph["tenure_multipliers"]
                    ],
                )
                logger.info(
                    f"Loaded promotion hazard config from workspace "
                    f"'{workspace_id}' base_config"
                )
                return config
            except Exception as e:
                logger.warning(
                    f"Failed to parse promotion hazard from workspace base_config, "
                    f"falling back to global CSV: {e}"
                )

    # Fall back to global CSV
    service = get_promotion_hazard_service()
    logger.info("Loaded promotion hazard config from global CSV (fallback)")

    try:
        return service.read_all()
    except FileNotFoundError as e:
        logger.error(f"Promotion hazard config file not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Promotion hazard config file not found: {e}",
        )
    except ValueError as e:
        logger.error(f"Invalid promotion hazard config data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid promotion hazard config data: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to read promotion hazard config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read promotion hazard config: {e}",
        )
