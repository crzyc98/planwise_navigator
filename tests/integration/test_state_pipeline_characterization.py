"""Verify an explicitly supplied frozen A+B database against checked aggregates."""

import os
from pathlib import Path

import pytest

from planalign_orchestrator.state_pipeline_validation import (
    CharacterizationRecord,
    verify_characterization_database,
)


@pytest.mark.integration
def test_frozen_ab_database_matches_checked_characterization() -> None:
    database = os.environ.get("F122_BASELINE_DB")
    if not database:
        pytest.skip("F122_BASELINE_DB is not configured")
    characterization_path = Path(
        os.environ.get(
            "F122_CHARACTERIZATION",
            "specs/122-state-pipeline-redesign/baseline-characterization.json",
        )
    )
    assert characterization_path.exists(), "checked characterization is missing"
    characterization = CharacterizationRecord.model_validate_json(
        characterization_path.read_text()
    )

    report = verify_characterization_database(Path(database), characterization)

    assert report.passed, report.failures
    assert report.database_fingerprint == characterization.database_fingerprint
    assert all("employee" not in key.lower() for key in report.aggregate)
