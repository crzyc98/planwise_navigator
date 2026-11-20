"""The import wizard's data-quality checks cover the whole file (#1261).

All census data here is synthetic.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from planalign_api.services.census_analysis_service import CensusAnalysisService
from planalign_api.services.census_plausibility import RULES
from planalign_api.services.import_quality import FLAGGED_ROWS_HEADER, RULE_LABELS

pytestmark = pytest.mark.fast

WS = "ws-test"
HEADER = "EmpID,DOB,Hire Date,Salary,Deferral,EE Contrib,Active"

# Bad rows, all past the 100-row preview sample. Keys are 1-based data rows.
BAD_ROWS = {
    120: 'E0120,03/15/1980,06/15/2015,"$40,000.00",0.05,"$50,000.00",Y',
    130: 'E0130,03/15/1980,06/15/2015,"($5,000.00)",0.05,,Y',
    140: 'E0140,03/15/2016,06/15/2015,"$60,000.00",0.05,"$3,000.00",Y',
    145: 'E0110,03/15/1980,06/15/2015,"$60,000.00",0.05,"$3,000.00",Y',
    150: 'E0150,03/15/1980,06/15/2015,"$60,000.00",6,"$3,000.00",Y',
}


def _census(rows: int = 150, bad_rows: dict[int, str] = BAD_ROWS) -> str:
    """Clean rows with formatted values, plus the given bad rows."""
    lines = [HEADER]
    for n in range(1, rows + 1):
        clean = (
            f'E{n:04d},03/15/1980,06/15/{2015 + n % 10},"$60,000.00",0.05,'
            f'"$3,000.00",Y'
        )
        lines.append(bad_rows.get(n, clean))
    return "\n".join(lines) + "\n"


def _mapping(output: str, column: str, kind: str) -> dict[str, object]:
    return {
        "input_column": column,
        "output_column": output,
        "output_type": kind,
        "is_excluded": False,
        "transformations": [],
    }


MAPPINGS = [
    _mapping("employee_id", "EmpID", "string"),
    _mapping("employee_birth_date", "DOB", "date"),
    _mapping("employee_hire_date", "Hire Date", "date"),
    _mapping("employee_gross_compensation", "Salary", "decimal"),
    _mapping("employee_deferral_rate", "Deferral", "decimal"),
    _mapping("employee_contribution", "EE Contrib", "decimal"),
    _mapping("active", "Active", "boolean"),
]


@pytest.fixture()
def workspaces(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    (root / WS).mkdir(parents=True)
    (root / WS / "workspace.json").write_text(
        json.dumps(
            {
                "id": WS,
                "name": "Test",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        )
    )
    return root


@pytest.fixture()
def client(workspaces: Path):
    from planalign_api.main import app
    from planalign_api.routers.imports import get_import_service, get_workspace_storage
    from planalign_api.services.import_service import ImportService
    from planalign_api.storage.workspace_storage import WorkspaceStorage

    app.dependency_overrides[get_import_service] = lambda: ImportService(workspaces)
    app.dependency_overrides[get_workspace_storage] = lambda: WorkspaceStorage(
        workspaces
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _mapped_import(
    client: TestClient, content: str, filename: str = "census.csv"
) -> str:
    response = client.post(
        f"/api/workspaces/{WS}/imports/upload",
        files={"file": (filename, io.BytesIO(content.encode()), "text/csv")},
    )
    assert response.status_code == 201, response.text
    import_id = response.json()["import_id"]
    saved = client.put(
        f"/api/workspaces/{WS}/imports/{import_id}/mapping",
        json={"field_mappings": MAPPINGS},
    )
    assert saved.json()["validation_errors"] == []
    return import_id


def _preview(client: TestClient, import_id: str) -> dict:
    response = client.get(f"/api/workspaces/{WS}/imports/{import_id}/mapped-preview")
    assert response.status_code == 200, response.text
    return response.json()


def _data_quality(client: TestClient, import_id: str) -> dict:
    preview = _preview(client, import_id)
    assert preview["data_quality_skipped_reason"] is None
    return preview["data_quality"]


def _flagged_rows(client: TestClient, import_id: str):
    return client.get(f"/api/workspaces/{WS}/imports/{import_id}/flagged-rows")


def _rule_counts(data_quality: dict) -> dict[str, int]:
    return {r["rule_id"]: r["count"] for r in data_quality["plausibility"]}


def test_bad_rows_beyond_the_preview_sample_are_counted(client: TestClient) -> None:
    import_id = _mapped_import(client, _census())
    dq = _data_quality(client, import_id)
    counts = _rule_counts(dq)
    severities = {r["rule_id"]: r["severity"] for r in dq["plausibility"]}

    # "$50,000.00" against "$40,000.00" only trips once both are parsed.
    assert counts["employee_contribution_above_pay"] == 1
    assert severities["employee_contribution_above_pay"] == "error"
    # "($5,000.00)" is a parenthesised negative.
    assert counts["compensation_not_positive"] == 1
    # Non-ISO dates are compared as dates.
    assert counts["birth_on_or_after_hire"] == 1
    assert counts["deferral_rate_out_of_range"] == 1
    assert severities["deferral_rate_out_of_range"] == "warning"
    assert dq["duplicate_employee_id_count"] == 1
    assert dq["null_required_field_counts"] == {}


def test_clean_file_reports_nothing(client: TestClient) -> None:
    dq = _data_quality(client, _mapped_import(client, _census(bad_rows={})))
    assert dq["plausibility"] == []
    assert dq["duplicate_employee_id_count"] == 0


def test_wizard_counts_match_census_analysis_after_import(
    client: TestClient, workspaces: Path
) -> None:
    import_id = _mapped_import(client, _census())
    wizard = _data_quality(client, import_id)

    generated = client.post(f"/api/workspaces/{WS}/imports/{import_id}/generate")
    assert generated.status_code == 202, generated.text
    analysis = CensusAnalysisService(workspaces).analyze(
        WS, generated.json()["storage_path"], employee_status="all"
    )
    rule_issue_types = {rule.issue_type for rule in RULES}
    page = {
        (issue.field, issue.severity, issue.count, issue.message)
        for issue in analysis.data_quality_issues
        if issue.issue_type in rule_issue_types
    }
    shown = {
        (rule["field"], rule["severity"], rule["count"], rule["message"])
        for rule in wizard["plausibility"]
    }
    assert len(shown) >= 4
    assert shown == page
    duplicates = next(
        i.count
        for i in analysis.data_quality_issues
        if i.issue_type == "duplicate_employee_id"
    )
    assert wizard["duplicate_employee_id_count"] == duplicates


def test_flagged_rows_download_has_only_row_id_and_rules(client: TestClient) -> None:
    import_id = _mapped_import(client, _census())
    response = _flagged_rows(client, import_id)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "census_flagged_rows.csv" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert tuple(rows[0]) == FLAGGED_ROWS_HEADER
    # Data-row ordinals as read: 1 is the first row after the header.
    by_row = {int(row): (employee_id, rules) for row, employee_id, rules in rows[1:]}
    assert set(by_row) == {120, 130, 140, 150}
    assert by_row[120][0] == "E0120"
    assert RULE_LABELS["employee_contribution_above_pay"] in by_row[120][1]
    assert by_row[140] == ("E0140", RULE_LABELS["birth_on_or_after_hire"])
    assert all(len(row) == 3 for row in rows)


def test_flagged_rows_download_names_non_latin_files(client: TestClient) -> None:
    import_id = _mapped_import(client, _census(), filename="census_日本.csv")
    response = _flagged_rows(client, import_id)
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        "attachment; filename*=utf-8''census_%E6%97%A5%E6%9C%AC_flagged_rows.csv"
    )


def test_unconvertible_file_says_why_checks_were_skipped(client: TestClient) -> None:
    import_id = _mapped_import(
        client,
        _census(bad_rows={130: "E0130,03/15/1980,06/15/2015,unknown,0.05,$0.00,Y"}),
    )
    preview = _preview(client, import_id)
    assert preview["data_quality"] is None
    reason = preview["data_quality_skipped_reason"]
    assert reason.startswith("Whole-file checks didn't run:")
    assert "'Salary'" in reason and "1 value(s)" in reason
    assert _flagged_rows(client, import_id).status_code == 409


def test_blank_hire_dates_skip_only_the_rules(client: TestClient) -> None:
    # No hire date to set the census year; E0001 appears twice.
    ids = [f"E{n:04d}" for n in range(1, 151)] + ["E0001"]
    content = "\n".join(
        [HEADER] + [f'{i},03/15/1980,,"$60,000.00",0.05,"$3,000.00",Y' for i in ids]
    )
    preview = _preview(client, _mapped_import(client, content))
    dq = preview["data_quality"]
    assert dq["plausibility"] == []
    assert dq["duplicate_employee_id_count"] == 1
    assert dq["null_required_field_counts"] == {"employee_hire_date": 151}
    assert preview["data_quality_skipped_reason"].startswith(
        "Cross-field checks didn't run"
    )


def test_flagged_rows_after_generate_is_a_conflict(client: TestClient) -> None:
    import_id = _mapped_import(client, _census())
    generated = client.post(f"/api/workspaces/{WS}/imports/{import_id}/generate")
    assert generated.status_code == 202
    assert _flagged_rows(client, import_id).status_code == 409


def test_formula_like_employee_ids_are_neutralised(client: TestClient) -> None:
    bad = {101: '=1+1,03/15/2016,06/15/2015,"$60,000.00",0.05,"$3,000.00",Y'}
    import_id = _mapped_import(client, _census(bad_rows=bad))
    rows = list(csv.reader(io.StringIO(_flagged_rows(client, import_id).text)))
    assert rows[1][:2] == ["101", "'=1+1"]


def test_every_rule_has_a_download_label() -> None:
    assert {rule.rule_id for rule in RULES} == set(RULE_LABELS)
