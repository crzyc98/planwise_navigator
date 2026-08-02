"""Fast tests for scorecard serialization and rendering."""

import pytest
import json
from pathlib import Path

import jsonschema

from planalign_backtest.models import (
    BacktestProvenance,
    MetricComparison,
    MetricThresholds,
    Scorecard,
    SeedRun,
    SnapshotRef,
    SnapshotSplit,
)
from planalign_backtest.report import load_scorecard, to_json, write_scorecard
from planalign_backtest.report import scorecard_is_current
from planalign_fit.apply import provenance_block
from planalign_fit.pack import PackManifest, ParameterPack, _fingerprint
from planalign_orchestrator.run_metadata import extract_param_pack_provenance
from types import SimpleNamespace

pytestmark = pytest.mark.fast


def _scorecard() -> Scorecard:
    thresholds = MetricThresholds()
    return Scorecard(
        split=SnapshotSplit(
            fit_years=(2021, 2022),
            holdout_years=(2023,),
            boundary_year=2022,
            all_years=(2021, 2022, 2023),
        ),
        seeds=(42,),
        seed_runs=(
            SeedRun(
                seed=42,
                database="seed_42.duckdb",
                config_fingerprint="config-fp",
                years_simulated=(2023,),
            ),
        ),
        thresholds=thresholds,
        comparisons=(
            MetricComparison(
                metric="headcount.total",
                period=2023,
                family="headcount",
                observable=True,
                predicted=101,
                actual=100,
                absolute_error=1,
                percent_error=0.01,
                threshold=thresholds.headcount,
                status="pass",
            ),
        ),
        provenance=BacktestProvenance(
            snapshots=(
                SnapshotRef(
                    year=2021, filename="a", sha256="a" * 64, row_count=1, role="fit"
                ),
                SnapshotRef(
                    year=2022, filename="b", sha256="b" * 64, row_count=1, role="fit"
                ),
                SnapshotRef(
                    year=2023,
                    filename="c",
                    sha256="c" * 64,
                    row_count=1,
                    role="holdout",
                ),
            ),
            source_digest="digest",
            pack_id="pack",
            pack_fingerprint="pack-fp",
            promotion_basis="measured",
            level_basis="census_level_id",
            compensation_basis="annualized rate for active employees at year end",
            backtest_date="2026-08-01T00:00:00+00:00",
            tool_version="2.2.0",
        ),
    )


def test_canonical_json_is_stable_and_round_trips(tmp_path) -> None:
    scorecard = _scorecard()
    assert to_json(scorecard) == to_json(scorecard)

    pack = tmp_path / "pack"
    json_path, markdown_path = write_scorecard(scorecard, pack)
    assert json_path.is_file() and markdown_path.is_file()
    assert load_scorecard(pack) == scorecard


def test_write_refuses_overwrite_without_force(tmp_path) -> None:
    scorecard = _scorecard()
    write_scorecard(scorecard, tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        write_scorecard(scorecard, tmp_path)


def test_emitted_scorecard_validates_against_documented_schema() -> None:
    schema_path = Path("specs/131-backtest-scorecard/contracts/scorecard.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(json.loads(to_json(_scorecard())))


def _pack() -> ParameterPack:
    fragment = {"workforce": {"total_termination_rate": 0.1}}
    seeds = {"example.csv": "name,value\na,1\n"}
    digest = "source"
    fingerprint = _fingerprint(fragment, seeds, digest)
    manifest = PackManifest(
        pack_id="pack",
        fingerprint=fingerprint,
        fit_date="2026-08-01T00:00:00+00:00",
        planalign_version="2.3.0",
        snapshot_years=[2021, 2022],
        sources=[],
        source_digest=digest,
        credibility_k=200,
        min_exposure=50,
        base_config="config/simulation_config.yaml",
        base_seeds="dbt/seeds",
    )
    return ParameterPack(manifest=manifest, config_fragment=fragment, seed_files=seeds)


def _scorecard_for_pack(pack: ParameterPack) -> Scorecard:
    original = _scorecard()
    provenance = original.provenance.model_copy(
        update={"pack_fingerprint": pack.manifest.fingerprint}
    )
    return Scorecard(
        **original.model_dump(exclude={"scorecard_fingerprint", "provenance"}),
        provenance=provenance,
    )


def test_pack_edit_makes_scorecard_stale_and_omits_provenance(tmp_path) -> None:
    pack = _pack()
    scorecard = _scorecard_for_pack(pack)
    write_scorecard(scorecard, tmp_path)
    assert scorecard_is_current(scorecard, pack)
    assert "backtest" in provenance_block(pack.manifest, pack=pack, pack_dir=tmp_path)

    edited = ParameterPack(
        manifest=pack.manifest,
        config_fragment={"workforce": {"total_termination_rate": 0.2}},
        seed_files=pack.seed_files,
    )
    assert not scorecard_is_current(scorecard, edited)
    assert "backtest" not in provenance_block(
        edited.manifest, pack=edited, pack_dir=tmp_path
    )


def test_writing_scorecard_does_not_change_pack_fingerprint(tmp_path) -> None:
    pack = _pack()
    before = _fingerprint(
        pack.config_fragment, pack.seed_files, pack.manifest.source_digest
    )
    write_scorecard(_scorecard_for_pack(pack), tmp_path)
    after = _fingerprint(
        pack.config_fragment, pack.seed_files, pack.manifest.source_digest
    )
    assert after == before == pack.manifest.fingerprint


def test_run_metadata_reference_is_compact_and_complete() -> None:
    config = SimpleNamespace(
        param_pack={
            "pack_id": "pack",
            "fingerprint": "pack-fp",
            "source_digest": "source",
            "backtest": {
                "scorecard_fingerprint": "score-fp",
                "verdict": "warn",
                "holdout_years": [2024],
            },
        }
    )
    extracted = extract_param_pack_provenance(config)
    reference = json.loads(extracted["backtest_score_ref"])
    assert reference == {
        "pack_id": "pack",
        "scorecard_fingerprint": "score-fp",
        "verdict": "warn",
        "holdout_years": [2024],
    }
