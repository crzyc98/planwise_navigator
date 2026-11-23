"""Data import bounds the work per request and keeps cell contents out of errors."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import planalign_api.config as api_config
from planalign_api.main import create_app
from planalign_api.models.imports import (
    FieldMapping,
    MappingSaveRequest,
    Transformation,
)
from planalign_api.services.mapping_engine import (
    MappingEngine,
    MappingError,
    validate_expression,
)

pytestmark = pytest.mark.fast

MARKER = "SECRET-123-45-6789"
HEADER = "EMP_ID,BIRTH,HIRE,PAY,ACTIVE,FIRST,LAST\n"
ROWS = [
    "E1,1980-01-01,2015-03-01,50000,true,Ann,Lee\n",
    "E2,1985-02-02,2016-04-01,60000,false,Bob,Kim\n",
]


def _calc(expr: str) -> FieldMapping:
    return FieldMapping(
        input_column="A",
        output_column="out",
        output_type="string",
        transformations=[
            Transformation(
                transform_type="calculated_field", params={"expression": expr}
            )
        ],
    )


def _eval(expr: str, df: pd.DataFrame) -> list[object]:
    return list(MappingEngine().apply(df, [_calc(expr)])["out"])


@pytest.fixture()
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "A": [1.0, 2.0],
            "B": [3.0, 5.0],
            "S": ["x", "y"],
            "salary": [1000.0, 2000.0],
            "first": ["Ann", "Bob"],
            "last": ["Lee", "Kim"],
        }
    )


# ---------------------------------------------------------------------------
# Calculated-field expressions
# ---------------------------------------------------------------------------


def test_long_flat_sum_is_a_clean_value_error(frame: pd.DataFrame) -> None:
    with pytest.raises(MappingError):
        _eval("+".join(["A"] * 1100), frame)


def test_node_count_limit_without_length_limit(frame: pd.DataFrame) -> None:
    with pytest.raises(MappingError, match="too complex"):
        validate_expression("+".join(["A"] * 40), {"A"})


def test_deep_nesting_is_rejected() -> None:
    with pytest.raises(MappingError, match="too complex"):
        validate_expression("-" * 20 + "1", set())


@pytest.mark.parametrize(
    "expr",
    ["'a' * 5", "S * 3", "S - S", "-S", "S / 2", "S + 1"],
)
def test_text_operands_are_rejected(frame: pd.DataFrame, expr: str) -> None:
    with pytest.raises(MappingError):
        _eval(expr, frame)


def test_text_concatenation_is_capped(frame: pd.DataFrame) -> None:
    big = pd.DataFrame({"A": ["x" * 3000], "B": ["y" * 3000]})
    with pytest.raises(MappingError, match="longer than 4096"):
        _eval("A + B", big)


@pytest.mark.parametrize("expr", ["1000000000 * 10000000", "1e16", "1e400 - 1"])
def test_huge_numbers_are_rejected(frame: pd.DataFrame, expr: str) -> None:
    with pytest.raises(MappingError):
        _eval(expr, frame)


def test_unexpected_evaluation_error_is_generic(frame: pd.DataFrame) -> None:
    mixed = pd.DataFrame({"A": ["x", 1], "B": ["y", "z"]})
    with pytest.raises(MappingError, match="could not be evaluated"):
        _eval("A + B", mixed)


def test_normal_expressions_still_work(frame: pd.DataFrame) -> None:
    assert _eval("salary * 1.03", frame) == [1030.0, 2060.0]
    assert _eval("first + ' ' + last", frame) == ["Ann Lee", "Bob Kim"]
    assert _eval("(A + B) / 2", frame) == [2.0, 3.5]


# ---------------------------------------------------------------------------
# Request model bounds
# ---------------------------------------------------------------------------


def test_request_models_bound_list_and_params_sizes() -> None:
    with pytest.raises(ValidationError):
        Transformation(transform_type="null_replace", params={"value": "x" * 5000})
    with pytest.raises(ValidationError):
        FieldMapping(
            input_column="A",
            output_column="out",
            output_type="string",
            transformations=[Transformation(transform_type="rename")] * 17,
        )
    mapping = FieldMapping(input_column="A", output_column="out", output_type="string")
    with pytest.raises(ValidationError):
        MappingSaveRequest(field_mappings=[mapping] * 501)


# ---------------------------------------------------------------------------
# Coercion messages
# ---------------------------------------------------------------------------


def test_coercion_error_names_rows_not_values() -> None:
    df = pd.DataFrame({"HIRE": ["2020-01-01", MARKER, "2020-02-02", MARKER]})
    mapping = FieldMapping(
        input_column="HIRE", output_column="employee_hire_date", output_type="date"
    )
    with pytest.raises(MappingError) as exc_info:
        MappingEngine().apply(df, [mapping])
    message = str(exc_info.value)
    assert "rows 2, 4" in message
    assert MARKER not in message


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
    settings = api_config.APISettings(
        workspaces_root=tmp_path / "workspaces",
        import_xlsx_max_unpacked_bytes=64 * 1024,
    )
    monkeypatch.setattr(api_config, "settings", settings)
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture()
def workspace_id(client: TestClient) -> str:
    resp = client.post("/api/workspaces", json={"name": "limits"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload(
    client: TestClient, workspace_id: str, name: str, content: bytes
) -> dict[str, object]:
    resp = client.post(
        f"/api/workspaces/{workspace_id}/imports/upload",
        files={"file": (name, content)},
    )
    return {"status": resp.status_code, "body": resp.json()}


def _csv_import(client: TestClient, workspace_id: str, rows: list[str]) -> str:
    result = _upload(client, workspace_id, "c.csv", (HEADER + "".join(rows)).encode())
    assert result["status"] == 201
    body = result["body"]
    assert isinstance(body, dict)
    return str(body["import_id"])


def _mapping_payload(hire_transforms: list[dict[str, object]]) -> dict[str, object]:
    fields = [
        ("EMP_ID", "employee_id", "string", []),
        ("BIRTH", "employee_birth_date", "date", []),
        ("HIRE", "employee_hire_date", "date", hire_transforms),
        ("PAY", "employee_gross_compensation", "decimal", []),
        ("ACTIVE", "active", "boolean", []),
    ]
    return {
        "field_mappings": [
            {
                "input_column": src,
                "output_column": out,
                "output_type": kind,
                "transformations": transforms,
            }
            for src, out, kind, transforms in fields
        ]
    }


def _save(client: TestClient, workspace_id: str, import_id: str, payload: object):
    return client.put(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/mapping", json=payload
    )


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


def test_upload_rejects_too_many_columns(client: TestClient, workspace_id: str):
    df = pd.DataFrame([[1] * 501], columns=[f"c{i}" for i in range(501)])
    result = _upload(client, workspace_id, "wide.csv", df.to_csv(index=False).encode())
    assert result["status"] == 422
    assert "500 columns" in str(result["body"])


def test_xlsx_with_too_many_columns_is_rejected(
    client: TestClient, workspace_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api_config.settings, "import_xlsx_max_unpacked_bytes", 512 * 1024 * 1024
    )
    df = pd.DataFrame([[1] * 501], columns=[f"c{i}" for i in range(501)])
    result = _upload(client, workspace_id, "wide.xlsx", _xlsx_bytes(df))
    assert result["status"] == 422
    assert "500 columns" in str(result["body"])


def test_upload_rejects_long_header(client: TestClient, workspace_id: str) -> None:
    content = ("A," + "h" * 257 + "\n1,2\n").encode()
    result = _upload(client, workspace_id, "long.csv", content)
    assert result["status"] == 422
    assert "256 characters" in str(result["body"])


def test_xlsx_over_unpacked_limit_is_rejected(
    client: TestClient, workspace_id: str
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/padding.xml", "0" * (128 * 1024))
    result = _upload(client, workspace_id, "big.xlsx", buffer.getvalue())
    assert result["status"] == 422
    assert "once unpacked" in str(result["body"])


def test_small_xlsx_still_uploads(client: TestClient, workspace_id: str) -> None:
    df = pd.DataFrame({"ID": ["E1"], "NAME": ["Ann"]})
    result = _upload(client, workspace_id, "ok.xlsx", _xlsx_bytes(df))
    assert result["status"] == 201


@pytest.mark.parametrize(
    "transforms",
    [
        [{"transform_type": "calculated_field", "params": {"expression": "'a' * 5"}}],
        [{"transform_type": "calculated_field", "params": {"expression": "NOPE"}}],
        [{"transform_type": "date_parse", "params": {"format": "%Y-%j"}}],
        [{"transform_type": "null_replace", "params": {"value": "x" * 300}}],
        [{"transform_type": "null_replace", "params": {"value": [1, 2]}}],
    ],
)
def test_save_mapping_rejects_bad_transformations(
    client: TestClient, workspace_id: str, transforms: list[dict[str, object]]
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    resp = _save(client, workspace_id, import_id, _mapping_payload(transforms))
    errors = resp.json()["validation_errors"]
    assert [e["field"] for e in errors] == ["transformations"]
    mapping_path = Path(
        api_config.settings.workspaces_root,
        workspace_id,
        "imports",
        import_id,
        "mapping.json",
    )
    assert not mapping_path.exists()


def test_save_mapping_rejects_oversize_transformation_list(
    client: TestClient, workspace_id: str
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    payload = _mapping_payload([{"transform_type": "rename", "params": {}}] * 17)
    resp = _save(client, workspace_id, import_id, payload)
    assert resp.status_code == 422


def test_save_mapping_accepts_valid_transformations(
    client: TestClient, workspace_id: str
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    payload = _mapping_payload(
        [{"transform_type": "date_parse", "params": {"format": "%Y-%m-%d"}}]
    )
    resp = _save(client, workspace_id, import_id, payload)
    assert resp.status_code == 200
    assert resp.json()["validation_errors"] == []


def _write_template(
    workspace_id: str, mappings: list[dict[str, object]], template_id: str
) -> None:
    path = Path(
        api_config.settings.workspaces_root, workspace_id, "templates", "imports"
    )
    path.mkdir(parents=True, exist_ok=True)
    record = {
        "template_id": template_id,
        "workspace_id": workspace_id,
        "name": "t",
        "field_mappings": mappings,
    }
    (path / f"{template_id}.json").write_text(json.dumps(record))


def test_apply_template_with_bad_expression_is_422_and_not_saved(
    client: TestClient, workspace_id: str
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    payload = _mapping_payload(
        [{"transform_type": "calculated_field", "params": {"expression": "'a' * 5"}}]
    )
    _write_template(workspace_id, payload["field_mappings"], "tpl1")  # type: ignore[arg-type]
    resp = client.post(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/apply-template",
        json={"template_id": "tpl1"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["field"] == "transformations"
    mapping_path = Path(
        api_config.settings.workspaces_root,
        workspace_id,
        "imports",
        import_id,
        "mapping.json",
    )
    assert not mapping_path.exists()


def test_apply_missing_template_hides_exception_text(
    client: TestClient, workspace_id: str
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    resp = client.post(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/apply-template",
        json={"template_id": "missing"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Template not found"


def _all_text_under(path: Path) -> str:
    return "".join(p.read_text(errors="ignore") for p in path.rglob("*") if p.is_file())


def test_failed_generate_keeps_cell_values_out_of_state(
    client: TestClient, workspace_id: str
) -> None:
    rows = [ROWS[0], f"E2,1985-02-02,{MARKER},60000,false,Bob,Kim\n"]
    import_id = _csv_import(client, workspace_id, rows)
    assert (
        _save(client, workspace_id, import_id, _mapping_payload([])).status_code == 200
    )

    preview = client.get(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/mapped-preview"
    )
    resp = client.post(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/generate",
        json={"census_as_of_date": "2025-12-31"},
    )

    assert resp.status_code == 422
    assert "(row 2)" in resp.json()["detail"]
    assert MARKER not in resp.text
    # Preview rows show the file by design; the messages must not repeat it.
    body = preview.json()
    messages = [w["message"] for w in body["transformation_warnings"]]
    messages.append(body["data_quality_skipped_reason"] or "")
    assert any("(row 2)" in m for m in messages)
    assert all(MARKER not in m for m in messages)
    ws = Path(api_config.settings.workspaces_root, workspace_id)
    metadata = json.loads((ws / "imports" / import_id / "metadata.json").read_text())
    assert metadata["status"] == "failed"
    assert "(row 2)" in metadata["error_message"]
    assert MARKER not in metadata["error_message"]
    assert MARKER not in _all_text_under(ws / "data" / "imports")


def test_unexpected_generate_failure_persists_a_generic_message(
    client: TestClient, workspace_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    assert (
        _save(client, workspace_id, import_id, _mapping_payload([])).status_code == 200
    )

    def _boom(*args: object, **kwargs: object) -> pd.DataFrame:
        raise RuntimeError("boom /srv/secret/path")

    monkeypatch.setattr(MappingEngine, "apply", _boom)
    resp = client.post(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/generate",
        json={"census_as_of_date": "2025-12-31"},
    )

    assert resp.status_code == 422
    assert "/srv/secret" not in resp.text
    ws = Path(api_config.settings.workspaces_root, workspace_id)
    metadata = json.loads((ws / "imports" / import_id / "metadata.json").read_text())
    assert metadata["error_message"].startswith("Import failed (error_id: ")
    assert "/srv/secret" not in _all_text_under(ws)


def test_mapped_preview_with_bad_expression_is_422(
    client: TestClient, workspace_id: str
) -> None:
    import_id = _csv_import(client, workspace_id, ROWS)
    # Bypass save-time validation to cover mappings stored before it existed.
    mapping = FieldMapping(
        input_column="FIRST",
        output_column="first_name",
        output_type="string",
        transformations=[
            Transformation(
                transform_type="calculated_field",
                params={"expression": "FIRST * 3"},
            )
        ],
    )
    path = Path(api_config.settings.workspaces_root, workspace_id, "imports", import_id)
    (path / "mapping.json").write_text(json.dumps([mapping.model_dump(mode="json")]))

    preview = client.get(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/mapped-preview"
    )
    flagged = client.get(
        f"/api/workspaces/{workspace_id}/imports/{import_id}/flagged-rows"
    )

    assert preview.status_code == 422
    assert "only on numbers" in preview.json()["detail"]
    assert flagged.status_code == 409
