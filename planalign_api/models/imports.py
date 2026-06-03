"""Pydantic v2 models for data import sessions, field mappings, and parquet files."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ImportStatus:
    uploaded = "uploaded"
    mapping_in_progress = "mapping_in_progress"
    generating = "generating"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


ImportStatusLiteral = Literal[
    "uploaded", "mapping_in_progress", "generating", "completed", "failed", "cancelled"
]

InferredType = Literal["string", "integer", "decimal", "boolean", "date", "timestamp", "unknown"]

OutputType = Literal["string", "integer", "decimal", "boolean", "date", "timestamp"]

TransformType = Literal[
    "rename", "string_case", "date_parse", "null_replace", "null_drop", "calculated_field"
]


class DetectedColumn(BaseModel):
    name: str
    inferred_type: InferredType
    null_count: int = Field(default=0, ge=0)
    sample_values: List[str] = Field(default_factory=list)


class Transformation(BaseModel):
    transform_type: TransformType
    params: Dict[str, Any] = Field(default_factory=dict)


class FieldMapping(BaseModel):
    mapping_id: str = Field(default_factory=lambda: str(uuid4()))
    import_id: str = ""
    input_column: str
    output_column: str = Field(..., max_length=128)
    output_type: OutputType
    is_required: bool = False
    is_excluded: bool = False
    transformations: List[Transformation] = Field(default_factory=list)


class ImportSession(BaseModel):
    import_id: str = Field(default_factory=lambda: str(uuid4()))
    correlation_id: str = ""
    workspace_id: str
    original_filename: str = Field(..., max_length=255)
    source_format: Literal["csv", "xlsx"]
    sheet_name: Optional[str] = None
    available_sheets: List[str] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    column_count: int = Field(default=0, ge=0)
    detected_columns: List[DetectedColumn] = Field(default_factory=list)
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)
    status: ImportStatusLiteral = "uploaded"
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    created_by: str = "system"
    mapping_saved_at: Optional[datetime] = None
    parquet_file_id: Optional[str] = None
    error_message: Optional[str] = None
    error_rows: List[Dict[str, Any]] = Field(default_factory=list)
    encoding_warnings: List[str] = Field(default_factory=list)
    encoding_used: str = "utf-8"

    def model_post_init(self, __context: Any) -> None:
        if not self.correlation_id:
            self.correlation_id = self.import_id


class ParquetColumn(BaseModel):
    name: str
    type: OutputType


class ParquetFile(BaseModel):
    file_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    import_id: str
    filename: str
    storage_path: str
    original_filename: str
    row_count: int = Field(default=0, ge=0)
    file_size_bytes: int = Field(default=0, ge=0)
    parquet_schema: List[ParquetColumn] = Field(default_factory=list, alias="schema")
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    created_by: str = "system"

    model_config = {"populate_by_name": True}


class MappingTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    name: str = Field(..., max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    field_mappings: List[FieldMapping] = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    created_by: str = "system"


class ImportErrorResponse(BaseModel):
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    error_code: str
    message: str
    resolution_hint: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)


class TransformationWarning(BaseModel):
    input_column: str
    rows_affected: int
    message: str


class MappingValidationError(BaseModel):
    field: str
    input_column: str
    message: str


class MappingSaveRequest(BaseModel):
    field_mappings: List[FieldMapping]


class MappingSaveResponse(BaseModel):
    import_id: str
    status: ImportStatusLiteral
    mapping_saved_at: datetime
    validation_errors: List[MappingValidationError] = Field(default_factory=list)
    output_column_count: int


class SheetSelectRequest(BaseModel):
    sheet_name: str


class PreviewResponse(BaseModel):
    import_id: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_row_count: int
    preview_row_count: int


class MappedPreviewResponse(BaseModel):
    import_id: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_row_count: int
    preview_row_count: int
    transformation_warnings: List[TransformationWarning] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    import_id: str
    correlation_id: str
    status: ImportStatusLiteral
    started_at: datetime


class ParquetFilesResponse(BaseModel):
    parquet_files: List[ParquetFile]
    total_count: int


class MappingTemplateSummary(BaseModel):
    template_id: str
    name: str
    description: Optional[str] = None
    field_count: int
    created_at: datetime
    created_by: str


class MappingTemplatesResponse(BaseModel):
    templates: List[MappingTemplateSummary]


class SaveTemplateRequest(BaseModel):
    import_id: str
    name: str = Field(..., max_length=128)
    description: Optional[str] = Field(None, max_length=512)


class SaveTemplateResponse(BaseModel):
    template_id: str
    name: str
    created_at: datetime


class ApplyTemplateRequest(BaseModel):
    template_id: str
