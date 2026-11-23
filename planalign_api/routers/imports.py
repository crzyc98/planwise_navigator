"""Data import endpoints — upload CSV/Excel, configure field mappings, generate Parquet."""

from __future__ import annotations

import io
import logging
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

import duckdb
import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response

from ..config import APISettings, get_settings
from ..errors import sanitize_error
from ..models.imports import (
    ApplyTemplateRequest,
    CensusAsOfDateRequest,
    DetectedColumn,
    GenerateResponse,
    ImportSession,
    MappedPreviewResponse,
    MappingSaveRequest,
    MappingSaveResponse,
    MappingTemplatesResponse,
    ParquetFile,
    ParquetFilesResponse,
    PreviewResponse,
    SaveTemplateRequest,
    SaveTemplateResponse,
    SheetSelectRequest,
    SuggestionsResponse,
)
from ..services.census_activation import (
    activate_census,
    is_active_census,
    prefill_as_of,
    set_active_census_as_of,
)
from ..services.census_schema import FIELDS, get_field
from ..services.import_service import ImportService
from ..services.mapping_engine import MappingError
from ..services.mapping_validation import MappingValidationFailed, validate_mappings
from ..services.suggestion_engine import SuggestionEngine
from ..services.upload_stream import stream_upload_to_tempfile
from ..storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
IMPORT_FILE_TYPES = ("csv", "xlsx")
# Shape limits for a parsed upload; the unpacked .xlsx size is a setting.
XLSX_MAX_MEMBERS = 2_000
MAX_IMPORT_COLUMNS = 500
MAX_HEADER_LENGTH = 256
MAX_IMPORT_ROWS = 2_000_000


class UploadShapeError(ValueError):
    """An upload is over a size or shape limit; the message is safe to show."""


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-safe list of dicts (handles NaT, Timestamp, NaN)."""
    import math

    records = []
    for row in df.to_dict(orient="records"):
        clean: dict = {}
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


def _pandas_source(source: bytes | Path) -> Path | io.BytesIO:
    """Return a fresh pandas-compatible input for a byte or file source."""
    return source if isinstance(source, Path) else io.BytesIO(source)


def _check_xlsx_archive(source: bytes | Path) -> None:
    """Reject workbooks whose archive is too large or has too many parts."""
    limit = get_settings().import_xlsx_max_unpacked_bytes
    try:
        with zipfile.ZipFile(_pandas_source(source)) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise UploadShapeError("The file is not a valid .xlsx workbook.") from exc
    if len(members) > XLSX_MAX_MEMBERS:
        raise UploadShapeError(
            f"The workbook has more than {XLSX_MAX_MEMBERS} internal parts."
        )
    if sum(member.file_size for member in members) > limit:
        raise UploadShapeError(
            f"The workbook is larger than {limit // (1024 * 1024)} MiB once unpacked."
        )


def _check_frame_shape(df: pd.DataFrame) -> None:
    """Reject parsed uploads with too many columns or rows, or long headers."""
    if len(df.columns) > MAX_IMPORT_COLUMNS:
        raise UploadShapeError(f"The file has more than {MAX_IMPORT_COLUMNS} columns.")
    if any(len(str(col)) > MAX_HEADER_LENGTH for col in df.columns):
        raise UploadShapeError(
            f"A column header is longer than {MAX_HEADER_LENGTH} characters."
        )
    if len(df) > MAX_IMPORT_ROWS:
        raise UploadShapeError(f"The file has more than {MAX_IMPORT_ROWS:,} data rows.")


def _parse_excel(
    source: bytes | Path, sheet_name: str | None
) -> tuple[pd.DataFrame, list[str]]:
    """Read one sheet, listing the sheets too when none was chosen."""
    _check_xlsx_archive(source)
    with pd.ExcelFile(_pandas_source(source)) as workbook:
        sheets = (
            [str(name) for name in workbook.sheet_names] if sheet_name is None else []
        )
        df = workbook.parse(
            sheet_name=sheet_name or 0, dtype=object, nrows=MAX_IMPORT_ROWS + 1
        )
    return df, sheets


def _parse_csv(source: bytes | Path) -> tuple[pd.DataFrame, str, list[str]]:
    """Read a CSV as UTF-8, falling back to latin-1."""
    try:
        df = pd.read_csv(
            _pandas_source(source), dtype=object, nrows=MAX_IMPORT_ROWS + 1
        )
        return df, "utf-8", []
    except UnicodeDecodeError:
        df = pd.read_csv(
            _pandas_source(source),
            encoding="latin-1",
            dtype=object,
            nrows=MAX_IMPORT_ROWS + 1,
        )
    warnings: list[str] = []
    null_like = (
        df.select_dtypes(include="object")
        .apply(lambda s: s.str.contains("Ã", na=False).sum())
        .sum()
    )
    if null_like:
        warnings.append(
            f"File decoded as latin-1; {int(null_like)} characters may render incorrectly"
        )
    return df, "latin-1", warnings


def _parse_dataframe(
    source: bytes | Path, filename: str, sheet_name: str | None = None
) -> tuple[pd.DataFrame, list[str], str, list[str]]:
    """Parse an uploaded file into a DataFrame and check its shape.

    Returns the frame, the workbook's sheet names (xlsx, no sheet chosen),
    the encoding used, and encoding warnings. Raises UploadShapeError when the
    upload is over a limit.
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    available_sheets: list[str] = []
    encoding_used = "utf-8"
    encoding_warnings: list[str] = []
    if suffix == "xlsx":
        df, available_sheets = _parse_excel(source, sheet_name)
    else:
        df, encoding_used, encoding_warnings = _parse_csv(source)
    _check_frame_shape(df)
    return df, available_sheets, encoding_used, encoding_warnings


