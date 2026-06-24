"""Data import endpoints — upload CSV/Excel, configure field mappings, generate Parquet."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ..config import APISettings, get_settings
from ..models.imports import (
    ApplyTemplateRequest,
    DetectedColumn,
    GenerateResponse,
    ImportSession,
    MappedPreviewResponse,
    MappingSaveRequest,
    MappingSaveResponse,
    MappingTemplatesResponse,
    MappingValidationError,
    ParquetFilesResponse,
    PreviewResponse,
    SaveTemplateRequest,
    SaveTemplateResponse,
    SheetSelectRequest,
    SuggestionsResponse,
)
from ..services.census_schema import CANONICAL_NAMES, FIELDS, get_field, is_canonical
from ..services.import_service import ImportService
from ..services.suggestion_engine import SuggestionEngine
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-safe list of dicts (handles NaT, Timestamp, NaN)."""
    import math

    records = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                clean[k] = None
            elif hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif hasattr(v, "item"):
                clean[k] = v.item()
            else:
                clean[k] = v
        records.append(clean)
    return records


OUTPUT_COLUMN_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")

router = APIRouter()


def get_import_service(settings: APISettings = Depends(get_settings)) -> ImportService:
    return ImportService(workspaces_root=settings.workspaces_root)


def get_workspace_storage(
    settings: APISettings = Depends(get_settings),
) -> WorkspaceStorage:
    return WorkspaceStorage(settings.workspaces_root)


def _check_workspace(workspace_id: str, storage: WorkspaceStorage) -> None:
    if storage.get_workspace(workspace_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id!r} not found",
        )


def _check_session(
    workspace_id: str, import_id: str, service: ImportService
) -> ImportSession:
    session = service.get_session(workspace_id, import_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import session {import_id!r} not found",
        )
    return session


def _validate_mapping(
    mappings, detected_names: set[str]
) -> List[MappingValidationError]:
    errors: List[MappingValidationError] = []
    seen_output: dict[str, str] = {}
    valid_names = ", ".join(sorted(CANONICAL_NAMES))
    for m in mappings:
        if m.is_excluded:
            continue
        if m.input_column not in detected_names:
            errors.append(
                MappingValidationError(
                    field="input_column",
                    input_column=m.input_column,
                    message=f"Column {m.input_column!r} not found in detected columns",
                )
            )
        if not is_canonical(m.output_column):
            errors.append(
                MappingValidationError(
                    field="output_column",
                    input_column=m.input_column,
                    message=(
                        f"Output column {m.output_column!r} is not a recognized census field. "
                        f"Valid fields: {valid_names}"
                    ),
                )
            )
        if m.output_column in seen_output:
            errors.append(
                MappingValidationError(
                    field="output_column",
                    input_column=m.input_column,
                    message=f"Duplicate output column name {m.output_column!r}",
                )
            )
        seen_output[m.output_column] = m.input_column
    return errors


