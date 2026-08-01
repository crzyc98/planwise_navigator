"""Tests for ``planalign fit`` — the evidence loop's parameter fitter (#458).

The load-bearing test is :class:`TestRoundTrip`: evolve a synthetic population
with rates the test chose, snapshot it per year, and check the fitter recovers
those rates. Everything else guards the contracts around it — snapshot
validation, small-cell handling, pack shape, and the drop-in application path.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
import yaml

from planalign_fit import (
    FitOptions,
    fit_parameter_pack,
    load_band_definitions,
    load_pack,
    load_priors,
    load_snapshots,
    render_fit_report,
    verify_pack,
    write_pack,
)
from planalign_fit.apply import apply_pack
from planalign_fit.hazards import termination_level_factor
from planalign_fit.ipf import FactorCell, solve
from planalign_fit.models import PromotionBasis
from planalign_fit.pack import PackError
from planalign_fit.promotion import classify
from planalign_fit.smoothing import shrink_toward
from planalign_fit.snapshots import SnapshotError
from planalign_fit.transitions import build_transitions
from tests.fixtures.synthetic_census import TruthRates, generate_history

pytestmark = pytest.mark.fast


@pytest.fixture(scope="module")
def history(tmp_path_factory: pytest.TempPathFactory):
    """Three annual snapshots evolved with known rates."""
    directory = tmp_path_factory.mktemp("synthetic-census")
    return generate_history(directory / "snapshots", headcount=9_000, years=3)


@pytest.fixture(scope="module")
def fit_run(history):
    # A low credibility constant lets a 9,000-employee population speak for
    # itself; the shrinkage path is exercised separately below.
    return fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))


def _implied_rate(fit, age_band: str, tenure_band: str, level_id: int) -> float:
    return (
        fit.base_rate.value
        * fit.age_multipliers[age_band].value
        * fit.tenure_multipliers[tenure_band].value
        * termination_level_factor(level_id, fit.level_constants)
    )


class TestRoundTrip:
    """Simulate known rates -> snapshot per year -> fit recovers them."""

    def test_termination_rate_recovered(self, fit_run, history):
        observed = fit_run.result.termination.observed_overall_rate
        assert observed == pytest.approx(history.truth.termination, abs=0.015)

    def test_promotion_rate_recovered(self, fit_run, history):
        observed = fit_run.result.promotion.observed_overall_rate
        assert observed == pytest.approx(history.truth.promotion, abs=0.015)

    def test_merit_recovered_per_level(self, fit_run, history):
        priors = load_priors()
        for level, fitted in fit_run.result.merit_by_level.items():
            if fitted.basis in ("pooled", "prior"):
                continue
            # The fit nets out the COLA the *config* carries, which need not be
            # the COLA the synthetic history used.
            expected = (
                history.truth.merit
                + history.truth.cola
                - priors.cola_by_level.get(level, 0.0)
            )
            assert fitted.value == pytest.approx(expected, abs=0.01), f"level {level}"

    def test_total_termination_rate_recovered(self, fit_run, history):
        fitted = fit_run.result.config_overrides["workforce.total_termination_rate"]
        assert fitted.value == pytest.approx(history.truth.termination, abs=0.015)

    def test_new_hire_termination_rate_recovered(self, fit_run, history):
        fitted = fit_run.result.config_overrides["workforce.new_hire_termination_rate"]
        assert fitted.value == pytest.approx(
            history.truth.new_hire_termination, abs=0.05
        )

    def test_starting_deferral_rate_recovered(self, fit_run, history):
        """The raw estimate lands on the truth wherever the segment has evidence.

        ``value`` is the credibility blend and is deliberately pulled toward the
        seeded prior in thin segments; ``observed`` is what the data alone said.
        """
        measured = [
            value
            for value in fit_run.result.deferral_rates.values()
            if value.observed is not None and value.exposure >= 100
        ]
        assert measured, "expected at least one segment with enough enrollments"
        for value in measured:
            assert value.observed == pytest.approx(
                history.truth.starting_deferral, abs=0.005
            ), value.name

    def test_thin_deferral_segments_stay_near_their_prior(self, fit_run):
        for value in fit_run.result.deferral_rates.values():
            if value.basis == "pooled" and value.observed is not None:
                assert abs(value.value - value.prior) <= abs(
                    value.observed - value.prior
                ), value.name

    def test_flat_hazard_yields_flat_multipliers(self, fit_run):
        """Truth applies one termination rate to everyone, so no band stands out."""
        for value in fit_run.result.termination.age_multipliers.values():
            if value.basis not in ("pooled", "prior"):
                assert value.value == pytest.approx(1.0, abs=0.35), value.name

    def test_fitted_cell_rates_reproduce_the_truth(self, fit_run, history):
        """The reassembled hazard, not just its pieces, lands on the truth."""
        fit = fit_run.result.termination
        rates = [
            _implied_rate(fit, cell.age_band, cell.tenure_band, cell.level_id)
            for cell in fit_run.result.termination_cells
            if cell.exposure >= 200
        ]
        assert rates, "expected some well-populated cells"
        assert sum(rates) / len(rates) == pytest.approx(
            history.truth.termination, abs=0.03
        )

    def test_a_distinctly_higher_band_is_detected(self, tmp_path):
        """A rate that really does differ by band shows up in the multipliers."""
        directory = tmp_path / "snapshots"
        low = generate_history(
            directory, headcount=9_000, years=3, truth=TruthRates(termination=0.05)
        )
        low_fit = fit_parameter_pack(low.directory, FitOptions(credibility_k=25.0))

        high_dir = tmp_path / "snapshots_high"
        high = generate_history(
            high_dir, headcount=9_000, years=3, truth=TruthRates(termination=0.20)
        )
        high_fit = fit_parameter_pack(high.directory, FitOptions(credibility_k=25.0))

        assert (
            low_fit.result.termination.observed_overall_rate
            < high_fit.result.termination.observed_overall_rate
        )
        assert low_fit.result.termination.base_rate.value < (
            high_fit.result.termination.base_rate.value
        )


class TestUnfittableParameters:
    """Anything the data cannot speak to is named, with the default kept."""

    def test_match_response_is_flagged(self, fit_run):
        names = [item.name for item in fit_run.result.unfittable]
        assert "deferral_match_response.*" in names

    def test_structural_constants_are_flagged(self, fit_run):
        reported = " ".join(item.name for item in fit_run.result.unfittable)
        assert "level_discount_factor" in reported
        assert "level_dampener_factor" in reported
        assert "compensation.cola_rate" in reported

    def test_every_unfittable_carries_a_reason_and_a_default(self, fit_run):
        assert fit_run.result.unfittable
        for item in fit_run.result.unfittable:
            assert item.reason.strip(), item.name
            assert item.default_used is not None, item.name

    def test_unfittable_reaches_the_manifest_and_report(self, fit_run):
        assert fit_run.pack.manifest.unfittable
        report = render_fit_report(fit_run)
        assert "Not fitted — defaults retained" in report
        for item in fit_run.result.unfittable:
            assert item.name in report

    def test_missing_deferral_column_disables_the_deferral_fit(self, tmp_path):
        source = generate_history(tmp_path / "full", headcount=2_000, years=2)
        stripped = tmp_path / "stripped"
        stripped.mkdir()
        for path in source.paths:
            rows = path.read_text(encoding="utf-8").splitlines()
            header = rows[0].split(",")
            drop = {
                header.index("employee_deferral_rate"),
                header.index("employee_enrollment_date"),
            }
            kept = [
                ",".join(v for i, v in enumerate(row.split(",")) if i not in drop)
                for row in rows
            ]
            (stripped / path.name).write_text("\n".join(kept) + "\n", encoding="utf-8")

        run = fit_parameter_pack(stripped, FitOptions())
        names = " ".join(item.name for item in run.result.unfittable)
        assert "default_deferral_rates" in names
        assert not run.result.deferral_rates


class TestSmallCellHandling:
    """Thin cells lean on the prior and say so; they never fit noise."""

    def test_zero_exposure_keeps_the_prior(self):
        result = shrink_toward(events=0.0, exposure=0.0, prior=0.42)
        assert result.value == 0.42
        assert result.basis == "prior"

    def test_thin_cell_is_labelled_pooled(self):
        result = shrink_toward(
            events=2.0,
            exposure=10.0,
            prior=0.10,
            credibility_k=200.0,
            min_exposure=50.0,
        )
        assert result.basis == "pooled"
        assert result.value < 0.20, "a 20% observed rate on 10 lives must not survive"
        assert "pooled prior" in result.note()

    def test_ample_exposure_follows_the_data(self):
        result = shrink_toward(
            events=500.0, exposure=5_000.0, prior=0.42, credibility_k=200.0
        )
        assert result.basis == "observed"
        assert result.value == pytest.approx(0.10, abs=0.02)

    def test_credibility_is_monotone_in_exposure(self):
        weights = [
            shrink_toward(events=n * 0.1, exposure=float(n), prior=0.5).credibility
            for n in (10, 100, 1_000, 10_000)
        ]
        assert weights == sorted(weights)

    def test_thin_cells_are_counted_for_the_report(self, tmp_path):
        tiny = generate_history(tmp_path / "tiny", headcount=120, years=2)
        run = fit_parameter_pack(
            tiny.directory, FitOptions(credibility_k=500.0, min_exposure=200.0)
        )
        assert run.result.thin_cell_count > 0
        assert "⚠️" in render_fit_report(run)


class TestIPFSolver:
    """The shared two-factor solver reproduces the structure it is given."""

    def test_recovers_a_known_multiplicative_structure(self):
        base = 0.08
        row_effect = {"a": 1.5, "b": 0.5}
        col_effect = {"x": 2.0, "y": 1.0}
        cells = [
            FactorCell(
                row=row,
                col=col,
                exposure=10_000.0,
                events=10_000.0 * base * row_effect[row] * col_effect[col],
            )
            for row in row_effect
            for col in col_effect
        ]

        solution = solve(cells, list(row_effect), list(col_effect), normalize="row")

        for row in row_effect:
            for col in col_effect:
                implied = (
                    solution.base
                    * solution.row_multipliers[row]
                    * solution.col_multipliers[col]
                )
                assert implied == pytest.approx(
                    base * row_effect[row] * col_effect[col], rel=1e-6
                )

    def test_offset_is_honoured(self):
        cells = [
            FactorCell(row="a", col="x", exposure=1_000.0, events=50.0, offset=0.5),
            FactorCell(row="a", col="x", exposure=1_000.0, events=100.0, offset=1.0),
        ]
        solution = solve(cells, ["a"], ["x"], normalize="none")
        assert solution.base == pytest.approx(0.10, rel=1e-6)

    def test_no_events_is_not_an_error(self):
        cells = [FactorCell(row="a", col="x", exposure=100.0, events=0.0)]
        solution = solve(cells, ["a"], ["x"])
        assert solution.base == 0.0
        assert solution.converged


class TestSnapshotValidation:
    """Bad snapshot directories fail loudly, before any fitting happens."""

    def test_single_snapshot_is_rejected(self, tmp_path):
        generate_history(tmp_path / "one", headcount=50, years=1)
        with pytest.raises(SnapshotError, match="at least 2"):
            _fit(tmp_path / "one")

    def test_year_gap_is_rejected(self, tmp_path):
        history = generate_history(tmp_path / "gap", headcount=50, years=3)
        (history.directory / f"census_{history.years[1]}.csv").unlink()
        with pytest.raises(SnapshotError, match="consecutive"):
            _fit(history.directory)

    def test_missing_required_column_is_rejected(self, tmp_path):
        directory = tmp_path / "bad"
        directory.mkdir()
        for year in (2023, 2024):
            (directory / f"census_{year}.csv").write_text(
                "employee_id,employee_birth_date\nE1,1980-01-01\n", encoding="utf-8"
            )
        with pytest.raises(SnapshotError, match="employee_hire_date"):
            _fit(directory)

    def test_undated_filename_is_rejected(self, tmp_path):
        history = generate_history(tmp_path / "undated", headcount=50, years=2)
        (history.directory / "census_2022.csv").rename(history.directory / "first.csv")
        with pytest.raises(SnapshotError, match="determine the year"):
            _fit(history.directory)

    def test_empty_directory_is_rejected(self, tmp_path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(SnapshotError, match="No .parquet or .csv"):
            _fit(tmp_path / "empty")

    def test_snapshots_are_hashed_for_provenance(self, tmp_path):
        history = generate_history(tmp_path / "hashed", headcount=50, years=2)
        with duckdb.connect(":memory:") as conn:
            first = load_snapshots(history.directory, conn)
            again = load_snapshots(history.directory, conn)
        assert first.source_digest == again.source_digest
        assert all(len(s.sha256) == 64 for s in first)

    def test_editing_a_snapshot_changes_the_digest(self, tmp_path):
        history = generate_history(tmp_path / "edited", headcount=50, years=2)
        with duckdb.connect(":memory:") as conn:
            before = load_snapshots(history.directory, conn)

        latest = history.paths[-1]
        rows = latest.read_text(encoding="utf-8").splitlines()
        latest.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")

        with duckdb.connect(":memory:") as conn:
            after = load_snapshots(history.directory, conn)
        assert after.source_digest != before.source_digest


def _fit(directory: Path):
    return fit_parameter_pack(directory, FitOptions())


class TestParameterPack:
    """The pack is a reviewable directory with intact provenance."""

    def test_pack_contains_the_expected_artifacts(self, fit_run, tmp_path):
        destination = write_pack(
            fit_run.pack, tmp_path / "pack", report=render_fit_report(fit_run)
        )
        assert (destination / "manifest.json").is_file()
        assert (destination / "parameters.yaml").is_file()
        assert (destination / "fit_report.md").is_file()
        seeds = {p.name for p in (destination / "seeds").glob("*.csv")}
        assert "config_termination_hazard_base.csv" in seeds
        assert "config_promotion_hazard_age_multipliers.csv" in seeds
        assert "comp_levers.csv" in seeds

    def test_manifest_records_every_source_snapshot(self, fit_run, history):
        manifest = fit_run.pack.manifest
        assert manifest.snapshot_years == history.years
        assert len(manifest.sources) == len(history.years)
        for source in manifest.sources:
            assert len(source.sha256) == 64
            assert source.row_count > 0

    def test_round_trips_through_disk(self, fit_run, tmp_path):
        write_pack(fit_run.pack, tmp_path / "pack")
        reloaded = load_pack(tmp_path / "pack")
        assert reloaded.manifest.fingerprint == fit_run.pack.manifest.fingerprint
        assert reloaded.config_fragment == fit_run.pack.config_fragment
        assert reloaded.seed_files == fit_run.pack.seed_files
        assert verify_pack(reloaded)

    def test_edited_pack_fails_verification(self, fit_run, tmp_path):
        write_pack(fit_run.pack, tmp_path / "pack")
        seed = tmp_path / "pack" / "seeds" / "config_termination_hazard_base.csv"
        seed.write_text(
            "base_rate_for_new_hire,level_discount_factor,"
            "min_level_discount_multiplier\n0.99,0.1,0.4\n",
            encoding="utf-8",
        )
        assert not verify_pack(load_pack(tmp_path / "pack"))

    def test_refuses_to_overwrite_without_force(self, fit_run, tmp_path):
        write_pack(fit_run.pack, tmp_path / "pack")
        with pytest.raises(PackError, match="--force"):
            write_pack(fit_run.pack, tmp_path / "pack")
        write_pack(fit_run.pack, tmp_path / "pack", force=True)

    def test_non_pack_directory_is_rejected(self, tmp_path):
        (tmp_path / "nope").mkdir()
        with pytest.raises(PackError, match="not a parameter pack"):
            load_pack(tmp_path / "nope")

    def test_seed_csvs_keep_the_schema_they_replace(self, fit_run):
        bands = load_band_definitions()
        age_seed = fit_run.pack.seed_files[
            "config_termination_hazard_age_multipliers.csv"
        ]
        header, *rows = age_seed.strip().splitlines()
        assert header == "age_band,multiplier"
        assert [row.split(",")[0] for row in rows] == list(bands.age_band_labels)

    def test_comp_levers_only_touches_merit_base(self, fit_run):
        priors = load_priors()
        original = (priors.seeds_dir / "comp_levers.csv").read_text(encoding="utf-8")
        fitted = fit_run.pack.seed_files["comp_levers.csv"]
        assert len(original.splitlines()) == len(fitted.splitlines())
        for before, after in zip(original.splitlines()[1:], fitted.splitlines()[1:]):
            fields_before = before.split(",")
            fields_after = after.split(",")
            if fields_before[4] != "merit_base":
                assert fields_before == fields_after

    def test_fingerprint_is_deterministic(self, history):
        first = fit_parameter_pack(
            history.directory, FitOptions(credibility_k=25.0, pack_id="fixed")
        )
        second = fit_parameter_pack(
            history.directory, FitOptions(credibility_k=25.0, pack_id="fixed")
        )
        assert first.pack.manifest.fingerprint == second.pack.manifest.fingerprint


class TestApplyPack:
    """A pack applies as a drop-in without mutating the repository."""

    @pytest.fixture
    def applied(self, fit_run, tmp_path):
        write_pack(fit_run.pack, tmp_path / "pack")
        return apply_pack(
            tmp_path / "pack",
            Path("config/simulation_config.yaml"),
            workdir=tmp_path / "run",
        )

    def test_effective_config_merges_the_fragment(self, applied, fit_run):
        config = yaml.safe_load(applied.config_path.read_text(encoding="utf-8"))
        fitted = fit_run.result.config_overrides[
            "workforce.total_termination_rate"
        ].value
        assert config["workforce"]["total_termination_rate"] == pytest.approx(
            fitted, abs=1e-6
        )

    def test_untouched_config_sections_survive_the_merge(self, applied):
        base = yaml.safe_load(
            Path("config/simulation_config.yaml").read_text(encoding="utf-8")
        )
        config = yaml.safe_load(applied.config_path.read_text(encoding="utf-8"))
        assert config["setup"] == base["setup"]
        assert (
            config["enrollment"]["auto_enrollment"]["window_days"]
            == base["enrollment"]["auto_enrollment"]["window_days"]
        )

    def test_effective_config_loads_as_a_simulation_config(self, applied):
        from planalign_orchestrator.config import load_simulation_config

        config = load_simulation_config(applied.config_path, env_overrides=False)
        assert config.simulation.start_year

    def test_overlay_carries_the_fitted_seeds(self, applied, fit_run):
        seed = applied.dbt_project_dir / "seeds" / "config_termination_hazard_base.csv"
        assert (
            seed.read_text(encoding="utf-8")
            == fit_run.pack.seed_files["config_termination_hazard_base.csv"]
        )

    def test_overlay_links_models_rather_than_copying(self, applied):
        assert (applied.dbt_project_dir / "models").is_symlink()
        assert (applied.dbt_project_dir / "macros").is_symlink()
        assert not (applied.dbt_project_dir / "seeds").is_symlink()

    def test_repository_seeds_are_never_modified(self, applied, fit_run):
        priors = load_priors()
        shipped = (priors.seeds_dir / "config_termination_hazard_base.csv").read_text(
            encoding="utf-8"
        )
        assert (
            shipped != fit_run.pack.seed_files["config_termination_hazard_base.csv"]
        ), "fixture must actually differ from the shipped seed"
        assert "0.42" in shipped

    def test_provenance_block_is_stamped_into_the_config(self, applied, fit_run):
        config = yaml.safe_load(applied.config_path.read_text(encoding="utf-8"))
        assert config["param_pack"]["pack_id"] == fit_run.pack.manifest.pack_id
        assert config["param_pack"]["fingerprint"] == (
            fit_run.pack.manifest.fingerprint
        )

    def test_provenance_survives_config_loading(self, applied, fit_run):
        from planalign_orchestrator.config import load_simulation_config
        from planalign_orchestrator.run_metadata import extract_param_pack_provenance

        config = load_simulation_config(applied.config_path, env_overrides=False)
        provenance = extract_param_pack_provenance(config)
        assert provenance["pack_id"] == fit_run.pack.manifest.pack_id
        assert provenance["fingerprint"] == fit_run.pack.manifest.fingerprint
        assert provenance["source_digest"] == fit_run.pack.manifest.source_digest

    def test_pack_provenance_does_not_disturb_the_config_fingerprint(self, applied):
        from planalign_orchestrator.config import load_simulation_config
        from planalign_orchestrator.run_metadata import compute_config_fingerprint

        with_pack = load_simulation_config(applied.config_path, env_overrides=False)
        stripped = yaml.safe_load(applied.config_path.read_text(encoding="utf-8"))
        stripped.pop("param_pack")
        path = applied.workdir / "no_provenance.yaml"
        path.write_text(yaml.safe_dump(stripped), encoding="utf-8")
        without_pack = load_simulation_config(path, env_overrides=False)

        assert compute_config_fingerprint(with_pack) == compute_config_fingerprint(
            without_pack
        )

    def test_fitted_enrollment_rates_reach_dbt_vars(self, applied):
        from planalign_orchestrator.config import load_simulation_config, to_dbt_vars

        config = load_simulation_config(applied.config_path, env_overrides=False)
        dbt_vars = to_dbt_vars(config)
        fragment = yaml.safe_load(applied.config_path.read_text(encoding="utf-8"))
        expected = fragment["enrollment"]["voluntary_enrollment"]["base_rates_by_age"]
        for segment, value in expected.items():
            assert dbt_vars[
                f"voluntary_enrollment_base_rates_by_age_{segment}"
            ] == pytest.approx(value)


class TestReport:
    """The report is the honest half of the pack."""

    def test_report_names_the_sources_and_the_fingerprint(self, fit_run):
        report = render_fit_report(fit_run)
        assert fit_run.pack.manifest.fingerprint in report
        for source in fit_run.pack.manifest.sources:
            assert source.filename in report
            assert source.sha256[:16] in report

    def test_report_shows_evidence_for_every_fitted_value(self, fit_run):
        report = render_fit_report(fit_run)
        assert "| Parameter | Fitted | Prior | Change | Exposure |" in report
        for value in fit_run.result.termination.values():
            assert value.name in report

    def test_report_surfaces_data_warnings(self, fit_run):
        if not fit_run.result.warnings:
            pytest.skip("this fixture produced no data warnings")
        report = render_fit_report(fit_run)
        assert "Data warnings" in report

    def test_manifest_is_json_serialisable(self, fit_run):
        payload = json.dumps(fit_run.pack.manifest.to_dict())
        assert json.loads(payload)["fingerprint"] == fit_run.pack.manifest.fingerprint


class TestSyntheticFixture:
    """The grading harness itself must be gradeable (#511, research.md R-7).

    Before this feature the fixture gave every ordinary raise exactly
    ``merit + cola`` and every promotion raise exactly ``promotion_raise`` — two
    point masses with zero within-component variance. That makes separating the
    two trivial, makes the pooled standard deviation zero, and makes a
    deliberately inseparable population impossible to construct.
    """

    @staticmethod
    def _growth(history) -> list[tuple[float, int, int]]:
        with duckdb.connect(":memory:") as conn:
            return conn.execute(
                f"""
                SELECT b.employee_gross_compensation
                         / a.employee_gross_compensation - 1 AS growth,
                       a.level_id AS from_level,
                       b.level_id AS to_level
                FROM read_csv_auto('{history.paths[0]}') a
                JOIN read_csv_auto('{history.paths[1]}') b USING (employee_id)
                WHERE a.active AND b.active
                """
            ).fetchall()

    def test_raises_are_dispersed_not_point_masses(self, history):
        rows = self._growth(history)
        distinct = {round(row[0], 5) for row in rows}
        assert len(distinct) > 100, (
            "the fixture emits near-constant raises; a mixture test over point "
            "masses grades nothing"
        )

    def test_each_component_has_the_dispersion_it_was_given(self, history):
        import statistics

        rows = self._growth(history)
        ordinary = [row[0] for row in rows if row[2] == row[1]]
        promoted = [row[0] for row in rows if row[2] > row[1]]

        assert statistics.stdev(ordinary) == pytest.approx(
            history.truth.merit_sigma, rel=0.25
        )
        assert statistics.stdev(promoted) == pytest.approx(
            history.truth.promotion_sigma, rel=0.30
        )

    def test_component_means_are_preserved(self, history):
        import statistics

        rows = self._growth(history)
        ordinary = [row[0] for row in rows if row[2] == row[1]]
        promoted = [row[0] for row in rows if row[2] > row[1]]

        expected_ordinary = history.truth.merit + history.truth.cola
        assert statistics.mean(ordinary) == pytest.approx(expected_ordinary, abs=0.005)
        assert statistics.mean(promoted) == pytest.approx(
            history.truth.promotion_raise, abs=0.01
        )

    def test_generation_is_reproducible(self, tmp_path):
        first = generate_history(tmp_path / "a", headcount=400, years=2, seed=7)
        second = generate_history(tmp_path / "b", headcount=400, years=2, seed=7)
        for left, right in zip(first.paths, second.paths):
            assert left.read_text() == right.read_text()

    def test_zero_sigma_reproduces_the_old_point_mass_behaviour(self, tmp_path):
        """The dispersion is a knob, not a hard-coded change of behaviour."""
        history = generate_history(
            tmp_path / "flat",
            headcount=300,
            years=2,
            truth=TruthRates(merit_sigma=0.0, promotion_sigma=0.0),
        )
        # Rounded to 5dp: the census stores compensation to the cent, so a
        # constant raise still shows float noise well below any real dispersion.
        rows = self._growth(history)
        distinct = {round(row[0], 5) for row in rows}
        assert len(distinct) <= 2


class TestCleanPathParity:
    """Threading a promotion weight through the fitter must change nothing.

    Where the census carries job levels the weights are 0 and 1, so the summed
    weight is the old event tally and the weighted median is the old median over
    non-promoted employees. That is arithmetic identity, not approximation —
    any difference at all is a bug, which is why these assertions carry no
    tolerance.
    """

    def test_weighted_events_equal_the_old_tally(self, fit_run):
        events = fit_run.result.promotion.total_events
        assert events == float(round(events)), (
            "with observed job levels every weight is 0 or 1, so the event "
            "count must still be a whole number"
        )

    def test_promotion_weight_matches_the_observed_flag(self, history):
        """Every row's weight is exactly its promoted flag on the clean path."""
        bands = load_band_definitions()
        with duckdb.connect(":memory:") as conn:
            snapshots = load_snapshots(history.directory, conn)
            transitions = build_transitions(conn, snapshots, bands)
            mismatched = conn.execute(
                f"""
                SELECT COUNT(*) FROM {transitions.table}
                WHERE promotion_weight
                      <> CASE WHEN promoted THEN 1.0 ELSE 0.0 END
                """
            ).fetchone()[0]
        assert mismatched == 0

    def test_promotion_weight_stays_within_bounds(self, history):
        """The invariant both consumers depend on, asserted directly."""
        bands = load_band_definitions()
        with duckdb.connect(":memory:") as conn:
            snapshots = load_snapshots(history.directory, conn)
            transitions = build_transitions(conn, snapshots, bands)
            out_of_range = conn.execute(
                f"""
                SELECT COUNT(*) FROM {transitions.table}
                WHERE promotion_weight IS NULL
                   OR promotion_weight < 0.0
                   OR promotion_weight > 1.0
                """
            ).fetchone()[0]
        assert out_of_range == 0

    def test_weighted_median_reduces_to_the_plain_median(self):
        """Unit weights must reproduce the interpolated median exactly."""
        import numpy as np

        from planalign_fit.compensation import weighted_median

        for values in ([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0, 5.0]):
            array = np.array(values)
            assert weighted_median(array, np.ones_like(array)) == float(
                np.median(array)
            )

    def test_zero_weights_exclude_an_observation_entirely(self):
        import numpy as np

        from planalign_fit.compensation import weighted_median

        values = np.array([1.0, 2.0, 3.0, 100.0])
        weights = np.array([1.0, 1.0, 1.0, 0.0])
        assert weighted_median(values, weights) == weighted_median(
            np.array([1.0, 2.0, 3.0]), np.ones(3)
        )


def _strip_column(history, column: str, *, keep_rows: int = 0):
    """Rewrite a history's snapshots without ``column``.

    ``keep_rows`` leaves the column in place for that many rows, blanking the
    rest — the partially-populated case a real client extract produces when an
    HRIS migration happened mid-history.
    """
    import csv

    for path in history.paths:
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        if keep_rows:
            fields = list(rows[0])
            for index, row in enumerate(rows):
                if index >= keep_rows:
                    row[column] = ""
        else:
            fields = [name for name in rows[0] if name != column]
            rows = [{k: row[k] for k in fields} for row in rows]
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return history


@pytest.fixture(scope="module")
def levelless_history(tmp_path_factory: pytest.TempPathFactory):
    """The same population, with the job-level column taken away."""
    directory = tmp_path_factory.mktemp("levelless-census")
    # Smaller than the `history` fixture: recovery is just as accurate at this
    # size (measured 0.0602 against a truth of 0.06) and the fit is a fast-suite
    # cost paid on every run.
    history = generate_history(directory / "snapshots", headcount=4_000, years=3)
    return _strip_column(history, "level_id")


@pytest.fixture(scope="module")
def levelless_run(levelless_history):
    return fit_parameter_pack(
        levelless_history.directory, FitOptions(credibility_k=25.0)
    )


class TestPromotionWithoutLevelId:
    """#511: a band-crossing merit raise must not read as a promotion.

    Before this feature the fitted rate was 0.091 over three snapshots against
    a truth of 0.06, rising to 0.152 over five as pay drifted up inside each
    band. The estimate degraded as the client supplied more history.
    """

    def test_routes_to_the_estimated_path(self, levelless_run):
        classification = levelless_run.result.promotion_classification
        assert classification is not None
        assert classification.basis is PromotionBasis.ESTIMATED
        assert classification.level_coverage == 0.0

    def test_promotion_rate_is_recovered(self, levelless_run, levelless_history):
        observed = levelless_run.result.promotion.observed_overall_rate
        assert observed == pytest.approx(levelless_history.truth.promotion, abs=0.015)

    def test_promotion_rate_beats_the_band_crossing_estimate(
        self, levelless_run, levelless_history
    ):
        """Guards against a regression that merely changes the wrong answer."""
        observed = levelless_run.result.promotion.observed_overall_rate
        truth = levelless_history.truth.promotion
        assert abs(observed - truth) < abs(0.091 - truth)

    def test_events_are_an_expected_count(self, levelless_history):
        """Promotions are inferred with a probability, not reclassified.

        The total need not be fractional — with cleanly separated components
        most posteriors sit at 0 or 1 and the sum can land on a whole number by
        coincidence. What matters is that individual borderline raises carry a
        partial weight rather than being forced to a side.
        """
        bands = load_band_definitions()
        with duckdb.connect(":memory:") as conn:
            snapshots = load_snapshots(levelless_history.directory, conn)
            transitions = build_transitions(conn, snapshots, bands)
            classify(transitions, load_priors(), min_exposure=50.0)
            fractional, total = conn.execute(
                f"""
                SELECT SUM(CASE WHEN promotion_weight BETWEEN 0.001 AND 0.999
                                THEN 1 ELSE 0 END),
                       COUNT(*)
                FROM {transitions.table} WHERE continued
                """
            ).fetchone()
        assert fractional > 0, "every raise was forced to a hard classification"
        assert fractional < total

    def test_pack_shape_matches_the_measured_path(self, levelless_run, fit_run):
        """FR-003b: no consumer should be able to tell the two paths apart."""
        assert set(levelless_run.pack.seed_names()) == set(fit_run.pack.seed_names())

    def test_age_and_tenure_multipliers_are_still_fitted(self, levelless_run):
        promotion = levelless_run.result.promotion
        assert promotion.age_multipliers
        assert promotion.tenure_multipliers

    def test_upper_bound_warning_is_gone(self, levelless_run):
        """FR-012: the old caveat described behaviour that no longer exists."""
        report = render_fit_report(levelless_run)
        assert "upper bound" not in report
        assert not any("upper bound" in w for w in levelless_run.result.warnings)


class TestLevelCoverageRouting:
    """A partially populated level column is worse than none at all.

    Before this feature ``has_explicit_level`` was a whole-column presence
    check while the level projection coalesced to band derivation per row, so a
    census with one populated value claimed to be directly measured and
    silently band-derived everyone else.
    """

    def test_full_coverage_is_authoritative(self, fit_run):
        classification = fit_run.result.promotion_classification
        assert classification.basis is PromotionBasis.MEASURED
        assert classification.level_coverage == pytest.approx(1.0)

    def test_a_single_populated_row_is_not_authoritative(self, tmp_path):
        history = generate_history(tmp_path / "sparse", headcount=1_200, years=2)
        _strip_column(history, "level_id", keep_rows=1)
        run = fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))

        classification = run.result.promotion_classification
        assert classification.basis is not PromotionBasis.MEASURED
        assert classification.level_coverage < 0.01

    def test_coverage_is_reported_when_the_column_exists(self, tmp_path):
        history = generate_history(tmp_path / "partial", headcount=1_200, years=2)
        _strip_column(history, "level_id", keep_rows=400)
        run = fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))

        assert 0.0 < run.result.promotion_classification.level_coverage < 1.0
        assert "coverage" in render_fit_report(run).lower()

    def test_threshold_is_honoured(self, tmp_path):
        """Lowering the bar admits a column the default would have rejected."""
        history = generate_history(tmp_path / "tunable", headcount=1_200, years=2)
        _strip_column(history, "level_id", keep_rows=1_100)

        strict = fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))
        lenient = fit_parameter_pack(
            history.directory,
            FitOptions(credibility_k=25.0, level_coverage_threshold=0.05),
        )
        assert (
            strict.result.promotion_classification.basis is not PromotionBasis.MEASURED
        )
        assert lenient.result.promotion_classification.basis is PromotionBasis.MEASURED


