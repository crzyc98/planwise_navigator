"""ImportService — session lifecycle: create, read, update, mapping, parquet index, audit."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
from pydantic import ValidationError

from planalign_orchestrator.census_hourly_rate import summarize_hourly_rates

from ..config import get_settings
from ..models.files import CensusHourlyRateSummary
from ..models.imports import (
    DetectedColumn,
    FieldMapping,
    ImportSession,
    ImportStatusLiteral,
    MappingTemplate,
    MappingTemplateSummary,
    ParquetColumn,
    ParquetFile,
    TransformationWarning,
)
from .census_analysis_service import CensusAnalysisService
from .import_quality import FullFileQuality, flagged_rows_csv, scan_data_quality
from .mapping_engine import MappingEngine
from .path_guard import require_safe_path_component, resolve_child_path

logger = logging.getLogger(__name__)


def _after_last_data_dir(stored: str) -> tuple[str, ...]:
    """Path parts after the last ``data`` directory of a stored path, if any."""
    pure = PureWindowsPath(stored) if "\\" in stored else PurePosixPath(stored)
    parts = pure.parts
    indexes = [i for i, part in enumerate(parts) if part == "data"]
    return parts[indexes[-1] + 1 :] if indexes else ()


def _is_foreign_windows_path(stored: str) -> bool:
    """True when ``stored`` uses Windows syntax on a POSIX host."""
    if os.name == "nt":
        return False
    return "\\" in stored or bool(PureWindowsPath(stored).drive)


def _contained_parquet(
    candidate: Path, data_dir: Path, *, must_exist: bool
) -> Optional[Path]:
    """Return ``candidate`` resolved inside ``data_dir`` if it is a safe parquet path."""
    if candidate.is_symlink():
        return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved.suffix.lower() != ".parquet" or not resolved.is_relative_to(data_dir):
        return None
    if must_exist:
        return resolved if resolved.is_file() else None
    return None if resolved.is_dir() else resolved


def resolve_workspace_parquet_path(
    workspace_path: Path,
    pf: ParquetFile,
    *,
    reroot: bool = True,
    must_exist: bool = True,
) -> Optional[Path]:
    """Return the record's ``.parquet`` file if it is inside the workspace ``data/``.

    Every candidate is resolved, following symlinks, before the containment
    check. With ``reroot``, a path from a moved or exported workspace (POSIX
    or Windows) is retried as the part after its last ``data`` component and
    must exist on disk. Records failing containment are logged at warning
    level and treated as not found.
    """
    stored = pf.storage_path
    if not stored or "\x00" in stored:
        logger.warning(
            "Ignoring parquet file record %s in workspace %s: invalid storage path",
            pf.file_id,
            workspace_path.name,
        )
        return None

    data_dir = (workspace_path / "data").resolve()
    direct_contained: Optional[Path] = None
    if not _is_foreign_windows_path(stored):
        direct_contained = _contained_parquet(
            data_dir / stored, data_dir, must_exist=False
        )
        if direct_contained is not None and direct_contained.is_file():
            return direct_contained

    if reroot:
        tail = _after_last_data_dir(stored)
        if tail and ".." not in tail:
            rerooted = _contained_parquet(
                data_dir.joinpath(*tail), data_dir, must_exist=True
            )
            if rerooted is not None:
                return rerooted

    if direct_contained is not None:
        return None if must_exist else direct_contained

    logger.warning(
        "Ignoring parquet file record %s in workspace %s: path is outside workspace data directory",
        pf.file_id,
        workspace_path.name,
    )
    return None


def _load_index_entries(index_path: Path, workspace_id: str) -> Optional[List[Any]]:
    """Load JSON entries from ``index_path``, resetting unreadable files to ``[]``."""
    try:
        raw_entries = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Resetting unreadable imports index in workspace %s: %s", workspace_id, exc
        )
        index_path.write_text("[]", encoding="utf-8")
        return None
    if not isinstance(raw_entries, list):
        logger.warning(
            "Resetting invalid imports index in workspace %s: expected a list",
            workspace_id,
        )
        index_path.write_text("[]", encoding="utf-8")
        return None
    return raw_entries


def sanitize_parquet_index(workspace_path: Path, workspace_id: str) -> int:
    """Rewrite imported ``data/imports/index.json`` records to stay inside the workspace.

    Valid records whose files exist under ``workspace_path / 'data'`` are
    rewritten with the new workspace ID and resolved local path; records that
    fail validation or point outside the workspace are dropped.

    Returns the number of dropped records.
    """
    index_path = workspace_path / "data" / "imports" / "index.json"
    if index_path.is_symlink():
        logger.warning(
            "Removing disallowed symlink at %s in workspace %s",
            index_path.name,
            workspace_id,
        )
        index_path.unlink()
        return 1
    if not index_path.exists():
        return 0

    raw_entries = _load_index_entries(index_path, workspace_id)
    if raw_entries is None:
        return 1

    kept: List[Dict[str, Any]] = []
    dropped = 0
    for entry in raw_entries:
        try:
            pf = ParquetFile.model_validate(entry)
        except (ValidationError, TypeError) as exc:
            logger.warning(
                "Dropping malformed parquet record in workspace %s: %s",
                workspace_id,
                exc,
            )
            dropped += 1
            continue
        resolved = resolve_workspace_parquet_path(
            workspace_path, pf, reroot=True, must_exist=True
        )
        if resolved is None:
            dropped += 1
            continue
        rewritten = pf.model_copy(
            update={
                "workspace_id": workspace_id,
                "storage_path": str(resolved),
                "filename": resolved.name,
            }
        )
        kept.append(json.loads(rewritten.model_dump_json()))

    index_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    return dropped


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportService:
    """Session lifecycle and filesystem persistence for data import sessions."""

    def __init__(self, workspaces_root: Optional[Path] = None) -> None:
        self._root = workspaces_root or get_settings().workspaces_root
        self._engine = MappingEngine()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _ws_path(self, workspace_id: str) -> Path:
        return resolve_child_path(self._root, workspace_id, label="workspace_id")

    def _imports_path(self, workspace_id: str) -> Path:
        return self._ws_path(workspace_id) / "imports"

    def _session_path(self, workspace_id: str, import_id: str) -> Path:
        return resolve_child_path(
            self._imports_path(workspace_id), import_id, label="import_id"
        )

    def _metadata_path(self, workspace_id: str, import_id: str) -> Path:
        return self._session_path(workspace_id, import_id) / "metadata.json"

    def _mapping_path(self, workspace_id: str, import_id: str) -> Path:
        return self._session_path(workspace_id, import_id) / "mapping.json"

    def _source_parquet_path(self, workspace_id: str, import_id: str) -> Path:
        return self._session_path(workspace_id, import_id) / "source.parquet"

    def _data_imports_path(self, workspace_id: str) -> Path:
        return self._ws_path(workspace_id) / "data" / "imports"

    def _index_path(self, workspace_id: str) -> Path:
        return self._data_imports_path(workspace_id) / "index.json"

    def _audit_log_path(self, workspace_id: str) -> Path:
        return self._data_imports_path(workspace_id) / "audit.log"

    def _templates_path(self, workspace_id: str) -> Path:
        return self._ws_path(workspace_id) / "templates" / "imports"

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _write_audit_log(
        self,
        workspace_id: str,
        action: str,
        import_id: str,
        filename: str,
        row_count: int,
        user: str,
        mapping_config: Dict[str, Any],
        error_message: Optional[str] = None,
    ) -> None:
        log_path = self._audit_log_path(workspace_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry: Dict[str, Any] = {
            "timestamp": _utcnow().isoformat(),
            "action": action,
            "import_id": import_id,
            "filename": filename,
            "row_count": row_count,
            "user": user,
            "mapping_config": mapping_config,
        }
        if error_message is not None:
            entry["error_message"] = error_message
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def create_session(
        self,
        workspace_id: str,
        original_filename: str,
        source_format: str,
        detected_columns: List[DetectedColumn],
        row_count: int,
        preview_rows: List[Dict[str, Any]],
        sheet_name: Optional[str] = None,
        available_sheets: Optional[List[str]] = None,
        created_by: str = "system",
        encoding_used: str = "utf-8",
        encoding_warnings: Optional[List[str]] = None,
        column_renames: Optional[List[Dict[str, str]]] = None,
    ) -> ImportSession:
        session = ImportSession(
            workspace_id=workspace_id,
            original_filename=original_filename,
            source_format=source_format,  # type: ignore[arg-type]
            sheet_name=sheet_name,
            available_sheets=available_sheets or [],
            detected_columns=detected_columns,
            row_count=row_count,
            column_count=len(detected_columns),
            preview_rows=preview_rows,
            created_by=created_by,
            encoding_used=encoding_used,
            encoding_warnings=encoding_warnings or [],
        )
        session_path = self._session_path(workspace_id, session.import_id)
        session_path.mkdir(parents=True, exist_ok=True)

        metadata = session.model_dump(mode="json")
        if column_renames:
            metadata["column_renames"] = column_renames
        self._metadata_path(workspace_id, session.import_id).write_text(
            json.dumps(metadata, default=str, indent=2)
        )
        self._write_audit_log(
            workspace_id=workspace_id,
            action="session_create",
            import_id=session.import_id,
            filename=original_filename,
            row_count=row_count,
            user=created_by,
            mapping_config={},
        )
        return session

    def get_session(self, workspace_id: str, import_id: str) -> Optional[ImportSession]:
        metadata_path = self._metadata_path(workspace_id, import_id)
        if not metadata_path.exists():
            return None
        data = json.loads(metadata_path.read_text())
        return ImportSession.model_validate(data)

    def update_status(
        self,
        workspace_id: str,
        import_id: str,
        status: ImportStatusLiteral,
        error_message: Optional[str] = None,
        parquet_file_id: Optional[str] = None,
    ) -> ImportSession:
        session = self.get_session(workspace_id, import_id)
        if session is None:
            raise FileNotFoundError(f"Import session {import_id!r} not found")
        session.status = status
        if error_message is not None:
            session.error_message = error_message
        if parquet_file_id is not None:
            session.parquet_file_id = parquet_file_id
        self._metadata_path(workspace_id, import_id).write_text(
            json.dumps(session.model_dump(mode="json"), default=str, indent=2)
        )
        return session

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def save_mapping(
        self,
        workspace_id: str,
        import_id: str,
        field_mappings: List[FieldMapping],
        user: str = "system",
    ) -> ImportSession:
        mappings_data = [m.model_dump(mode="json") for m in field_mappings]
        self._mapping_path(workspace_id, import_id).write_text(
            json.dumps(mappings_data, default=str, indent=2)
        )
        session = self.update_status(workspace_id, import_id, "mapping_in_progress")
        session.mapping_saved_at = _utcnow()
        self._metadata_path(workspace_id, import_id).write_text(
            json.dumps(session.model_dump(mode="json"), default=str, indent=2)
        )
        self._write_audit_log(
            workspace_id=workspace_id,
            action="mapping_save",
            import_id=import_id,
            filename=session.original_filename,
            row_count=session.row_count,
            user=user,
            mapping_config={"field_count": len(field_mappings)},
        )
        return session

    def get_mapping(
        self, workspace_id: str, import_id: str
    ) -> Optional[List[FieldMapping]]:
        mapping_path = self._mapping_path(workspace_id, import_id)
        if not mapping_path.exists():
            return None
        data = json.loads(mapping_path.read_text())
        return [FieldMapping.model_validate(m) for m in data]

    # ------------------------------------------------------------------
    # Parquet generation
    # ------------------------------------------------------------------

    def generate_parquet(
        self,
        import_id: str,
        workspace_id: str,
        user: str = "system",
        census_as_of_date: Optional[date] = None,
    ) -> ParquetFile:
        session = self.get_session(workspace_id, import_id)
        if session is None:
            raise FileNotFoundError(f"Import session {import_id!r} not found")

        mappings = self.get_mapping(workspace_id, import_id)
        if not mappings:
            raise ValueError("No mapping saved; cannot generate parquet")

        from .census_schema import get_required_fields

        mapped_outputs = {m.output_column for m in mappings if not m.is_excluded}
        missing = [f for f in get_required_fields() if f not in mapped_outputs]
        if missing:
            raise ValueError(
                f"Required census fields not mapped: {', '.join(missing)}. "
                "All required fields must be mapped before generating parquet."
            )

        source_path = self._source_parquet_path(workspace_id, import_id)
        df = self.read_source(workspace_id, import_id)

        try:
            transformed = self._engine.apply(df, mappings)
        except Exception as exc:
            self.update_status(
                workspace_id, import_id, "failed", error_message=str(exc)
            )
            self._write_audit_log(
                workspace_id=workspace_id,
                action="generate_failure",
                import_id=import_id,
                filename=session.original_filename,
                row_count=session.row_count,
                user=user,
                mapping_config={"field_count": len(mappings)},
                error_message=str(exc),
            )
            raise

        timestamp = _utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(
            c if c.isalnum() or c in "-_." else "_" for c in session.original_filename
        )
        filename = f"{timestamp}_{safe_name}.parquet"
        output_dir = self._data_imports_path(workspace_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename

        transformed = _normalize_dtypes_for_duckdb(transformed)
        conn = duckdb.connect(":memory:")
        conn.register("_transformed", transformed)
        conn.execute(f"COPY _transformed TO '{output_path}' (FORMAT PARQUET)")
        hourly_rates = summarize_hourly_rates(
            conn, "_transformed", list(transformed.columns)
        )
        conn.close()

        schema = [
            ParquetColumn(name=col, type=_infer_output_type(transformed[col]))
            for col in transformed.columns
        ]
        pf = ParquetFile(
            workspace_id=workspace_id,
            import_id=import_id,
            filename=filename,
            storage_path=str(output_path.resolve()),
            original_filename=session.original_filename,
            row_count=len(transformed),
            file_size_bytes=output_path.stat().st_size,
            schema=schema,
            hourly_rate_summary=(
                CensusHourlyRateSummary.model_validate(asdict(hourly_rates))
                if hourly_rates
                else None
            ),
            census_as_of_date=census_as_of_date,
            created_by=user,
        )
        self.save_parquet_record(workspace_id, pf)
        self.update_status(
            workspace_id, import_id, "completed", parquet_file_id=pf.file_id
        )
        self._write_audit_log(
            workspace_id=workspace_id,
            action="generate_success",
            import_id=import_id,
            filename=session.original_filename,
            row_count=len(transformed),
            user=user,
            mapping_config={"field_count": len(mappings)},
        )
        # Persist auto-fingerprint for repeat-upload detection (T024)
        from .suggestion_engine import SuggestionEngine

        fingerprint = SuggestionEngine.get_auto_fingerprint(
            [c.name for c in session.detected_columns]
        )
        auto_path = self._templates_path(workspace_id) / f"_auto_{fingerprint}.json"
        auto_path.parent.mkdir(parents=True, exist_ok=True)
        auto_path.write_text(
            json.dumps([m.model_dump(mode="json") for m in mappings], indent=2)
        )
        # Cleanup source parquet to reclaim disk space (retain metadata + mapping)
        if source_path.exists():
            source_path.unlink()
        return pf

    # ------------------------------------------------------------------
    # Parquet index
    # ------------------------------------------------------------------

    def save_parquet_record(self, workspace_id: str, pf: ParquetFile) -> None:
        index_path = self._index_path(workspace_id)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        files: List[Dict[str, Any]] = []
        if index_path.exists():
            files = json.loads(index_path.read_text())
        files.append(json.loads(pf.model_dump_json()))
        index_path.write_text(json.dumps(files, indent=2))

    def register_external_parquet(
        self,
        workspace_id: str,
        storage_path: str,
        original_filename: str,
        row_count: int,
        columns: List[str],
        file_size_bytes: int,
        user: str = "system",
        census_as_of_date: Optional[date] = None,
    ) -> ParquetFile:
        """Register a parquet that was produced outside the import wizard.

        Used by the direct census-upload path so the file appears in the
        Imported Files list. Existing index entries pointing at the same
        ``storage_path`` are replaced (the census file is overwritten in place).
        """
        index_path = self._index_path(workspace_id)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        existing: List[Dict[str, Any]] = []
        if index_path.exists():
            existing = json.loads(index_path.read_text())
        existing = [f for f in existing if f.get("storage_path") != storage_path]

        pf = ParquetFile(
            workspace_id=workspace_id,
            import_id="direct-upload",
            filename=Path(storage_path).name,
            storage_path=storage_path,
            original_filename=original_filename,
            row_count=row_count,
            file_size_bytes=file_size_bytes,
            schema=[ParquetColumn(name=c, type="string") for c in columns],
            census_as_of_date=census_as_of_date,
            created_by=user,
        )
        existing.append(json.loads(pf.model_dump_json()))
        index_path.write_text(json.dumps(existing, indent=2))
        return pf

    def list_parquet_files(self, workspace_id: str) -> List[ParquetFile]:
        index_path = self._index_path(workspace_id)
        if not index_path.exists():
            return []
        files = json.loads(index_path.read_text())
        return [ParquetFile.model_validate(f) for f in files]

    def get_parquet_file(
        self, workspace_id: str, file_id: str
    ) -> Optional[ParquetFile]:
        for pf in self.list_parquet_files(workspace_id):
            if pf.file_id == file_id:
                return pf
        return None

    def find_parquet_by_path(
        self, workspace_id: str, storage_path: str
    ) -> Optional[ParquetFile]:
        """The newest record for the file at ``storage_path``.

        Records are resolved like downloads, so relative paths and paths from
        an exported workspace still match.
        """
        raw = Path(storage_path)
        target = (
            raw.resolve()
            if raw.is_absolute()
            else (self._ws_path(workspace_id) / raw).resolve()
        )
        matches = [
            pf
            for pf in self.list_parquet_files(workspace_id)
            if self.resolve_parquet_path(workspace_id, pf) == target
        ]
        return max(matches, key=lambda pf: pf.created_at) if matches else None

    def set_census_as_of_date(
        self, workspace_id: str, file_id: str, as_of: date
    ) -> Optional[ParquetFile]:
        """Store the analyst's as-of date on a file record; None if no such file."""
        files = self.list_parquet_files(workspace_id)
        target = next((f for f in files if f.file_id == file_id), None)
        if target is None:
            return None
        if (
            self.resolve_parquet_path(
                workspace_id, target, reroot=True, must_exist=False
            )
            is None
        ):
            return None
        files = [
            (
                f.model_copy(update={"census_as_of_date": as_of})
                if f.file_id == file_id
                else f
            )
            for f in files
        ]
        self._index_path(workspace_id).write_text(
            json.dumps([json.loads(f.model_dump_json()) for f in files], indent=2)
        )
        return next(f for f in files if f.file_id == file_id)

    def resolve_parquet_path(
        self,
        workspace_id: str,
        pf: ParquetFile,
        *,
        reroot: bool = True,
        must_exist: bool = True,
    ) -> Optional[Path]:
        """Return the record's ``.parquet`` file if it is inside the workspace ``data/``."""
        return resolve_workspace_parquet_path(
            self._ws_path(workspace_id), pf, reroot=reroot, must_exist=must_exist
        )

    def delete_parquet_file(
        self, workspace_id: str, file_id: str, user: str = "system"
    ) -> bool:
        files = self.list_parquet_files(workspace_id)
        target = next((f for f in files if f.file_id == file_id), None)
        if target is None:
            return False
        # No re-rooting: a stale record must never delete a different file
        # that happens to share its name, such as the active census.
        storage = self.resolve_parquet_path(
            workspace_id, target, reroot=False, must_exist=False
        )
        # A record that points outside the workspace is dropped from the index,
        # so it can be cleared, but nothing on disk is touched.
        if storage is not None and storage.is_file():
            storage.unlink()
        remaining = [
            json.loads(f.model_dump_json()) for f in files if f.file_id != file_id
        ]
        self._index_path(workspace_id).write_text(json.dumps(remaining, indent=2))
        self._write_audit_log(
            workspace_id=workspace_id,
            action="file_delete",
            import_id=target.import_id,
            filename=target.original_filename,
            row_count=target.row_count,
            user=user,
            mapping_config={},
        )
        return True

    # ------------------------------------------------------------------
    # Mapping templates
    # ------------------------------------------------------------------

    def save_template(
        self,
        workspace_id: str,
        import_id: str,
        name: str,
        description: Optional[str],
        user: str = "system",
    ) -> MappingTemplate:
        mappings = self.get_mapping(workspace_id, import_id)
        if not mappings:
            raise ValueError("No mapping saved for this import session")
        self.get_session(workspace_id, import_id)

        template = MappingTemplate(
            workspace_id=workspace_id,
            name=name,
            description=description,
            field_mappings=mappings,
            created_by=user,
        )
        tpl_path = self._templates_path(workspace_id)
        tpl_path.mkdir(parents=True, exist_ok=True)
        (tpl_path / f"{template.template_id}.json").write_text(
            json.dumps(template.model_dump(mode="json"), default=str, indent=2)
        )
        return template

    def list_templates(self, workspace_id: str) -> List[MappingTemplateSummary]:
        tpl_path = self._templates_path(workspace_id)
        if not tpl_path.exists():
            return []
        summaries: List[MappingTemplateSummary] = []
        for fp in sorted(tpl_path.glob("*.json")):
            data = json.loads(fp.read_text())
            tpl = MappingTemplate.model_validate(data)
            summaries.append(
                MappingTemplateSummary(
                    template_id=tpl.template_id,
                    name=tpl.name,
                    description=tpl.description,
                    field_count=len(tpl.field_mappings),
                    created_at=tpl.created_at,
                    created_by=tpl.created_by,
                )
            )
        return summaries

    def get_template(
        self, workspace_id: str, template_id: str
    ) -> Optional[MappingTemplate]:
        safe_id = require_safe_path_component(template_id, label="template_id")
        fp = self._templates_path(workspace_id) / f"{safe_id}.json"
        if not fp.exists():
            return None
        return MappingTemplate.model_validate(json.loads(fp.read_text()))

    def apply_template(
        self,
        workspace_id: str,
        import_id: str,
        template_id: str,
        user: str = "system",
    ) -> ImportSession:
        session = self.get_session(workspace_id, import_id)
        if session is None:
            raise FileNotFoundError(f"Import session {import_id!r} not found")
        template = self.get_template(workspace_id, template_id)
        if template is None:
            raise FileNotFoundError(f"Template {template_id!r} not found")
        detected_names = {c.name for c in session.detected_columns}
        matched = [
            FieldMapping(**{**m.model_dump(), "import_id": import_id})
            for m in template.field_mappings
            if m.input_column in detected_names
        ]
        return self.save_mapping(workspace_id, import_id, matched, user=user)

    # ------------------------------------------------------------------
    # Preview helpers
    # ------------------------------------------------------------------

    def get_raw_preview(
        self, workspace_id: str, import_id: str, limit: int = 100
    ) -> pd.DataFrame:
        source_path = self._source_parquet_path(workspace_id, import_id)
        conn = duckdb.connect(":memory:")
        df = conn.execute(
            f"SELECT * FROM read_parquet('{source_path}') LIMIT {limit}"
        ).df()
        conn.close()
        return df

    def get_mapped_preview(
        self,
        workspace_id: str,
        import_id: str,
        limit: int = 100,
        source: Optional[pd.DataFrame] = None,
    ) -> tuple[pd.DataFrame, List[TransformationWarning]]:
        """Map the first ``limit`` rows; pass ``source`` to reuse a frame
        already read with ``read_source``."""
        if source is None:
            source_path = self._source_parquet_path(workspace_id, import_id)
            with duckdb.connect(":memory:") as conn:
                source = conn.execute(
                    f"SELECT * FROM read_parquet(?) LIMIT {int(limit)}",
                    [str(source_path)],
                ).df()
        mappings = self.get_mapping(workspace_id, import_id)
        if not mappings:
            raise ValueError("No mapping saved")
        return self._engine.apply_preview(source.head(limit), mappings)

    def read_source(self, workspace_id: str, import_id: str) -> pd.DataFrame:
        """The whole uploaded file, as stored at upload.

        Raises duckdb.IOException once generating has removed it.
        """
        source_path = self._source_parquet_path(workspace_id, import_id)
        with duckdb.connect(":memory:") as conn:
            df = conn.execute("SELECT * FROM read_parquet(?)", [str(source_path)]).df()
        return _normalize_dtypes_for_duckdb(df)

    def _mapped_source(
        self,
        workspace_id: str,
        import_id: str,
        source: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """The whole file as ``generate_parquet`` would write it.

        Raises ValueError when no mapping is saved or the file can't be
        converted with it.
        """
        mappings = self.get_mapping(workspace_id, import_id)
        if not mappings:
            raise ValueError("No mapping saved")
        if source is None:
            source = self.read_source(workspace_id, import_id)
        return _normalize_dtypes_for_duckdb(self._engine.apply(source, mappings))

    def get_data_quality(
        self,
        workspace_id: str,
        import_id: str,
        source: Optional[pd.DataFrame] = None,
    ) -> FullFileQuality:
        """Whole-file checks matching what Census Analysis shows after import.

        When the mapping can't convert the file, the result is None and the
        reason is the same message generating would fail with.
        """
        try:
            mapped = self._mapped_source(workspace_id, import_id, source)
        except ValueError as exc:
            logger.info("Import %s: whole-file checks skipped", import_id)
            return FullFileQuality(None, f"Whole-file checks didn't run: {exc}")
        return scan_data_quality(mapped, CensusAnalysisService(self._root))

    def get_flagged_rows_csv(self, workspace_id: str, import_id: str) -> str:
        """Rows breaking a plausibility rule, as row number, ID and rule names.

        Raises ValueError when the file can't be checked and duckdb.IOException
        once generating has removed the upload.
        """
        return flagged_rows_csv(
            self._mapped_source(workspace_id, import_id),
            CensusAnalysisService(self._root),
        )

    def get_source_column_values(
        self, workspace_id: str, import_id: str, column: str
    ) -> list[str]:
        """Read distinct source values for column-wide date format detection."""
        source_path = self._source_parquet_path(workspace_id, import_id)
        identifier = column.replace('"', '""')
        with duckdb.connect(":memory:") as conn:
            rows = conn.execute(
                f'SELECT DISTINCT CAST("{identifier}" AS VARCHAR) '
                "FROM read_parquet(?) WHERE "
                f'"{identifier}" IS NOT NULL',
                [str(source_path)],
            ).fetchall()
        return [row[0] for row in rows]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _normalize_dtypes_for_duckdb(df: pd.DataFrame) -> pd.DataFrame:
    """Cast pandas StringDtype columns to object so DuckDB 1.0.0 can register the DataFrame.

    DuckDB's read_parquet().df() returns StringDtype columns; DuckDB cannot re-register those.
    """
    str_cols = [c for c in df.columns if isinstance(df[c].dtype, pd.StringDtype)]
    return df.astype({c: object for c in str_cols}) if str_cols else df


def _infer_output_type(series: pd.Series) -> str:
    dtype = series.dtype
    if dtype == "object":
        return "string"
    if pd.api.types.is_integer_dtype(dtype):
        return "integer"
    if pd.api.types.is_float_dtype(dtype):
        return "decimal"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "timestamp"
    return "string"
