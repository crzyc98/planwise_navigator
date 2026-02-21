"""File upload and validation router."""

import logging
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from ..config import get_settings
from ..models.files import (
    CompensationAnalysisRequest,
    CompensationSolverRequest,
    CompensationSolverResponse,
    FileUploadResponse,
    FileValidationRequest,
    FileValidationResponse,
    LevelDistributionResponse,
)
from ..services.compensation_solver import CompensationSolver, WorkforceDynamics
from ..services.file_service import FileService
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


def get_workspace_storage() -> WorkspaceStorage:
    """Get workspace storage instance."""
    settings = get_settings()
    return WorkspaceStorage(settings.workspaces_root)

router = APIRouter()


def get_compensation_solver() -> CompensationSolver:
    """Get compensation solver instance."""
    settings = get_settings()
    return CompensationSolver(settings.workspaces_root)


def get_file_service() -> FileService:
    """Get file service instance."""
    settings = get_settings()
    return FileService(settings.workspaces_root)


@router.post(
    "/{workspace_id}/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload census file",
    description="Upload a census file (Parquet or CSV) to a workspace's data directory",
)
async def upload_census_file(
    workspace_id: str,
    file: UploadFile = File(..., description="Census file (.parquet or .csv)"),
) -> FileUploadResponse:
    """Upload a census file to a workspace."""
    service = get_file_service()

    # Validate file extension early
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided",
        )

    suffix = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if f".{suffix}" not in service.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File must be .parquet or .csv, got: .{suffix}",
        )

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {e}",
        )

    # Check file size
    if len(content) > service.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {service.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB limit",
        )

    # Save and validate file
    try:
        relative_path, metadata, absolute_path = service.save_uploaded_file(
            workspace_id=workspace_id,
            file_content=content,
            filename=file.filename,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error saving file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}",
        )

    # E090: Update workspace config to use this census file for all scenarios
    try:
        storage = get_workspace_storage()
        config_updated = storage.update_base_config_key(
            workspace_id=workspace_id,
            key_path="setup.census_parquet_path",
            value=absolute_path,
        )
        if config_updated:
            logger.info(f"Updated workspace {workspace_id} census path to: {absolute_path}")
        else:
            logger.warning(f"Failed to update workspace config - workspace may not exist: {workspace_id}")
    except Exception as e:
        # Don't fail the upload if config update fails - log warning and continue
        logger.warning(f"Failed to update workspace config with census path: {e}")

    return FileUploadResponse(
        success=True,
        file_path=relative_path,
        file_name=file.filename,
        file_size_bytes=metadata["file_size_bytes"],
        row_count=metadata["row_count"],
        columns=metadata["columns"],
        upload_timestamp=datetime.utcnow(),
        validation_warnings=metadata.get("validation_warnings", []),
        structured_warnings=metadata.get("structured_warnings", []),
        data_quality_warnings=metadata.get("data_quality_warnings", []),
        column_renames=metadata.get("column_renames", []),
        original_filename=metadata.get("original_filename"),
    )


@router.post(
    "/{workspace_id}/validate-path",
    response_model=FileValidationResponse,
    summary="Validate file path",
    description="Validate a file path and return metadata if valid",
)
async def validate_file_path(
    workspace_id: str,
    request: FileValidationRequest,
) -> FileValidationResponse:
    """Validate a file path and return metadata."""
    service = get_file_service()

    result = service.validate_path(
        workspace_id=workspace_id,
        file_path=request.file_path,
    )

    return FileValidationResponse(
        file_path=request.file_path,
        **result,
    )


@router.post(
    "/{workspace_id}/analyze-age-distribution",
    summary="Analyze age distribution from census",
    description="Analyze the age distribution of employees in a census file to match hiring patterns",
)
async def analyze_age_distribution(
    workspace_id: str,
    request: FileValidationRequest,
) -> dict:
    """Analyze age distribution from census data."""
    service = get_file_service()

    try:
        result = service.analyze_age_distribution(
            workspace_id=workspace_id,
            file_path=request.file_path,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to analyze age distribution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze census: {e}",
        )


@router.post(
    "/{workspace_id}/analyze-compensation-by-level",
    summary="Analyze compensation ranges by job level",
    description=(
        "Analyze compensation min/max/median/percentiles by job level from census data. "
        "By default, focuses on employees hired in the last 4 years for more relevant new hire targeting. "
        "Use lookback_years=0 to analyze all employees."
    ),
)
async def analyze_compensation_by_level(
    workspace_id: str,
    request: CompensationAnalysisRequest,
) -> dict:
    """Analyze compensation ranges by job level from census data."""
    service = get_file_service()

    try:
        result = service.analyze_compensation_by_level(
            workspace_id=workspace_id,
            file_path=request.file_path,
            lookback_years=request.lookback_years,
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to analyze compensation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze census: {e}",
        )