def _parse_upload(
    source: bytes | Path, filename: str, sheet_name: str | None = None
) -> tuple[pd.DataFrame, list[str], str, list[str]]:
    """``_parse_dataframe`` with client-safe 422 errors."""
    try:
        return _parse_dataframe(source, filename, sheet_name=sheet_name)
    except UploadShapeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=sanitize_error(logger, "Could not parse file"),
        ) from exc


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


def _retained_original_path(session_dir: Path, source_format: str) -> Path:
    """Return the fixed on-disk path for a session's retained original upload."""
    if source_format not in IMPORT_FILE_TYPES:
        raise ValueError(f"Unsupported import format: {source_format!r}")
    return session_dir / f"_orig.{source_format}"


def _find_retained_original(session_dir: Path, session: ImportSession) -> Path | None:
    """Locate a session's retained original upload, supporting legacy names."""
    current = _retained_original_path(session_dir, session.source_format)
    if not current.is_symlink() and current.is_file():
        return current

    legacy_name = f"_orig_{session.original_filename}"
    if "\x00" in legacy_name or "/" in legacy_name or "\\" in legacy_name:
        return None
    legacy = session_dir / legacy_name
    if legacy.is_symlink():
        return None
    try:
        resolved_dir = session_dir.resolve()
        resolved_legacy = legacy.resolve()
    except OSError:
        return None
    if resolved_legacy.parent != resolved_dir or not resolved_legacy.is_file():
        return None
    return resolved_legacy


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
    if suffix not in IMPORT_FILE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: .{suffix}. Only .csv and .xlsx are accepted",
        )

    # Cleared once the file is moved into the session directory, so the
    # cleanup in `finally` does not delete the retained original.
    temp_path: Path | None
    temp_path, _ = await stream_upload_to_tempfile(
        file,
        suffix=f".{suffix}",
        max_file_bytes=MAX_UPLOAD_BYTES,
    )
    try:
        df, available_sheets, encoding_used, enc_warnings = _parse_upload(
            temp_path, file.filename
        )

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

        # Retain the original file so sheet re-selection can re-parse it.
        session_dir = service._session_path(workspace_id, session.import_id)
        orig_path = _retained_original_path(session_dir, suffix)
        shutil.move(str(temp_path), orig_path)
        temp_path = None

        # Persist source as parquet for downstream use
        source_path = service._source_parquet_path(workspace_id, session.import_id)
        import duckdb

        conn = duckdb.connect(":memory:")
        conn.register("_src", df)
        conn.execute(f"COPY _src TO '{source_path}' (FORMAT PARQUET)")
        conn.close()

        return session
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Sheet select (XLSX only)
# ---------------------------------------------------------------------------


