"""All supported callers emit one semantic construction signature."""

from pathlib import Path

from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator


def test_six_entry_points_share_one_semantic_signature(tmp_path):
    entry_points = (
        "cli.simulate",
        "batch",
        "studio",
        "parity",
        "invariant_test",
        "perf_harness",
    )
    results = []
    for entry_point in entry_points:
        config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
        results.append(
            build_orchestrator(
                ConstructionSpec(
                    config=config,
                    database=tmp_path / f"{entry_point}.duckdb",
                    entry_point=entry_point,
                    validation_mode=True,
                )
            )
        )

    assert [result.signature.entry_point for result in results] == list(entry_points)
    assert len({result.signature.signature_hash for result in results}) == 1
    assert len({result.signature.database_path for result in results}) == 6
