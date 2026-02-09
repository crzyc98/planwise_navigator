"""Promotion hazard configuration management router.

API endpoints for viewing promotion hazard parameters
(base rate, level dampener, age/tenure multipliers) in PlanAlign Studio.

Note: PUT endpoint removed in 039-per-scenario-seed-config.
Promotion hazard saves now go through the unified scenario/workspace update endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from ..models.promotion_hazard import (
    PromotionHazardConfig,
)
from ..services.promotion_hazard_service import PromotionHazardService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_promotion_hazard_service() -> PromotionHazardService:
    """Get promotion hazard service instance."""
    return PromotionHazardService()


@router.get(
    "/{workspace_id}/config/promotion-hazards",
    response_model=PromotionHazardConfig,
    summary="Get promotion hazard configuration",
    description="Retrieve current promotion hazard parameters from dbt seed files",
)
async def get_promotion_hazard_config(workspace_id: str) -> PromotionHazardConfig:
    """Get current promotion hazard configuration."""
    service = get_promotion_hazard_service()

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
