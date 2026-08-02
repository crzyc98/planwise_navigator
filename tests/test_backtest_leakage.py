"""Fast tests proving held-out snapshots cannot reach fitting."""

import pytest

from planalign_fit.snapshots import Snapshot, SnapshotError, SnapshotSet
from planalign_fit import FitOptions, fit_parameter_pack
from tests.fixtures.synthetic_census import generate_history
import planalign_fit.runner as fit_runner_module

pytestmark = pytest.mark.fast


def _snapshot(year: int) -> Snapshot:
    return Snapshot(year, __file__, str(year), 1, ())


def test_subset_keeps_requested_years_and_revalidates() -> None:
    snapshots = SnapshotSet(tuple(_snapshot(year) for year in range(2021, 2025)))

    assert snapshots.subset((2021, 2022, 2023)).years == (2021, 2022, 2023)
    with pytest.raises(SnapshotError, match="consecutive"):
        snapshots.subset((2021, 2023))


def test_subset_names_requested_and_available_unknown_years() -> None:
    snapshots = SnapshotSet(tuple(_snapshot(year) for year in range(2021, 2024)))

    with pytest.raises(SnapshotError, match=r"Requested.*2024.*available.*2021.*2023"):
        snapshots.subset((2021, 2022, 2024))


def test_fitted_manifest_and_digest_cover_only_selected_years(tmp_path) -> None:
    history = generate_history(tmp_path / "history", headcount=300, years=4)
    run = fit_parameter_pack(
        history.directory,
        FitOptions(only_years=history.years[:3], credibility_k=25),
    )

    assert tuple(run.pack.manifest.snapshot_years) == tuple(history.years[:3])
    assert run.pack.manifest.source_digest == run.snapshot_set.source_digest
    assert history.years[-1] not in run.snapshot_set.years


def test_held_out_year_never_gets_a_fitting_view(tmp_path, monkeypatch) -> None:
    history = generate_history(tmp_path / "history", headcount=300, years=4)
    held_out = history.years[-1]
    original = fit_runner_module.build_transitions

    def guarded(conn, snapshot_set, bands):
        transitions = original(conn, snapshot_set, bands)
        views = {
            row[0]
            for row in conn.execute("SELECT view_name FROM duckdb_views()").fetchall()
        }
        assert f"snapshot_{held_out}" not in views
        return transitions

    monkeypatch.setattr(fit_runner_module, "build_transitions", guarded)
    fit_parameter_pack(
        history.directory,
        FitOptions(only_years=tuple(history.years[:-1]), credibility_k=25),
    )