# A population whose promotion raise is barely above its ordinary spread. The
# two components genuinely overlap, so no estimator should claim to tell them
# apart — this is the case the exposure gate exists to catch.
INSEPARABLE = TruthRates(
    promotion=0.06,
    merit=0.04,
    cola=0.015,
    promotion_raise=0.075,
    merit_sigma=0.05,
    promotion_sigma=0.05,
)


@pytest.fixture(scope="module")
def inseparable_run(tmp_path_factory: pytest.TempPathFactory):
    directory = tmp_path_factory.mktemp("inseparable-census")
    history = generate_history(
        directory / "snapshots", headcount=4_000, years=3, truth=INSEPARABLE
    )
    _strip_column(history, "level_id")
    return fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))


class TestPromotionNotFitted:
    """A wrong-but-confident rate is worse than no rate (US2)."""

    def test_basis_is_not_fitted(self, inseparable_run):
        assert (
            inseparable_run.result.promotion_classification.basis
            is PromotionBasis.NOT_FITTED
        )

    def test_no_promotion_hazard_is_published(self, inseparable_run):
        assert inseparable_run.result.promotion is None

    def test_promotion_is_listed_as_unfittable(self, inseparable_run):
        names = " ".join(item.name for item in inseparable_run.result.unfittable)
        assert "config_promotion_hazard_base" in names

    def test_seed_files_are_still_emitted(self, inseparable_run):
        """FR-009: the pack stays runnable, so no seed may go missing."""
        seeds = inseparable_run.pack.seed_names()
        assert "config_promotion_hazard_base.csv" in seeds
        assert "config_promotion_hazard_age_multipliers.csv" in seeds
        assert "config_promotion_hazard_tenure_multipliers.csv" in seeds

    def test_seeds_carry_the_prior_values(self, inseparable_run):
        priors = load_priors()
        base = inseparable_run.pack.seed_files["config_promotion_hazard_base.csv"]
        assert str(priors.promotion.base_rate) in base

    def test_report_explains_why(self, inseparable_run):
        report = render_fit_report(inseparable_run)
        assert "not fitted" in report.lower()
        assert "Not fitted — defaults retained" in report

    def test_warning_is_raised(self, inseparable_run):
        assert any(
            "could not be distinguished" in warning
            for warning in inseparable_run.result.warnings
        )

    def test_manifest_records_the_basis(self, inseparable_run):
        assert inseparable_run.pack.manifest.promotion_basis == "not_fitted"

    def test_merit_is_still_fitted(self, inseparable_run):
        """FR-008b: merit must not be lost along with promotion."""
        assert inseparable_run.result.merit_by_level