def _parse_dataframe(content: bytes, filename: str, sheet_name: str | None = None):
    """Parse bytes into a pandas DataFrame with encoding fallback."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    encoding_used = "utf-8"
    encoding_warnings: list[str] = []

    if suffix == "xlsx":
        import io

        df = pd.read_excel(
            io.BytesIO(content), sheet_name=sheet_name or 0, dtype=object
        )
        available_sheets: list[str] = []
        if sheet_name is None:
            xf = pd.ExcelFile(io.BytesIO(content))
            available_sheets = xf.sheet_names
        return df, available_sheets, encoding_used, encoding_warnings

    # CSV — try UTF-8, fall back to latin-1
    import io

    try:
        df = pd.read_csv(io.BytesIO(content), dtype=object)
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(content), encoding="latin-1", dtype=object)
        encoding_used = "latin-1"
        null_like = (
            df.select_dtypes(include="object")
            .apply(lambda s: s.str.contains("Ã", na=False).sum())
            .sum()
        )
        if null_like:
            encoding_warnings.append(
                f"File decoded as latin-1; {int(null_like)} characters may render incorrectly"
            )
    return df, [], encoding_used, encoding_warnings


def _build_detected_columns(df: pd.DataFrame) -> list[DetectedColumn]:
    columns = []
    for col in df.columns:
        series = df[col].dropna()
        sample = [str(v) for v in series.head(5).tolist()]
        null_count = int(df[col].isna().sum())
        inferred = "string"
        if series.empty:
            inferred = "unknown"
        else:
            try:
                pd.to_numeric(series)
                if all("." in str(v) for v in series.head(20)):
                    inferred = "decimal"
                else:
                    inferred = "integer"
            except (ValueError, TypeError):
                pass
        columns.append(
            DetectedColumn(
                name=str(col),
                inferred_type=inferred,  # type: ignore[arg-type]
                null_count=null_count,
                sample_values=sample,
            )
        )
    return columns


def _dedup_columns(df: pd.DataFrame):
    """Rename duplicate column headers to avoid conflicts."""
    renames: list[dict] = []
    seen: dict[str, int] = {}
    new_cols = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_name = f"{col}_{seen[col]}"
            renames.append({"original": col, "renamed": new_name})
            new_cols.append(new_name)
        else:
            seen[col] = 0
            new_cols.append(col)
    df.columns = new_cols
    return df, renames


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/imports/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportSession,
    summary="Upload CSV or Excel file",
)
async def upload_file(
    workspace_id: str,
    file: UploadFile = File(...),
    service: ImportService = Depends(get_import_service),
    storage: WorkspaceStorage = Depends(get_workspace_storage),
    x_user_id: str = Header(default="system"),
) -> ImportSession:
    _check_workspace(workspace_id, storage)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in ("csv", "xlsx"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: .{suffix}. Only .csv and .xlsx are accepted",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 500MB limit")

    try:
        df, available_sheets, encoding_used, enc_warnings = _parse_dataframe(
            content, file.filename
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Could not parse file: {exc}"
        ) from exc

    if len(df) == 0:
        raise HTTPException(status_code=422, detail="File has 0 data rows")

    df, column_renames = _dedup_columns(df)
    detected = _build_detected_columns(df)
    preview = _df_to_records(df.head(100))

    session = service.create_session(
        workspace_id=workspace_id,
        original_filename=file.filename,
        source_format=suffix,  # type: ignore[arg-type]
        detected_columns=detected,
        row_count=len(df),
        preview_rows=preview,
        available_sheets=available_sheets,
        created_by=x_user_id,
        encoding_used=encoding_used,
        encoding_warnings=enc_warnings,
        column_renames=column_renames or None,
    )

    # Retain original bytes so sheet re-selection can re-parse
    session_dir = service._session_path(workspace_id, session.import_id)
    orig_path = session_dir / f"_orig_{file.filename}"
    orig_path.write_bytes(content)

    # Persist source as parquet for downstream use
    source_path = service._source_parquet_path(workspace_id, session.import_id)
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.register("_src", df)
    conn.execute(f"COPY _src TO '{source_path}' (FORMAT PARQUET)")
    conn.close()

    return session


# ---------------------------------------------------------------------------
# Sheet select (XLSX only)
# ---------------------------------------------------------------------------


@router.patch(
    "/{workspace_id}/imports/{import_id}/sheet",
    response_model=ImportSession,
    summary="Select Excel sheet",
)
async def select_sheet(
    workspace_id: str,
    import_id: str,
    body: SheetSelectRequest,
    service: ImportService = Depends(get_import_service),
) -> ImportSession:
    session = _check_session(workspace_id, import_id, service)
    if body.sheet_name not in session.available_sheets:
        raise HTTPException(
            status_code=422,
            detail=f"Sheet {body.sheet_name!r} not found in {session.available_sheets}",
        )

    source_path = service._source_parquet_path(workspace_id, import_id)
    orig_path = (
        service._session_path(workspace_id, import_id)
        / f"_orig_{session.original_filename}"
    )
    if not orig_path.exists():
        raise HTTPException(
            status_code=422, detail="Original file not retained; cannot re-parse sheet"
        )

    orig_bytes = orig_path.read_bytes()
    df, _, encoding_used, enc_warnings = _parse_dataframe(
        orig_bytes, session.original_filename, sheet_name=body.sheet_name
    )
    df, _ = _dedup_columns(df)
    detected = _build_detected_columns(df)
    preview = _df_to_records(df.head(100))

    import duckdb

    conn = duckdb.connect(":memory:")
    conn.register("_src", df)
    conn.execute(f"COPY _src TO '{source_path}' (FORMAT PARQUET)")
    conn.close()

    session.sheet_name = body.sheet_name
    session.detected_columns = detected
    session.preview_rows = preview
    session.row_count = len(df)
    session.column_count = len(detected)

    service._metadata_path(workspace_id, import_id).write_text(
        session.model_dump_json(indent=2)
    )
    return session


# ---------------------------------------------------------------------------
# Mapping save
# ---------------------------------------------------------------------------


@router.put(
    "/{workspace_id}/imports/{import_id}/mapping",
    response_model=MappingSaveResponse,
    summary="Save field mapping configuration",
)
async def save_mapping(
    workspace_id: str,
    import_id: str,
    body: MappingSaveRequest,
    service: ImportService = Depends(get_import_service),
    x_user_id: str = Header(default="system"),
) -> MappingSaveResponse:
    session = _check_session(workspace_id, import_id, service)
    detected_names = {c.name for c in session.detected_columns}
    validation_errors = _validate_mapping(body.field_mappings, detected_names)

    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail=[e.model_dump() for e in validation_errors],
        )

    for m in body.field_mappings:
        m.import_id = import_id

    updated = service.save_mapping(
        workspace_id, import_id, body.field_mappings, user=x_user_id
    )
    output_count = sum(1 for m in body.field_mappings if not m.is_excluded)
    from datetime import datetime, timezone

    return MappingSaveResponse(
        import_id=import_id,
        status=updated.status,
        mapping_saved_at=updated.mapping_saved_at or datetime.now(timezone.utc),
        validation_errors=validation_errors,
        output_column_count=output_count,
    )


# ---------------------------------------------------------------------------
# Preview (raw)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/imports/{import_id}/preview",
    response_model=PreviewResponse,
    summary="Raw preview (first 100 rows, no mapping applied)",
)
def get_preview(
    workspace_id: str,
    import_id: str,
    service: ImportService = Depends(get_import_service),
) -> PreviewResponse:
    session = _check_session(workspace_id, import_id, service)
    df = service.get_raw_preview(workspace_id, import_id)
    rows = _df_to_records(df)
    return PreviewResponse(
        import_id=import_id,
        columns=list(df.columns),
        rows=rows,
        total_row_count=session.row_count,
        preview_row_count=len(rows),
    )


# ---------------------------------------------------------------------------
# Suggestions (schema-aware auto-mapping)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/imports/{import_id}/suggestions",
    response_model=SuggestionsResponse,
    summary="Auto-suggest canonical field mappings for uploaded columns",
)
def get_suggestions(
    workspace_id: str,
    import_id: str,
    service: ImportService = Depends(get_import_service),
) -> SuggestionsResponse:
    session = _check_session(workspace_id, import_id, service)

    engine = SuggestionEngine()
    suggestions = engine.suggest(session.detected_columns)

    # Attach format detection for each suggestion with a known canonical field
    for suggestion in suggestions:
        if suggestion.suggested_canonical_field is None:
            continue
        field_def = get_field(suggestion.suggested_canonical_field)
        if field_def is None:
            continue
        input_col = next(
            (c for c in session.detected_columns if c.name == suggestion.input_column),
            None,
        )
        if input_col is None:
            continue
        suggestion.format_detection = engine.detect_format(input_col, field_def)

    # Check for auto-fingerprint from prior successful imports
    fingerprint = SuggestionEngine.get_auto_fingerprint(
        [c.name for c in session.detected_columns]
    )
    auto_path = service._templates_path(workspace_id) / f"_auto_{fingerprint}.json"
    if auto_path.exists():
        import json as _json

        stored_mappings = _json.loads(auto_path.read_text())
        stored_map = {m["input_column"]: m["output_column"] for m in stored_mappings}
        for suggestion in suggestions:
            if suggestion.input_column in stored_map:
                suggestion.suggested_canonical_field = stored_map[
                    suggestion.input_column
                ]
                suggestion.confidence = "high"
                suggestion.confidence_score = 1.0
                suggestion.reason = "prior_mapping"

    data_quality = engine.scan_data_quality(session, suggestions)

    schema_payload = [
        {
            "field_name": f.field_name,
            "required": f.required,
            "data_type": f.data_type,
            "description": f.description,
        }
        for f in FIELDS
    ]

    return SuggestionsResponse(
        import_id=import_id,
        suggestions=suggestions,
        data_quality=data_quality,
        canonical_schema=schema_payload,
    )


# ---------------------------------------------------------------------------
# Preview (mapped)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/imports/{import_id}/mapped-preview",
    response_model=MappedPreviewResponse,
    summary="Mapped preview (first 100 rows with transforms applied)",
)
def get_mapped_preview(
    workspace_id: str,
    import_id: str,
    service: ImportService = Depends(get_import_service),
) -> MappedPreviewResponse:
    session = _check_session(workspace_id, import_id, service)
    if service.get_mapping(workspace_id, import_id) is None:
        raise HTTPException(
            status_code=409, detail="No mapping saved yet; save a mapping first"
        )
    df, warnings = service.get_mapped_preview(workspace_id, import_id)
    rows = _df_to_records(df)
    return MappedPreviewResponse(
        import_id=import_id,
        columns=list(df.columns),
        rows=rows,
        total_row_count=session.row_count,
        preview_row_count=len(rows),
        transformation_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Get session status
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/imports/{import_id}",
    response_model=ImportSession,
    summary="Get import session status",
)
def get_import_status(
    workspace_id: str,
    import_id: str,
    service: ImportService = Depends(get_import_service),
) -> ImportSession:
    return _check_session(workspace_id, import_id, service)


# ---------------------------------------------------------------------------
# Generate Parquet
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/imports/{import_id}/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerateResponse,
    summary="Generate Parquet from saved mapping",
)
def generate_parquet(
    workspace_id: str,
    import_id: str,
    service: ImportService = Depends(get_import_service),
    storage: WorkspaceStorage = Depends(get_workspace_storage),
    x_user_id: str = Header(default="system"),
) -> GenerateResponse:
    session = _check_session(workspace_id, import_id, service)

    if service.get_mapping(workspace_id, import_id) is None:
        raise HTTPException(
            status_code=409, detail="No mapping saved; save a mapping before generating"
        )

    service.update_status(workspace_id, import_id, "generating")

    from datetime import datetime, timezone

    started_at = datetime.now(timezone.utc)
    try:
        parquet_file = service.generate_parquet(import_id, workspace_id, user=x_user_id)
    except Exception as exc:
        # detail=str(exc) exposes internal errors — future: map exceptions to user-facing messages
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Point the workspace census at the freshly generated parquet so scenarios
    # pick it up without a separate "Use as Census" step (mirrors the upload flow).
    census_path_set = False
    try:
        census_path_set = storage.update_base_config_key(
            workspace_id=workspace_id,
            key_path="setup.census_parquet_path",
            value=parquet_file.storage_path,
        )
        if not census_path_set:
            logger.warning(
                "Generated parquet but could not update census path for workspace %s",
                workspace_id,
            )
    except Exception as exc:
        # Don't fail the import if the config update fails — the file is generated
        # and can still be assigned via "Use as Census".
        logger.warning("Failed to set census path after parquet generation: %s", exc)

    return GenerateResponse(
        import_id=import_id,
        correlation_id=session.correlation_id,
        status="completed",
        started_at=started_at,
        storage_path=parquet_file.storage_path,
        census_path_set=census_path_set,
    )


# ---------------------------------------------------------------------------
# Parquet file management
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/parquet-files",
    response_model=ParquetFilesResponse,
    summary="List all generated Parquet files in workspace",
)
def list_parquet_files(
    workspace_id: str,
    service: ImportService = Depends(get_import_service),
    storage: WorkspaceStorage = Depends(get_workspace_storage),
) -> ParquetFilesResponse:
    _check_workspace(workspace_id, storage)
    files = service.list_parquet_files(workspace_id)
    files_sorted = sorted(files, key=lambda f: f.created_at, reverse=True)
    return ParquetFilesResponse(
        parquet_files=files_sorted, total_count=len(files_sorted)
    )


@router.get(
    "/{workspace_id}/parquet-files/{file_id}/download",
    summary="Download a Parquet file",
)
def download_parquet_file(
    workspace_id: str,
    file_id: str,
    service: ImportService = Depends(get_import_service),
) -> FileResponse:
    pf = service.get_parquet_file(workspace_id, file_id)
    if pf is None:
        raise HTTPException(status_code=404, detail="Parquet file not found")
    storage_path = Path(pf.storage_path)
    if not storage_path.exists():
        raise HTTPException(status_code=404, detail="Parquet file not found on disk")
    return FileResponse(
        path=str(storage_path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{pf.filename}"'},
    )


@router.delete(
    "/{workspace_id}/parquet-files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Parquet file (workspace creator only)",
)
def delete_parquet_file(
    workspace_id: str,
    file_id: str,
    service: ImportService = Depends(get_import_service),
    x_user_id: str = Header(default="system"),
) -> None:
    pf = service.get_parquet_file(workspace_id, file_id)
    if pf is None:
        raise HTTPException(status_code=404, detail="Parquet file not found")
    if pf.created_by != x_user_id:
        raise HTTPException(
            status_code=403, detail="Only the file creator can delete it"
        )
    service.delete_parquet_file(workspace_id, file_id, user=x_user_id)


# ---------------------------------------------------------------------------
# Mapping templates
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/mapping-templates",
    response_model=MappingTemplatesResponse,
    summary="List mapping templates",
)
def list_mapping_templates(
    workspace_id: str,
    service: ImportService = Depends(get_import_service),
    storage: WorkspaceStorage = Depends(get_workspace_storage),
) -> MappingTemplatesResponse:
    _check_workspace(workspace_id, storage)
    templates = service.list_templates(workspace_id)
    return MappingTemplatesResponse(templates=templates)


@router.post(
    "/{workspace_id}/mapping-templates",
    status_code=status.HTTP_201_CREATED,
    response_model=SaveTemplateResponse,
    summary="Save mapping as reusable template",
)
def save_mapping_template(
    workspace_id: str,
    body: SaveTemplateRequest,
    service: ImportService = Depends(get_import_service),
    x_user_id: str = Header(default="system"),
) -> SaveTemplateResponse:
    _check_session(workspace_id, body.import_id, service)
    try:
        template = service.save_template(
            workspace_id=workspace_id,
            import_id=body.import_id,
            name=body.name,
            description=body.description,
            user=x_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SaveTemplateResponse(
        template_id=template.template_id,
        name=template.name,
        created_at=template.created_at,
    )


@router.post(
    "/{workspace_id}/imports/{import_id}/apply-template",
    response_model=MappingSaveResponse,
    summary="Apply a saved template to this import session",
)
def apply_template(
    workspace_id: str,
    import_id: str,
    body: ApplyTemplateRequest,
    service: ImportService = Depends(get_import_service),
    x_user_id: str = Header(default="system"),
) -> MappingSaveResponse:
    _check_session(workspace_id, import_id, service)
    try:
        updated = service.apply_template(
            workspace_id, import_id, body.template_id, user=x_user_id
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    mappings = service.get_mapping(workspace_id, import_id) or []
    output_count = sum(1 for m in mappings if not m.is_excluded)
    from datetime import datetime, timezone

    return MappingSaveResponse(
        import_id=import_id,
        status=updated.status,
        mapping_saved_at=updated.mapping_saved_at or datetime.now(timezone.utc),
        validation_errors=[],
        output_column_count=output_count,
    )
