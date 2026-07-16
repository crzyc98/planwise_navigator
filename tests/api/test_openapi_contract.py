"""OpenAPI schema contract tests (Feature 115, US1; issue #439).

Compares the live generated OpenAPI schema against a committed snapshot so
that unintentional changes to paths, methods, or response models fail with a
reviewable diff. To update the snapshot after an intentional API change, see
specs/115-api-contract-tests/quickstart.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from planalign_api.main import create_app
from planalign_api.models.system import HealthResponse, SystemStatus

pytestmark = [pytest.mark.fast]

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "openapi_schema.json"


def _diff_openapi(baseline: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Summarize path/method/schema differences between two OpenAPI documents."""
    differences: list[str] = []

    baseline_paths = baseline.get("paths", {})
    actual_paths = actual.get("paths", {})
    for path in sorted(set(actual_paths) - set(baseline_paths)):
        differences.append(f"added path: {path}")
    for path in sorted(set(baseline_paths) - set(actual_paths)):
        differences.append(f"removed path: {path}")
    for path in sorted(set(baseline_paths) & set(actual_paths)):
        baseline_ops = baseline_paths[path]
        actual_ops = actual_paths[path]
        for method in sorted(set(actual_ops) - set(baseline_ops)):
            differences.append(f"added method: {method.upper()} {path}")
        for method in sorted(set(baseline_ops) - set(actual_ops)):
            differences.append(f"removed method: {method.upper()} {path}")
        for method in sorted(set(baseline_ops) & set(actual_ops)):
            if baseline_ops[method] != actual_ops[method]:
                differences.append(f"changed operation: {method.upper()} {path}")

    baseline_schemas = baseline.get("components", {}).get("schemas", {})
    actual_schemas = actual.get("components", {}).get("schemas", {})
    for name in sorted(set(actual_schemas) - set(baseline_schemas)):
        differences.append(f"added schema: {name}")
    for name in sorted(set(baseline_schemas) - set(actual_schemas)):
        differences.append(f"removed schema: {name}")
    for name in sorted(set(baseline_schemas) & set(actual_schemas)):
        if baseline_schemas[name] != actual_schemas[name]:
            differences.append(f"changed schema: {name}")

    return differences


def test_openapi_schema_matches_committed_snapshot() -> None:
    baseline = json.loads(SNAPSHOT_PATH.read_text())
    # Round-trip through JSON so tuples/ints compare identically to the file.
    actual = json.loads(json.dumps(create_app().openapi()))

    if actual == baseline:
        return

    differences = _diff_openapi(baseline, actual) or [
        "schema differs outside paths/components (e.g. info/title/version)"
    ]
    summary = "\n  ".join(differences)
    pytest.fail(
        "OpenAPI schema drifted from the committed snapshot:\n"
        f"  {summary}\n"
        "If this change is intentional, regenerate the snapshot per "
        "specs/115-api-contract-tests/quickstart.md and review the diff."
    )


def test_health_response_conforms_to_model(client_factory) -> None:
    client = client_factory("shared-secret")

    response = client.get("/api/health")

    assert response.status_code == 200
    HealthResponse.model_validate(response.json())


def test_system_status_response_conforms_to_model(client_factory) -> None:
    client = client_factory("shared-secret")

    response = client.get(
        "/api/system/status",
        headers={"Authorization": "Bearer shared-secret"},
    )

    assert response.status_code == 200
    SystemStatus.model_validate(response.json())


def test_config_defaults_response_conforms_to_declared_shape(client_factory) -> None:
    client = client_factory("shared-secret")

    response = client.get(
        "/api/config/defaults",
        headers={"Authorization": "Bearer shared-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    # Declared response model is Dict[str, Any]; assert the declared shape.
    assert isinstance(body, dict)
    assert body, "expected a non-empty default configuration"