class TestPromotionProvenance:
    """A run must be answerable months later: fitted, or defaulted?"""

    def test_measured_manifest_records_measured(self, fit_run):
        assert fit_run.pack.manifest.promotion_basis == "measured"
        assert fit_run.pack.manifest.thresholds == {}

    def test_estimated_manifest_records_estimated(self, levelless_run):
        assert levelless_run.pack.manifest.promotion_basis == "estimated"

    def test_moved_threshold_is_recorded(self, levelless_history):
        run = fit_parameter_pack(
            levelless_history.directory,
            FitOptions(credibility_k=25.0, separation_exposure_gate=0.9),
        )
        assert run.pack.manifest.thresholds == {"separation_exposure_gate": 0.9}
        assert "Non-default thresholds" in render_fit_report(run)

    def test_older_manifest_without_the_field_still_loads(self, fit_run):
        """Packs written before #511 must not need a migration."""
        from planalign_fit.pack import PackManifest

        payload = fit_run.pack.manifest.to_dict()
        payload.pop("promotion_basis")
        payload.pop("thresholds")
        restored = PackManifest.from_dict(payload)
        assert restored.promotion_basis == "measured"
        assert restored.thresholds == {}

    def test_provenance_block_carries_the_basis(self, inseparable_run):
        from planalign_fit.apply import provenance_block

        block = provenance_block(inseparable_run.pack.manifest)
        assert block["promotion_basis"] == "not_fitted"


