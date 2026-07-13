from uuid import UUID

import pytest
from pydantic import ValidationError

from planalign_api.models.provenance import InputFingerprint, RunIdentityEvidence

pytestmark = pytest.mark.fast


def test_run_identity_sorts_unique_years():
    model = RunIdentityEvidence(
        run_id=UUID("12345678-1234-5678-9234-567812345678"),
        status="future",
        completed_years=[2026, 2025, 2026],
    )
    assert model.completed_years == [2025, 2026]


@pytest.mark.parametrize(
    "name", ["/private/census.csv", "../census.csv", "seed/../../x"]
)
def test_logical_input_names_reject_paths(name):
    with pytest.raises(ValidationError):
        InputFingerprint(logical_name=name, sha256="a" * 64)


def test_models_forbid_unknown_employee_fields():
    with pytest.raises(ValidationError):
        InputFingerprint(
            logical_name="census.csv", sha256="a" * 64, employee_id="secret"
        )
