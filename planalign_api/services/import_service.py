"""ImportService — session lifecycle: create, read, update, mapping, parquet index, audit."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

from ..config import get_settings
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
from .mapping_engine import MappingEngine

logger = logging.getLogger(__name__)


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
        return self._root / workspace_id

    def _imports_path(self, workspace_id: str) -> Path:
        return self._ws_path(workspace_id) / "imports"

    def _session_path(self, workspace_id: str, import_id: str) -> Path:
        return self._imports_path(workspace_id) / import_id

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
        self, import_id: str, workspace_id: str, user: str = "system"
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
        conn = duckdb.connect(":memory:")
        df = conn.execute(f"SELECT * FROM read_parquet('{source_path}')").df()
        conn.close()
        df = _normalize_dtypes_for_duckdb(df)

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
        conn.close()

        schema = [
            ParquetColumn(name=col, type=_infer_output_type(transformed[col]))
            for col in transformed.columns
        ]
        pf = ParquetFile(
            workspace_id=workspace_id,
            import_id=import_id,
            filename=filename,
            storage_path=str(output_path),
            original_filename=session.original_filename,
            row_count=len(transformed),
            file_size_bytes=output_path.stat().st_size,
            schema=schema,
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

    def delete_parquet_file(
        self, workspace_id: str, file_id: str, user: str = "system"
    ) -> bool:
        files = self.list_parquet_files(workspace_id)
        target = next((f for f in files if f.file_id == file_id), None)
        if target is None:
            return False
        storage = Path(target.storage_path)
        if storage.exists():
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
        fp = self._templates_path(workspace_id) / f"{template_id}.json"
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
        self, workspace_id: str, import_id: str, limit: int = 100
    ) -> tuple[pd.DataFrame, List[TransformationWarning]]:
        source_path = self._source_parquet_path(workspace_id, import_id)
        conn = duckdb.connect(":memory:")
        df = conn.execute(
            f"SELECT * FROM read_parquet('{source_path}') LIMIT {limit}"
        ).df()
        conn.close()
        mappings = self.get_mapping(workspace_id, import_id)
        if not mappings:
            raise ValueError("No mapping saved")
        return self._engine.apply_preview(df.head(limit), mappings)


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
