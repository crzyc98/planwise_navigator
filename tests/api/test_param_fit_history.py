"""Studio census history sets for parameter fitting (#588, US1)."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from tests.fixtures.param_fit import StubCommands, history_files, make_harness

pytestmark = [pytest.mark.fast]


@pytest.fixture(scope="module")
def three_years(tmp_path_factory) -> list[Path]:
    return history_files(tmp_path_factory.mktemp("history") / "census", years=3)


@pytest.fixture
def harness(tmp_path):
    return make_harness(tmp_path, StubCommands(fixture_pack=tmp_path / "unused"))


def test_upload_previews_every_snapshot(harness, three_years):
    response = harness.upload(three_years)

    assert response.status_code == 201, response.text
    body = response.json()
    years = [snapshot["year"] for snapshot in body["snapshots"]]
    assert years == [2022, 2023, 2024]
    first = body["snapshots"][0]
    assert first["sha256"] == hashlib.sha256(three_years[0].read_bytes()).hexdigest()
    assert first["row_count"] > 0
    assert first["as_of_date"] == "2022-12-31"
    assert len(body["source_digest"]) == 64


def test_upload_previews_both_backtest_splits(harness, three_years):
    body = harness.upload(three_years).json()
    splits = {item["holdout_years"]: item for item in body["splits"]}

    one = splits[1]["split"]
    assert one["fit_years"] == [2022, 2023]
    assert one["holdout_years"] == [2024]
    assert one["boundary_year"] == 2023
    assert one["simulation_effective_date"] == "2024-12-31"
    assert splits[2]["split"] is None
    assert "leaves 1 year to fit" in splits[2]["error"]
    assert "--holdout" not in splits[2]["error"]
    assert "Choose a 1-year holdout" in splits[2]["error"]


def test_year_gap_is_rejected_and_nothing_is_kept(harness, three_years, tmp_path):
    response = harness.upload([three_years[0], three_years[2]])

    assert response.status_code == 422
    assert "consecutive" in response.json()["detail"]
    assert harness.client.get(harness.url("/fit-history")).json() == []


def test_single_snapshot_is_rejected(harness, three_years):
    response = harness.upload(three_years[:1])

    assert response.status_code == 422
    assert "at least 2" in response.json()["detail"]


def test_duplicate_year_is_rejected(harness, three_years, tmp_path):
    copy = tmp_path / "census_2022_copy.csv"
    shutil.copy(three_years[0], copy)
    response = harness.upload([three_years[0], copy, three_years[1]])

    assert response.status_code == 422


def test_non_census_extension_is_rejected(harness, tmp_path):
    bogus = tmp_path / "census_2022.txt"
    bogus.write_text("nope")
    response = harness.upload([bogus, bogus])

    assert response.status_code == 422
    assert "not a .parquet or .csv" in response.json()["detail"]


def test_errors_never_echo_server_paths(harness, tmp_path):
    broken = tmp_path / "census_2022.csv"
    broken.write_text("employee_id\nE1\n")
    other = tmp_path / "census_2023.csv"
    other.write_text("employee_id\nE1\n")

    response = harness.upload([broken, other])

    assert response.status_code == 422
    assert str(tmp_path) not in response.json()["detail"]


def test_list_get_and_delete(harness, three_years):
    created = harness.upload(three_years).json()
    history_id = created["history_id"]

    listed = harness.client.get(harness.url("/fit-history")).json()
    fetched = harness.client.get(harness.url(f"/fit-history/{history_id}")).json()
    deleted = harness.client.delete(harness.url(f"/fit-history/{history_id}"))

    assert [item["history_id"] for item in listed] == [history_id]
    assert fetched["source_digest"] == created["source_digest"]
    assert deleted.status_code == 204
    missing = harness.client.get(harness.url(f"/fit-history/{history_id}"))
    assert missing.status_code == 404


def test_get_rehashes_the_stored_files(harness, three_years):
    created = harness.upload(three_years).json()
    history_id = created["history_id"]
    stored = harness.storage.workspaces_root / harness.workspace_id / "fit_history"
    target = next((stored / history_id / "files").glob("*2024*"))
    target.write_text(target.read_text() + target.read_text().splitlines()[1] + "\n")

    fetched = harness.client.get(harness.url(f"/fit-history/{history_id}")).json()

    assert fetched["source_digest"] != created["source_digest"]


def test_unknown_workspace_is_404(harness, three_years):
    response = harness.client.post(
        "/api/workspaces/nope/fit-history",
        files=[("files", (p.name, p.read_bytes(), "text/csv")) for p in three_years],
    )
    assert response.status_code == 404


def test_path_like_history_id_is_404(harness):
    response = harness.client.get(harness.url("/fit-history/..%2F..%2Fetc"))
    assert response.status_code == 404