@router.patch(
    "/{workspace_id}/imports/{import_id}/sheet",
    response_model=ImportSession,
    summary="Select Excel sheet",
)
def select_sheet(
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
    session_dir = service._session_path(workspace_id, import_id)
    orig_path = _find_retained_original(session_dir, session)
    if orig_path is None:
        raise HTTPException(
            status_code=422, detail="Original file not retained; cannot re-parse sheet"
        )

    df, _, encoding_used, enc_warnings = _parse_upload(
        orig_path, session.original_filename, sheet_name=body.sheet_name
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
def save_mapping(
    workspace_id: str,
    import_id: str,
    body: MappingSaveRequest,
    service: ImportService = Depends(get_import_service),
    x_user_id: str = Header(default="system"),
) -> MappingSaveResponse:
    session = _check_session(workspace_id, import_id, service)
    detected_names = {c.name for c in session.detected_columns}
    validation_errors = validate_mappings(body.field_mappings, detected_names)

    from datetime import datetime, timezone

    # Soft validation: invalid mappings return 200 with a populated
    # validation_errors list (rendered inline by the Studio UI) rather than a
    # hard 422. The mapping is NOT persisted while errors remain.
    if validation_errors:
        return MappingSaveResponse(
            import_id=import_id,
            status=session.status,
            mapping_saved_at=session.mapping_saved_at or datetime.now(timezone.utc),
            validation_errors=validation_errors,
            output_column_count=0,
        )

    for m in body.field_mappings:
        m.import_id = import_id

    updated = service.save_mapping(
        workspace_id, import_id, body.field_mappings, user=x_user_id
    )
    output_count = sum(1 for m in body.field_mappings if not m.is_excluded)

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

    # Detect date order for all columns, including fields mapped manually.
    for suggestion in suggestions:
        input_col = next(
            (c for c in session.detected_columns if c.name == suggestion.input_column),
            None,
        )
        if input_col is None:
            continue
        field_def = (
            get_field(suggestion.suggested_canonical_field)
            if suggestion.suggested_canonical_field
            else None
        )
        sample_date = engine.detect_date_format(input_col.sample_values)
        if field_def is None and sample_date is None:
            continue
        if field_def is None or field_def.data_type == "date" or sample_date:
            input_col = input_col.model_copy(
                update={
                    "sample_values": service.get_source_column_values(
                        workspace_id, import_id, input_col.name
                    )
                }
            )
        if field_def is None or (field_def.data_type != "date" and sample_date):
            suggestion.format_detection = engine.detect_date_format(
                input_col.sample_values
            )
        else:
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
    storage: WorkspaceStorage = Depends(get_workspace_storage),
) -> MappedPreviewResponse:
    session = _check_session(workspace_id, import_id, service)
    if service.get_mapping(workspace_id, import_id) is None:
        raise HTTPException(
            status_code=409, detail="No mapping saved yet; save a mapping first"
        )
    # One read of the upload serves both the preview and the whole-file checks.
    source = service.read_source(workspace_id, import_id)
    try:
        df, warnings = service.get_mapped_preview(
            workspace_id, import_id, source=source
        )
    except MappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=sanitize_error(logger, "The mapping can't convert this file"),
        ) from exc
    quality = service.get_data_quality(workspace_id, import_id, source=source)
    rows = _df_to_records(df)
    return MappedPreviewResponse(
        import_id=import_id,
        columns=list(df.columns),
        rows=rows,
        total_row_count=session.row_count,
        preview_row_count=len(rows),
        transformation_warnings=warnings,
        data_quality=quality.result,
        data_quality_skipped_reason=quality.skipped_reason,
        suggested_census_as_of_date=prefill_as_of(
            storage, workspace_id, quality.suggested_as_of
        ),
    )