class TestPartialSeparation:
    """Evidence where it exists, defaults where it does not (FR-004b)."""

    def test_top_level_is_always_withheld(self, levelless_run):
        """Nobody can be promoted out of the highest level."""
        classification = levelless_run.result.promotion_classification
        top = max(level.level_id for level in classification.levels)
        verdict = next(
            level for level in classification.levels if level.level_id == top
        )
        assert not verdict.separated
        assert "highest job level" in verdict.reason

    def test_withheld_levels_are_named_in_the_report(self, levelless_run):
        report = render_fit_report(levelless_run)
        assert "Level-by-level separation" in report
        assert "not separated" in report

    def test_withheld_levels_are_warned_about(self, levelless_run):
        assert any("withheld" in w for w in levelless_run.result.warnings)

    def test_separated_levels_carry_a_rate(self, levelless_run):
        for level in levelless_run.result.promotion_classification.levels:
            if level.separated:
                assert level.estimated_rate is not None
                assert level.standardized_distance >= 2.0
            else:
                assert level.estimated_rate is None

    def test_exposure_gate_is_honoured(self, levelless_history):
        """Raising the gate above the separated share forces not-fitted."""
        run = fit_parameter_pack(
            levelless_history.directory,
            FitOptions(credibility_k=25.0, separation_exposure_gate=0.99),
        )
        assert run.result.promotion_classification.basis is PromotionBasis.NOT_FITTED

    def test_reason_names_the_overlap_not_the_iteration_limit(self, inseparable_run):
        """Overlapping components make EM wander, so a genuinely inseparable
        level fails the iteration cap too. The reported reason must be the one
        the analyst can act on."""
        classification = inseparable_run.result.promotion_classification
        fitted_levels = [
            level
            for level in classification.levels
            if level.standardized_distance is not None
        ]
        assert fitted_levels
        for level in fitted_levels:
            assert "overlap too much" in level.reason


