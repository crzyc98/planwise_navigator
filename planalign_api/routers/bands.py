"""Band configuration management router.

API endpoints for viewing, editing, and analyzing age and tenure band configurations
in PlanAlign Studio.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from ..config import get_settings
from ..models.bands import (
    BandAnalysisRequest,
    BandAnalysisResult,
    BandConfig,
    BandSaveRequest,
    BandSaveResponse,
)
from ..services.band_service import BandService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_band_service() -> BandService:
    """Get band service instance."""
    settings = get_settings()
    return BandService(settings.workspaces_root)


# -----------------------------------------------------------------------------
# GET /config/bands - Get Band Configurations (T009)
# -----------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/config/bands",
    response_model=BandConfig,
    summary="Get band configurations",
    description="Retrieve current age and tenure band definitions from dbt seed files",
)
async def get_band_configs(workspace_id: str) -> BandConfig:
    """
    Get current band configurations.

    Args:
        workspace_id: Workspace ID (for API consistency; bands are global)

    Returns:
        BandConfig with age_bands and tenure_bands
    """
    service = get_band_service()

    try:
        config = service.read_band_configs()
        return config
    except FileNotFoundError as e:
        logger.error(f"Band configuration file not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Band configuration file not found: {e}",
        )
    except ValueError as e:
        logger.error(f"Invalid band configuration data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid band configuration data: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to read band configurations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read band configurations: {e}",
        )


# -----------------------------------------------------------------------------
# PUT /config/bands - Save Band Configurations (T016)
# -----------------------------------------------------------------------------


@router.put(
    "/{workspace_id}/config/bands",
    response_model=BandSaveResponse,
    summary="Save band configurations",
    description="""
Save updated band configurations to dbt seed files.

Validates for:
- [min, max) interval convention
- No gaps between consecutive bands
- No overlapping ranges
- Coverage from 0 to upper bound
""",
)
async def save_band_configs(
    workspace_id: str,
    request: BandSaveRequest,
) -> BandSaveResponse:
    """
    Save band configurations after validation.

    Args:
        workspace_id: Workspace ID
        request: Band configuration to save

    Returns:
        BandSaveResponse with success status and any validation errors
    """
    service = get_band_service()

    try:
        success, validation_errors, message = service.save_band_configs(
            age_bands=request.age_bands,
            tenure_bands=request.tenure_bands,
        )

        # Return 400 if validation failed
        if not success and validation_errors:
            return BandSaveResponse(
                success=False,
                validation_errors=validation_errors,
                message=message,
            )

        return BandSaveResponse(
            success=success,
            validation_errors=validation_errors,
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to save band configurations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save band configurations: {e}",
        )


# -----------------------------------------------------------------------------
# POST /analyze-age-bands - Analyze Census for Age Band Suggestions (T026)
# -----------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/analyze-age-bands",
    response_model=BandAnalysisResult,
    summary="Analyze census for age band suggestions",
    description="""
Analyzes census data to suggest optimal age band boundaries based on
employee age distribution. Focuses on recent hires when possible.
Uses percentile-based boundary detection.
""",
)
async def analyze_age_bands(
    workspace_id: str,
    request: BandAnalysisRequest,
) -> BandAnalysisResult:
    """
    Analyze census data and suggest age band boundaries.

    Args:
        workspace_id: Workspace ID
        request: Request with file_path to census file

    Returns:
        BandAnalysisResult with suggested bands and statistics
    """
    service = get_band_service()

    try:
        result = service.analyze_age_distribution_for_bands(
            workspace_id=workspace_id,
            file_path=request.file_path,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to analyze age bands: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze census: {e}",
        )


# -----------------------------------------------------------------------------
# POST /analyze-tenure-bands - Analyze Census for Tenure Band Suggestions (T034)
# -----------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/analyze-tenure-bands",
    response_model=BandAnalysisResult,
    summary="Analyze census for tenure band suggestions",
    description="""
Analyzes census data to suggest optimal tenure band boundaries based on
employee tenure distribution. Uses percentile-based boundary detection.
""",
)
async def analyze_tenure_bands(
    workspace_id: str,
    request: BandAnalysisRequest,
) -> BandAnalysisResult:
    """
    Analyze census data and suggest tenure band boundaries.

    Args:
        workspace_id: Workspace ID
        request: Request with file_path to census file

    Returns:
        BandAnalysisResult with suggested bands and statistics
    """
    service = get_band_service()

    try:
        result = service.analyze_tenure_distribution_for_bands(
            workspace_id=workspace_id,
            file_path=request.file_path,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to analyze tenure bands: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze census: {e}",
        )