@router.get(
    "/{workspace_id}/imports/{import_id}/flagged-rows",
    summary="Download rows that broke a census plausibility rule (CSV)",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def download_flagged_rows(
    workspace_id: str,
    import_id: str,
    service: ImportService = Depends(get_import_service),
) -> Response:
    """Row number, employee ID and the rules broken; no other row contents."""
    session = _check_session(workspace_id, import_id, service)
    try:
        content = service.get_flagged_rows_csv(workspace_id, import_id)
    except (ValueError, duckdb.IOException) as exc:
        # ValueError: the mapping can't convert the file, or no census year;
        # IOException: generating has already removed the upload.
        raise HTTPException(
            status_code=409,
            detail="Flagged rows aren't available for this import",
        ) from exc
    filename = f"{Path(session.original_filename).stem}_flagged_rows.csv"
    return Response(
        content=content,
        media_type="text/csv",
        # RFC 5987 form: upload names may hold quotes or non-ASCII text.
        headers={
            "Content-Disposition": (
                f"attachment; filename*=utf-8''{quote(filename, safe='')}"
            )
        },
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
    request: CensusAsOfDateRequest,
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
        parquet_file = service.generate_parquet(
            import_id,
            workspace_id,
            user=x_user_id,
            census_as_of_date=request.census_as_of_date,
        )
    except MappingError as exc:
        # Engine-authored message: names columns and row numbers, no cell values.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=sanitize_error(logger, "Failed to generate parquet file"),
        ) from exc

    # Point the workspace census at the freshly generated parquet so scenarios
    # pick it up without a separate "Use as Census" step (mirrors the upload flow).
    census_path_set = False
    try:
        census_path_set = activate_census(
            storage,
            workspace_id,
            parquet_file.storage_path,
            request.census_as_of_date,
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
    storage_path = service.resolve_parquet_path(workspace_id, pf)
    if storage_path is None:
        raise HTTPException(status_code=404, detail="Parquet file not found on disk")
    return FileResponse(
        path=str(storage_path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{storage_path.name}"'},
    )


@router.put(
    "/{workspace_id}/parquet-files/{file_id}/census-as-of-date",
    response_model=ParquetFile,
    summary="Set the date a census file was taken",
)
def set_parquet_census_as_of_date(
    workspace_id: str,
    file_id: str,
    request: CensusAsOfDateRequest,
    service: ImportService = Depends(get_import_service),
    storage: WorkspaceStorage = Depends(get_workspace_storage),
) -> ParquetFile:
    """Store the date on the file, and on the workspace if it's the census in use."""
    _check_workspace(workspace_id, storage)
    pf = service.set_census_as_of_date(workspace_id, file_id, request.census_as_of_date)
    if pf is None:
        raise HTTPException(status_code=404, detail="Parquet file not found")
    resolved = service.resolve_parquet_path(workspace_id, pf)
    if resolved is not None and is_active_census(storage, workspace_id, str(resolved)):
        set_active_census_as_of(storage, workspace_id, pf.census_as_of_date)
    return pf


@router.delete(
    "/{workspace_id}/parquet-files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Parquet file",
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
    except MappingValidationFailed as exc:
        raise HTTPException(
            status_code=422,
            detail=[error.model_dump() for error in exc.errors],
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Template not found") from exc
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
