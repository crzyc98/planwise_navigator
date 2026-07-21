"""Product entry points resolve one semantic construction."""

import hashlib
from pathlib import Path

from planalign_api.services.simulation.service import SimulationService
from planalign_orchestrator.config import load_simulation_config
from planalign_orchestrator.construction import ConstructionSpec, build_orchestrator


SHARED_DATABASE = Path("dbt/simulation.duckdb")


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_product_entrypoints_share_signature_and_studio_origin(tmp_path):
    before = _sha256(SHARED_DATABASE)
    hashes = []
    for entry_point in ("cli.simulate", "batch", "studio"):
        config = load_simulation_config(Path("tests/fixtures/invariant_config.yaml"))
        result = build_orchestrator(
            ConstructionSpec(
                config=config,
                database=tmp_path / f"{entry_point}.duckdb",
                entry_point=entry_point,
                validation_mode=True,
            )
        )
        hashes.append(result.signature.signature_hash)

    env = SimulationService._build_env(Path.cwd(), run_id="test-run")

    assert len(set(hashes)) == 1
    assert env["PLANALIGN_ENTRY_POINT"] == "studio"
    assert _sha256(SHARED_DATABASE) == before