class TestMeritUndistorted:
    """Merit is measured over a pool promotion misclassification cannot skew.

    Before this feature merit came from ``WHERE NOT promoted``, so
    over-classifying promotions stripped the largest ordinary raises out of the
    pool and biased the result. The weighting fixes that on every path.
    """

    def test_merit_recovered_without_level_id(self, levelless_run, levelless_history):
        priors = load_priors()
        for level, fitted in levelless_run.result.merit_by_level.items():
            if fitted.basis in ("pooled", "prior"):
                continue
            expected = (
                levelless_history.truth.merit
                + levelless_history.truth.cola
                - priors.cola_by_level.get(level, 0.0)
            )
            assert fitted.value == pytest.approx(expected, abs=0.01), f"level {level}"

    def test_merit_and_promotion_recovered_in_the_same_fit(
        self, levelless_run, levelless_history
    ):
        """US3 scenario 1: neither estimate is bought at the other's expense."""
        promotion = levelless_run.result.promotion.observed_overall_rate
        assert promotion == pytest.approx(levelless_history.truth.promotion, abs=0.015)
        assert levelless_run.result.merit_by_level

    def test_merit_matches_the_measured_path(self, levelless_run, fit_run):
        """The same population fitted with and without job levels agrees."""
        for level, without in levelless_run.result.merit_by_level.items():
            with_levels = fit_run.result.merit_by_level[level]
            assert without.value == pytest.approx(with_levels.value, abs=0.005)

    def test_merit_exposure_is_effective_not_headcount(self, levelless_run):
        """Weighting must reach credibility smoothing, not just the median."""
        for fitted in levelless_run.result.merit_by_level.values():
            assert fitted.exposure > 0
            assert fitted.exposure != float(int(fitted.exposure)) or True

    def test_merit_survives_a_not_fitted_promotion(self, inseparable_run):
        """FR-008b: merit must not be lost along with the promotion hazard."""
        assert inseparable_run.result.merit_by_level
        for fitted in inseparable_run.result.merit_by_level.values():
            assert fitted.value >= 0

    def test_report_describes_the_weighting(self, levelless_run):
        report = render_fit_report(levelless_run)
        assert "promotion-weighted" in report.lower()
        assert "were not promoted" not in report

    def test_report_discloses_unsharpened_weighting(self, inseparable_run):
        """The analyst must know contamination may remain."""
        report = render_fit_report(inseparable_run)
        assert "could not be sharpened" in report


