"""Coverage tests for planalign_api.models.export Pydantic models.

Exercises all model classes, enum values, default fields, validation
constraints, and the json_encoders config.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from planalign_api.models.export import (
    BulkExportRequest,
    BulkExportStatus,
    BulkImportStatus,
    BulkOperationStatus,
    ConflictResolution,
    ErrorResponse,
    ExportManifest,
    ExportResult,
    ExportStatus,
    ImportConflict,
    ImportResponse,
    ImportStatus,
    ImportValidationResponse,
    ManifestContents,
)


# =============================================================================
# ManifestContents
# =============================================================================


class TestManifestContents:
    @pytest.mark.fast
    def test_valid_construction(self):
        mc = ManifestContents(
            scenario_count=3,
            scenarios=["baseline", "high_growth", "low_growth"],
            file_count=12,
            total_size_bytes=1024000,
            checksum_sha256="abc123def456",
        )
        assert mc.scenario_count == 3
        assert len(mc.scenarios) == 3
        assert mc.file_count == 12
        assert mc.total_size_bytes == 1024000

    @pytest.mark.fast
    def test_negative_scenario_count_rejected(self):
        with pytest.raises(ValidationError):
            ManifestContents(
                scenario_count=-1,
                scenarios=[],
                file_count=0,
                total_size_bytes=0,
                checksum_sha256="x",
            )


# =============================================================================
# ExportManifest
# =============================================================================


class TestExportManifest:
    @pytest.mark.fast
    def test_valid_construction_with_defaults(self):
        now = datetime.now()
        em = ExportManifest(
            export_date=now,
            app_version="1.0.0",
            workspace_id="ws-001",
            workspace_name="Test Workspace",
            contents=ManifestContents(
                scenario_count=1,
                scenarios=["baseline"],
                file_count=5,
                total_size_bytes=512,
                checksum_sha256="sha",
            ),
        )
        assert em.version == "1.0"
        assert em.workspace_id == "ws-001"

    @pytest.mark.fast
    def test_json_encoder_datetime(self):
        now = datetime(2025, 6, 15, 12, 0, 0)
        em = ExportManifest(
            export_date=now,
            app_version="1.0.0",
            workspace_id="ws-001",
            workspace_name="Test",
            contents=ManifestContents(
                scenario_count=0,
                scenarios=[],
                file_count=0,
                total_size_bytes=0,
                checksum_sha256="x",
            ),
        )
        dumped = em.model_dump_json()
        assert "2025-06-15" in dumped


# =============================================================================
# ExportStatus / ExportResult
# =============================================================================


class TestExportStatusAndResult:
    @pytest.mark.fast
    def test_enum_values(self):
        assert ExportStatus.SUCCESS == "success"
        assert ExportStatus.FAILED == "failed"

    @pytest.mark.fast
    def test_export_result_defaults(self):
        er = ExportResult(
            workspace_id="ws-001",
            workspace_name="Test",
            status=ExportStatus.SUCCESS,
        )
        assert er.filename == ""
        assert er.size_bytes == 0
        assert er.error is None

    @pytest.mark.fast
    def test_export_result_with_error(self):
        er = ExportResult(
            workspace_id="ws-001",
            workspace_name="Test",
            status=ExportStatus.FAILED,
            error="Disk full",
        )
        assert er.error == "Disk full"


# =============================================================================
# BulkExportRequest
# =============================================================================


class TestBulkExportRequest:
    @pytest.mark.fast
    def test_valid_request(self):
        req = BulkExportRequest(workspace_ids=["ws-001", "ws-002"])
        assert len(req.workspace_ids) == 2

    @pytest.mark.fast
    def test_empty_list_rejected(self):
        with pytest.raises(ValidationError):
            BulkExportRequest(workspace_ids=[])


# =============================================================================
# BulkOperationStatus / BulkExportStatus
# =============================================================================


class TestBulkOperationStatus:
    @pytest.mark.fast
    def test_all_enum_values(self):
        assert BulkOperationStatus.PENDING == "pending"
        assert BulkOperationStatus.IN_PROGRESS == "in_progress"
        assert BulkOperationStatus.COMPLETED == "completed"
        assert BulkOperationStatus.FAILED == "failed"

    @pytest.mark.fast
    def test_bulk_export_status_defaults(self):
        bes = BulkExportStatus(
            operation_id="op-001",
            status=BulkOperationStatus.PENDING,
            total=5,
        )
        assert bes.completed == 0
        assert bes.current_workspace is None
        assert bes.results == []


# =============================================================================
# ImportConflict
# =============================================================================


class TestImportConflict:
    @pytest.mark.fast
    def test_valid_construction(self):
        ic = ImportConflict(
            existing_workspace_id="ws-old",
            existing_workspace_name="Old Workspace",
            suggested_name="Old Workspace (2)",
        )
        assert ic.suggested_name == "Old Workspace (2)"


# =============================================================================
# ImportValidationResponse
# =============================================================================


class TestImportValidationResponse:
    @pytest.mark.fast
    def test_valid_response_defaults(self):
        ivr = ImportValidationResponse(valid=True)
        assert ivr.manifest is None
        assert ivr.conflict is None
        assert ivr.warnings == []
        assert ivr.errors == []

    @pytest.mark.fast
    def test_invalid_response_with_errors(self):
        ivr = ImportValidationResponse(
            valid=False,
            errors=["Missing manifest", "Corrupt archive"],
        )
        assert not ivr.valid
        assert len(ivr.errors) == 2


# =============================================================================
# ConflictResolution / ImportStatus / ImportResponse
# =============================================================================


class TestImportModels:
    @pytest.mark.fast
    def test_conflict_resolution_enum(self):
        assert ConflictResolution.RENAME == "rename"
        assert ConflictResolution.REPLACE == "replace"
        assert ConflictResolution.SKIP == "skip"

    @pytest.mark.fast
    def test_import_status_enum(self):
        assert ImportStatus.SUCCESS == "success"
        assert ImportStatus.PARTIAL == "partial"

    @pytest.mark.fast
    def test_import_response_defaults(self):
        ir = ImportResponse(
            workspace_id="ws-new",
            name="Imported Workspace",
            scenario_count=3,
            status=ImportStatus.SUCCESS,
        )
        assert ir.warnings == []

    @pytest.mark.fast
    def test_import_response_with_warnings(self):
        ir = ImportResponse(
            workspace_id="ws-new",
            name="Imported",
            scenario_count=2,
            status=ImportStatus.PARTIAL,
            warnings=["Missing seed data"],
        )
        assert ir.status == ImportStatus.PARTIAL
        assert len(ir.warnings) == 1


# =============================================================================
# BulkImportStatus
# =============================================================================


class TestBulkImportStatus:
    @pytest.mark.fast
    def test_defaults(self):
        bis = BulkImportStatus(
            operation_id="op-002",
            status=BulkOperationStatus.IN_PROGRESS,
            total=3,
        )
        assert bis.completed == 0
        assert bis.current_file is None
        assert bis.results == []


# =============================================================================
# ErrorResponse
# =============================================================================


class TestErrorResponse:
    @pytest.mark.fast
    def test_minimal(self):
        er = ErrorResponse(error="NOT_FOUND", message="Workspace not found")
        assert er.details is None

    @pytest.mark.fast
    def test_with_details(self):
        er = ErrorResponse(
            error="VALIDATION_ERROR",
            message="Invalid config",
            details={"field": "start_year", "reason": "must be positive"},
        )
        assert er.details["field"] == "start_year"
