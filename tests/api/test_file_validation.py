"""Tests for census file field validation warnings.

Tests structured warning generation with severity tiers, impact descriptions,
alias detection, and backward compatibility of flat validation_warnings.
"""

import csv
import tempfile
from pathlib import Path

import pytest

from planalign_api.services.file_service import FileService


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace directory structure."""
    workspace_id = "test-workspace"
    workspace_dir = tmp_path / workspace_id
    workspace_dir.mkdir()
    (workspace_dir / "data").mkdir()
    return tmp_path, workspace_id


@pytest.fixture
def file_service(tmp_workspace):
    """Create a FileService instance with the temp workspace root."""
    workspaces_root, _ = tmp_workspace
    return FileService(workspaces_root)


def _create_csv(workspace_root: Path, workspace_id: str, filename: str, columns: list, rows: list) -> bytes:
    """Helper to create a CSV file and return its bytes."""
    data_dir = workspace_root / workspace_id / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / filename
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    return file_path.read_bytes()


# =============================================================================
# Phase 2 (US1): Critical field warning tests
# =============================================================================


class TestCriticalFieldWarnings:
    """Test structured warnings for missing critical fields."""

    def test_missing_single_critical_field_returns_structured_warning(self, file_service, tmp_workspace):
        """Missing employee_birth_date should produce a critical structured warning."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        critical = [w for w in structured if w["severity"] == "critical"]
        assert len(critical) == 1
        assert critical[0]["field_name"] == "employee_birth_date"
        assert critical[0]["warning_type"] == "missing"
        assert critical[0]["severity"] == "critical"
        assert len(critical[0]["impact_description"]) > 0

    def test_missing_multiple_critical_fields_returns_one_warning_per_field(self, file_service, tmp_workspace):
        """Each missing critical field should have its own structured warning."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "active"],
            rows=[["EMP001", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        critical = [w for w in structured if w["severity"] == "critical"]
        critical_names = {w["field_name"] for w in critical}
        assert "employee_hire_date" in critical_names
        assert "employee_gross_compensation" in critical_names
        assert "employee_birth_date" in critical_names
        assert len(critical) == 3

    def test_all_critical_fields_present_returns_no_critical_warnings(self, file_service, tmp_workspace):
        """No critical warnings when all critical columns are present."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation", "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        critical = [w for w in structured if w["severity"] == "critical"]
        assert len(critical) == 0

    def test_flat_validation_warnings_still_populated(self, file_service, tmp_workspace):
        """Backward compat: validation_warnings List[str] must still be populated."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id"],
            rows=[["EMP001"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        flat_warnings = metadata.get("validation_warnings", [])
        assert len(flat_warnings) > 0
        assert all(isinstance(w, str) for w in flat_warnings)

    def test_critical_warning_has_impact_description(self, file_service, tmp_workspace):
        """Each critical warning must have a non-empty impact_description."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id"],
            rows=[["EMP001"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        critical = [w for w in structured if w["severity"] == "critical"]
        for warning in critical:
            assert warning["impact_description"], f"Missing impact for {warning['field_name']}"
            assert warning["suggested_action"], f"Missing action for {warning['field_name']}"


# =============================================================================
# Phase 3 (US2): Optional field warning tests
# =============================================================================


class TestOptionalFieldWarnings:
    """Test structured warnings for missing optional fields."""

    def test_missing_optional_field_returns_optional_warning(self, file_service, tmp_workspace):
        """Missing employee_termination_date should produce an optional structured warning."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation", "employee_birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        optional = [w for w in structured if w["severity"] == "optional"]
        optional_names = {w["field_name"] for w in optional}
        assert "employee_termination_date" in optional_names

    def test_all_optional_fields_present_returns_no_optional_warnings(self, file_service, tmp_workspace):
        """No optional warnings when all optional columns are present."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation", "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        optional = [w for w in structured if w["severity"] == "optional"]
        assert len(optional) == 0

    def test_mixed_critical_and_optional_warnings(self, file_service, tmp_workspace):
        """Both critical and optional warnings returned when both tiers missing."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation"],
            rows=[["EMP001", "2020-01-15", "75000"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        critical = [w for w in structured if w["severity"] == "critical"]
        optional = [w for w in structured if w["severity"] == "optional"]
        assert len(critical) >= 1  # at least employee_birth_date
        assert len(optional) >= 1  # at least employee_termination_date or active


# =============================================================================
# Phase 4 (US3): Alias detection tests
# =============================================================================


class TestAliasDetection:
    """Test structured warnings for detected column aliases."""

    def test_alias_found_generates_auto_mapped_warning(self, file_service, tmp_workspace):
        """Alias column is auto-renamed and produces warning_type='auto_mapped'."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "hire_date", "employee_gross_compensation", "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        auto_mapped = [w for w in structured if w["warning_type"] == "auto_mapped"]
        assert len(auto_mapped) == 1
        assert auto_mapped[0]["field_name"] == "employee_hire_date"
        assert auto_mapped[0]["detected_alias"] == "hire_date"
        assert auto_mapped[0]["severity"] == "info"

        # Verify the saved file has canonical column names
        assert "employee_hire_date" in metadata["columns"]
        assert "hire_date" not in metadata["columns"]

    def test_alias_replaces_generic_missing_warning(self, file_service, tmp_workspace):
        """When alias is auto-mapped, no generic 'missing' warning for same field."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "hire_date", "employee_gross_compensation", "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        hire_date_warnings = [w for w in structured if w["field_name"] == "employee_hire_date"]
        assert len(hire_date_warnings) == 1
        assert hire_date_warnings[0]["warning_type"] == "auto_mapped"

    def test_alias_when_target_column_also_present(self, file_service, tmp_workspace):
        """No alias warning when both the alias and the canonical column exist."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "hire_date", "employee_hire_date", "employee_gross_compensation", "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        hire_date_warnings = [w for w in structured if w["field_name"] == "employee_hire_date"]
        assert len(hire_date_warnings) == 0


# =============================================================================
# Phase 5: Edge case tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases for field validation warnings."""

    def test_only_employee_id_shows_all_critical_missing(self, file_service, tmp_workspace):
        """File with only employee_id should list all critical fields as missing."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id"],
            rows=[["EMP001"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        structured = metadata.get("structured_warnings", [])
        critical = [w for w in structured if w["severity"] == "critical"]
        critical_names = {w["field_name"] for w in critical}
        assert "employee_hire_date" in critical_names
        assert "employee_gross_compensation" in critical_names
        assert "employee_birth_date" in critical_names

    def test_structured_warnings_coexist_with_flat_warnings(self, file_service, tmp_workspace):
        """Both structured_warnings and validation_warnings populated together."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id"],
            rows=[["EMP001"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        assert len(metadata["validation_warnings"]) > 0
        assert len(metadata["structured_warnings"]) > 0

    def test_no_warnings_when_all_fields_present(self, file_service, tmp_workspace):
        """No warnings of any kind when all expected fields are present."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation", "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        assert len(metadata["validation_warnings"]) == 0
        assert len(metadata["structured_warnings"]) == 0


# =============================================================================
# Phase 6: Data Quality - Null/Empty checks
# =============================================================================


class TestDataQualityNullEmpty:
    """Test row-level null/empty data quality checks."""

    def test_null_employee_id_produces_error_severity(self, file_service, tmp_workspace):
        """Null employee_id (critical field) should produce error-severity DQ warning."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["", "2020-01-15", "75000", "1985-06-01", "", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        null_id = [w for w in dq if w["field_name"] == "employee_id" and w["check_type"] == "null_or_empty"]
        assert len(null_id) == 1
        assert null_id[0]["severity"] == "error"
        assert null_id[0]["affected_count"] == 1
        assert null_id[0]["total_count"] == 2
        assert null_id[0]["affected_percentage"] == 50.0

    def test_null_optional_field_produces_warning_severity(self, file_service, tmp_workspace):
        """Null optional field should produce warning-severity DQ warning."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["EMP001", "2020-01-15", "75000", "1985-06-01", "", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        null_term = [w for w in dq if w["field_name"] == "employee_termination_date" and w["check_type"] == "null_or_empty"]
        assert len(null_term) == 1
        assert null_term[0]["severity"] == "warning"

    def test_clean_data_produces_no_dq_warnings(self, file_service, tmp_workspace):
        """Fully populated data should produce no DQ warnings."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "2025-06-01", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        assert len(dq) == 0

    def test_samples_capped_at_5(self, file_service, tmp_workspace):
        """Samples should contain at most 5 entries even with more issues."""
        workspace_root, workspace_id = tmp_workspace
        rows = [["", "2020-01-15", "75000", "1985-06-01", "", "true"] for _ in range(10)]
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=rows,
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        null_id = [w for w in dq if w["field_name"] == "employee_id" and w["check_type"] == "null_or_empty"]
        assert len(null_id) == 1
        assert null_id[0]["affected_count"] == 10
        assert len(null_id[0]["samples"]) <= 5

    def test_samples_contain_row_number_and_value(self, file_service, tmp_workspace):
        """Sample entries should have row_number and value keys."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["", "2020-01-15", "75000", "1985-06-01", "", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        null_id = [w for w in dq if w["field_name"] == "employee_id"]
        assert len(null_id) == 1
        assert len(null_id[0]["samples"]) >= 1
        sample = null_id[0]["samples"][0]
        assert "row_number" in sample
        assert "value" in sample


# =============================================================================
# Phase 7: Data Quality - Date checks
# =============================================================================


class TestDataQualityDates:
    """Test row-level date quality checks."""

    def test_unparseable_dates_flagged(self, file_service, tmp_workspace):
        """Unparseable date strings should be flagged.

        Note: DuckDB CSV auto-detect may successfully parse some formats,
        turning truly unparseable values into NULLs (caught by null check).
        This test uses a value that is clearly not a date.
        """
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["EMP001", "not-a-date", "75000", "1985-06-01", "", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        # DuckDB may parse the column as VARCHAR when it sees "not-a-date",
        # in which case we get an unparseable_date warning.
        # Or it may fail to auto-detect, leaving the column as VARCHAR.
        # Either way, there should be some data quality warning flagging the issue.
        date_or_null_issues = [
            w for w in dq
            if w["field_name"] == "employee_hire_date"
            and w["check_type"] in ("unparseable_date", "null_or_empty")
        ]
        assert len(date_or_null_issues) >= 1


# =============================================================================
# Phase 8: Data Quality - Numeric checks
# =============================================================================


class TestDataQualityNumeric:
    """Test row-level numeric quality checks."""

    def test_negative_compensation_flagged(self, file_service, tmp_workspace):
        """Negative compensation values should produce a DQ warning."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["EMP001", "2020-01-15", "-5000", "1985-06-01", "", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        neg_comp = [w for w in dq if w["field_name"] == "employee_gross_compensation" and w["check_type"] == "negative_value"]
        assert len(neg_comp) == 1
        assert neg_comp[0]["severity"] == "warning"
        assert neg_comp[0]["affected_count"] == 1

    def test_zero_compensation_flagged(self, file_service, tmp_workspace):
        """Zero compensation should also be flagged."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["EMP001", "2020-01-15", "0", "1985-06-01", "", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "", "true"],
            ],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        dq = metadata.get("data_quality_warnings", [])
        neg_comp = [w for w in dq if w["field_name"] == "employee_gross_compensation" and w["check_type"] == "negative_value"]
        assert len(neg_comp) == 1


# =============================================================================
# Phase 9: Data Quality - Backward compatibility
# =============================================================================


class TestDataQualityBackwardCompat:
    """Test backward compatibility of data_quality_warnings field."""

    def test_data_quality_warnings_field_always_present(self, file_service, tmp_workspace):
        """data_quality_warnings should always be present in metadata."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        assert "data_quality_warnings" in metadata
        assert isinstance(metadata["data_quality_warnings"], list)

    def test_structured_warnings_unaffected_by_dq(self, file_service, tmp_workspace):
        """Existing structured_warnings should be unaffected by DQ additions."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id"],
            rows=[["EMP001"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        # structured_warnings should still have the missing-field warnings
        assert len(metadata["structured_warnings"]) > 0
        # data_quality_warnings is separate
        assert "data_quality_warnings" in metadata

    def test_validate_path_includes_dq_warnings(self, file_service, tmp_workspace):
        """validate_path should also include data_quality_warnings."""
        workspace_root, workspace_id = tmp_workspace
        _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[
                ["", "2020-01-15", "75000", "1985-06-01", "", "true"],
            ],
        )

        result = file_service.validate_path(workspace_id, "data/test.csv")

        assert result["valid"] is True
        assert "data_quality_warnings" in result
        assert isinstance(result["data_quality_warnings"], list)
        # Should have null employee_id warning
        null_id = [w for w in result["data_quality_warnings"]
                   if w["field_name"] == "employee_id" and w["check_type"] == "null_or_empty"]
        assert len(null_id) == 1


# =============================================================================
# Column Auto-Mapping Tests
# =============================================================================


class TestColumnAutoMapping:
    """Test automatic column renaming from aliases to canonical names."""

    def test_alias_columns_are_renamed(self, file_service, tmp_workspace):
        """Alias columns should be renamed to canonical names in the saved file."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "hire_date", "compensation", "birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        # Canonical names should be in the saved columns
        assert "employee_hire_date" in metadata["columns"]
        assert "employee_gross_compensation" in metadata["columns"]
        assert "employee_birth_date" in metadata["columns"]
        # Original aliases should NOT be in the saved columns
        assert "hire_date" not in metadata["columns"]
        assert "compensation" not in metadata["columns"]
        assert "birth_date" not in metadata["columns"]

    def test_canonical_columns_untouched(self, file_service, tmp_workspace):
        """Columns already using canonical names should not be affected."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        assert "employee_hire_date" in metadata["columns"]
        assert len(metadata["column_renames"]) == 0

    def test_both_alias_and_canonical_skips_rename(self, file_service, tmp_workspace):
        """When both alias and canonical column exist, skip rename for that column."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "hire_date", "employee_hire_date",
                      "employee_gross_compensation", "employee_birth_date",
                      "employee_termination_date", "active"],
            rows=[["EMP001", "2020-01-15", "2020-01-15", "75000", "1985-06-01", "2025-01-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        # Both columns should still exist (no rename attempted)
        assert "employee_hire_date" in metadata["columns"]
        assert "hire_date" in metadata["columns"]
        # No rename for hire_date
        hire_renames = [r for r in metadata["column_renames"] if r["original"] == "hire_date"]
        assert len(hire_renames) == 0

    def test_unknown_columns_preserved(self, file_service, tmp_workspace):
        """Unknown/custom columns should pass through unchanged."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "custom_field", "department_code", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "foo", "DEPT1", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        assert "custom_field" in metadata["columns"]
        assert "department_code" in metadata["columns"]

    def test_column_renames_populated_in_metadata(self, file_service, tmp_workspace):
        """column_renames should list each rename performed."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "hire_date", "salary", "dob", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content, "test.csv")

        renames = metadata["column_renames"]
        rename_map = {r["original"]: r["canonical"] for r in renames}
        assert rename_map["hire_date"] == "employee_hire_date"
        assert rename_map["salary"] == "employee_gross_compensation"
        assert rename_map["dob"] == "employee_birth_date"

    def test_csv_converted_to_parquet(self, file_service, tmp_workspace):
        """CSV files should be converted to parquet format."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        relative_path, metadata, absolute_path = file_service.save_uploaded_file(
            workspace_id, content, "test.csv"
        )

        assert relative_path == "data/census.parquet"
        assert absolute_path.endswith("census.parquet")
        assert Path(absolute_path).exists()


# =============================================================================
# Filename Normalization Tests
# =============================================================================


class TestFilenameNormalization:
    """Test that uploaded files are always saved as census.parquet."""

    def test_file_saved_as_census_parquet(self, file_service, tmp_workspace):
        """Regardless of input filename, output should be census.parquet."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "my_custom_census_2024.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        relative_path, _, absolute_path = file_service.save_uploaded_file(
            workspace_id, content, "my_custom_census_2024.csv"
        )

        assert relative_path == "data/census.parquet"
        assert Path(absolute_path).name == "census.parquet"

    def test_original_filename_preserved_in_metadata(self, file_service, tmp_workspace):
        """Original filename should be stored in metadata."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "hr_export_jan2025.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        _, metadata, _ = file_service.save_uploaded_file(
            workspace_id, content, "hr_export_jan2025.csv"
        )

        assert metadata["original_filename"] == "hr_export_jan2025.csv"

    def test_temp_files_cleaned_up(self, file_service, tmp_workspace):
        """Temp files should be cleaned up after normalization."""
        workspace_root, workspace_id = tmp_workspace
        content = _create_csv(
            workspace_root, workspace_id, "test.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )

        file_service.save_uploaded_file(workspace_id, content, "test.csv")

        data_dir = workspace_root / workspace_id / "data"
        temp_files = list(data_dir.glob("_temp_upload*"))
        assert len(temp_files) == 0

    def test_multiple_uploads_overwrite_census_parquet(self, file_service, tmp_workspace):
        """Later uploads should overwrite census.parquet."""
        workspace_root, workspace_id = tmp_workspace

        # First upload
        content1 = _create_csv(
            workspace_root, workspace_id, "first.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "active"],
            rows=[["EMP001", "2020-01-15", "75000", "1985-06-01", "true"]],
        )
        file_service.save_uploaded_file(workspace_id, content1, "first.csv")

        # Second upload
        content2 = _create_csv(
            workspace_root, workspace_id, "second.csv",
            columns=["employee_id", "employee_hire_date", "employee_gross_compensation",
                      "employee_birth_date", "active"],
            rows=[
                ["EMP001", "2020-01-15", "75000", "1985-06-01", "true"],
                ["EMP002", "2021-03-01", "80000", "1990-02-15", "true"],
            ],
        )
        _, metadata, _ = file_service.save_uploaded_file(workspace_id, content2, "second.csv")

        # Should have 2 rows from second upload
        assert metadata["row_count"] == 2
        assert metadata["original_filename"] == "second.csv"