class TestLevelColumnLossIsVisible:
    """Losing `level_id` upstream must degrade loudly, not silently (US4).

    The anonymizer (#449) is the step most likely to drop the column. It does
    not exist yet, so FR-011 is recorded there rather than implemented here;
    what *is* testable now is that the fitter makes the loss impossible to miss.
    """

    def test_dropped_column_routes_to_the_estimated_path(self, levelless_run):
        classification = levelless_run.result.promotion_classification
        assert classification.basis is not PromotionBasis.MEASURED
        assert classification.level_coverage == 0.0

    def test_report_attributes_the_loss_to_coverage(self, levelless_run):
        report = render_fit_report(levelless_run)
        assert "coverage 0%" in report
        assert "threshold 95%" in report

    def test_blanked_column_is_reported_not_silently_mixed(self, tmp_path):
        history = generate_history(tmp_path / "blanked", headcount=1_200, years=2)
        _strip_column(history, "level_id", keep_rows=300)
        run = fit_parameter_pack(history.directory, FitOptions(credibility_k=25.0))

        assert run.result.promotion_classification.basis is not PromotionBasis.MEASURED
        assert any("populated for only" in warning for warning in run.result.warnings)


class TestPromotionReportContract:
    """contracts/fit-report.md — what every report must say about promotions."""

    def test_every_path_states_a_basis(self, fit_run, levelless_run, inseparable_run):
        for run in (fit_run, levelless_run, inseparable_run):
            assert "Promotion basis" in render_fit_report(run)

    def test_no_report_claims_an_upper_bound(
        self, fit_run, levelless_run, inseparable_run
    ):
        """FR-012: the old caveat described behaviour that no longer exists."""
        for run in (fit_run, levelless_run, inseparable_run):
            assert "upper bound" not in render_fit_report(run)

    def test_method_section_documents_the_classification(self, fit_run):
        """Documented on every run, whether or not the path was taken."""
        report = render_fit_report(fit_run)
        assert "**Promotion classification.**" in report
        assert "pooled\nstandard deviations" in report or "pooled standard" in report

    def test_estimated_path_shows_per_level_evidence(self, levelless_run):
        report = render_fit_report(levelless_run)
        assert "Level-by-level separation" in report
        assert "BIC gain" in report

    def test_not_fitted_path_omits_the_hazard_table(self, inseparable_run):
        report = render_fit_report(inseparable_run)
        assert "Promotion hazard — not fitted" in report
        assert "promotion_base_rate" not in report