@router.post(
    "/{workspace_id}/solve-compensation-growth",
    response_model=CompensationSolverResponse,
    summary="Solve for compensation parameters",
    description=(
        "Given a target average compensation growth rate (e.g., 2% per year), "
        "solve for the COLA, merit budget, promotion increase, and promotion budget "
        "that achieve that target. IMPORTANTLY, this solver accounts for workforce "
        "dynamics (turnover and new hire compensation) which significantly impact "
        "average compensation growth."
    ),
)
async def solve_compensation_growth(
    workspace_id: str,
    request: CompensationSolverRequest,
) -> CompensationSolverResponse:
    """
    Solve for compensation parameters given a target growth rate.

    This is the "magic button" that clients can use to say "I want 2% average
    compensation growth" and get back the recommended COLA, merit, and promotion
    settings to achieve that target.

    The solver uses the CORRECT formula that accounts for workforce dynamics:
        Next_Year_Avg = (Stayers × Avg × (1 + raise_rate) + NewHires × NH_Avg) / Total
        Growth = (Next_Year_Avg / Current_Avg) - 1

    This is critical because turnover and new hires often have a significant
    (usually negative) impact on average compensation growth, even with generous
    raises for existing employees.
    """
    solver = get_compensation_solver()

    # Build workforce dynamics from request parameters
    dynamics = None
    if any([
        request.turnover_rate is not None,
        request.workforce_growth_rate is not None,
        request.new_hire_comp_ratio is not None,
    ]):
        dynamics = WorkforceDynamics(
            turnover_rate=request.turnover_rate if request.turnover_rate is not None else 0.15,
            workforce_growth_rate=request.workforce_growth_rate if request.workforce_growth_rate is not None else 0.03,
            new_hire_comp_ratio=request.new_hire_comp_ratio if request.new_hire_comp_ratio is not None else 0.85,
        )

    try:
        if request.file_path:
            result = solver.solve_with_census(
                workspace_id=workspace_id,
                file_path=request.file_path,
                target_growth_rate=request.target_growth_rate,
                promotion_increase=request.promotion_increase,
                cola_to_merit_ratio=request.cola_to_merit_ratio,
                workforce_dynamics=dynamics,
            )
            # Get level distribution for response
            try:
                distributions, _, _ = solver.analyze_workforce_for_solver(
                    workspace_id, request.file_path
                )
                level_dist = [
                    LevelDistributionResponse(
                        level=d.level,
                        name=d.name,
                        headcount=d.headcount,
                        percentage=round(d.percentage * 100, 1),
                        avg_compensation=round(d.avg_compensation, 2),
                        promotion_rate=round(d.promotion_rate * 100, 1),
                    )
                    for d in distributions
                ]
            except Exception:
                level_dist = None
        else:
            result = solver.solve_for_target_growth(
                target_growth_rate=request.target_growth_rate,
                promotion_increase=request.promotion_increase,
                cola_to_merit_ratio=request.cola_to_merit_ratio,
                workforce_dynamics=dynamics,
            )
            level_dist = None

        return CompensationSolverResponse(
            target_growth_rate=round(request.target_growth_rate * 100, 2),
            cola_rate=result.cola_rate,
            merit_budget=result.merit_budget,
            promotion_increase=result.promotion_increase,
            promotion_budget=result.promotion_budget,
            achieved_growth_rate=result.achieved_growth_rate,
            growth_gap=result.growth_gap,
            cola_contribution=result.cola_contribution,
            merit_contribution=result.merit_contribution,
            promo_contribution=result.promo_contribution,
            turnover_contribution=result.turnover_contribution,
            total_headcount=result.total_headcount,
            avg_compensation=result.avg_compensation,
            weighted_promotion_rate=result.weighted_promotion_rate,
            turnover_rate=result.turnover_rate,
            workforce_growth_rate=result.workforce_growth_rate,
            new_hire_comp_ratio=result.new_hire_comp_ratio,
            recommended_new_hire_ratio=result.recommended_new_hire_ratio,
            recommended_scale_factor=result.recommended_scale_factor,
            level_distribution=level_dist,
            warnings=result.warnings,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to solve compensation growth: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to solve: {e}",
        )
