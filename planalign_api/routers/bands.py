"""Band configuration and census analysis router.

API endpoints for viewing, editing, and analyzing age and tenure band configurations
and turnover rate analysis in PlanAlign Studio.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..models.bands import (
    Band,
    BandAnalysisRequest,
    BandAnalysisResult,
    BandConfig,
)
from ..models.turnover import TurnoverAnalysisRequest, TurnoverAnalysisResult
from ..services.band_service import BandService
from ..services.turnover_service import TurnoverAnalysisService
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

router = APIRouter()


def get_band_service() -> BandService:
    """Get band service instance."""
    settings = get_settings()
    return BandService(settings.workspaces_root)


def get_storage(settings: APISettings = Depends(get_settings)) -> WorkspaceStorage:
    """Dependency to get workspace storage."""
    return WorkspaceStorage(settings.workspaces_root)


# -----------------------------------------------------------------------------
# GET /config/bands - Get Band Configurations (T009)
# -----------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/config/bands",
    response_model=BandConfig,
    summary="Get band configurations",
    description="Retrieve current age and tenure band definitions from dbt seed files",
)
async def get_band_configs(
    workspace_id: str,
    storage: WorkspaceStorage = Depends(get_storage),
) -> BandConfig:
    """
    Get current band configurations.

    Follows the fallback chain: workspace base_config > global CSV defaults.

    Args:
        workspace_id: Workspace ID
        storage: Injected workspace storage

    Returns:
        BandConfig with age_bands and tenure_bands
    """
    service = get_band_service()

    # Try workspace base_config first
    age_bands = None
    tenure_bands = None
    workspace = storage.get_workspace(workspace_id)

    if workspace is not None and workspace.base_config:
        if "age_bands" in workspace.base_config:
            try:
                age_bands = [
                    Band(**band_dict)
                    for band_dict in workspace.base_config["age_bands"]
                ]
                logger.info(
                    f"Loaded {len(age_bands)} age bands from workspace "
                    f"'{workspace_id}' base_config"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse age bands from workspace base_config, "
                    f"falling back to global CSV: {e}"
                )
                age_bands = None

        if "tenure_bands" in workspace.base_config:
            try:
                tenure_bands = [
                    Band(**band_dict)
                    for band_dict in workspace.base_config["tenure_bands"]
                ]
                logger.info(
                    f"Loaded {len(tenure_bands)} tenure bands from workspace "
                    f"'{workspace_id}' base_config"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse tenure bands from workspace base_config, "
                    f"falling back to global CSV: {e}"
                )
                tenure_bands = None

    # Fall back to global CSV for any missing band types
    try:
        if age_bands is None:
            age_bands = service.read_bands_from_csv("age")
            logger.info("Loaded age bands from global CSV (fallback)")
        if tenure_bands is None:
            tenure_bands = service.read_bands_from_csv("tenure")
            logger.info("Loaded tenure bands from global CSV (fallback)")
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

    return BandConfig(age_bands=age_bands, tenure_bands=tenure_bands)


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


# -----------------------------------------------------------------------------
# POST /analyze-turnover - Analyze Census for Turnover Rate Suggestions
# -----------------------------------------------------------------------------


def get_turnover_service() -> TurnoverAnalysisService:
    """Get turnover analysis service instance."""
    settings = get_settings()
    return TurnoverAnalysisService(settings.workspaces_root)


@router.post(
    "/{workspace_id}/analyze-turnover",
    response_model=TurnoverAnalysisResult,
    summary="Analyze census for turnover rate suggestions",
    description="""
Analyzes census data to suggest termination rates for experienced employees
and new hires based on actual termination history in the census file.
""",
)
async def analyze_turnover(
    workspace_id: str,
    request: TurnoverAnalysisRequest,
) -> TurnoverAnalysisResult:
    """
    Analyze census data and suggest termination rates.

    Args:
        workspace_id: Workspace ID
        request: Request with file_path to census file

    Returns:
        TurnoverAnalysisResult with suggested rates and statistics
    """
    service = get_turnover_service()

    try:
        result = service.analyze_turnover_rates(
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
        logger.error(f"Failed to analyze turnover rates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze census for turnover rates: {e}",
        )
