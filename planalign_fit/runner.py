"""Orchestrate one ``planalign fit`` run end to end.

Load and hash the snapshots, link the cohorts, run every estimator the data can
support, record the rest as explicitly unfittable, and assemble the parameter
pack. Nothing here writes to disk — :func:`planalign_fit.pack.write_pack` does
that, so a fit can be inspected before it is materialized.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import duckdb

from planalign_fit import behavior, compensation, hazards
from planalign_fit.bands import BandDefinitions, load_band_definitions
from planalign_fit.models import FitResult, Unfittable
from planalign_fit.pack import ParameterPack, build_pack
from planalign_fit.priors import Priors, load_priors
from planalign_fit.smoothing import DEFAULT_CREDIBILITY_K, DEFAULT_MIN_EXPOSURE
from planalign_fit.snapshots import SnapshotSet, load_snapshots
from planalign_fit.transitions import TransitionSet, build_transitions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FitOptions:
    """Knobs a caller can turn without changing what the estimators mean."""

    credibility_k: float = DEFAULT_CREDIBILITY_K
    min_exposure: float = DEFAULT_MIN_EXPOSURE
    seeds_dir: Optional[Path] = None
    config_path: Optional[Path] = None
    pack_id: Optional[str] = None
    notes: str = ""


@dataclass
class FitRun:
    """A completed fit: the pack plus the context it was produced from."""

    pack: ParameterPack
    result: FitResult
    snapshot_set: SnapshotSet
    priors: Priors
    bands: BandDefinitions
    options: FitOptions
    diagnostics: dict[str, object] = field(default_factory=dict)


def fit_parameter_pack(
    snapshots_dir: Path | str,
    options: Optional[FitOptions] = None,
) -> FitRun:
    """Fit every supported parameter from ``snapshots_dir`` and build a pack."""
    options = options or FitOptions()
    bands = load_band_definitions(options.seeds_dir)
    priors = load_priors(options.seeds_dir, options.config_path)

    # An in-memory database: fitting reads census files and never touches any
    # simulation database, shared or isolated.
    with duckdb.connect(":memory:") as conn:
        snapshot_set = load_snapshots(snapshots_dir, conn)
        transitions = build_transitions(conn, snapshot_set, bands)
        result = _run_estimators(transitions, priors, options)

    pack = build_pack(
        result=result,
        snapshot_set=snapshot_set,
        priors=priors,
        bands=bands,
        credibility_k=options.credibility_k,
        min_exposure=options.min_exposure,
        pack_id=options.pack_id,
        notes=options.notes,
    )
    return FitRun(
        pack=pack,
        result=result,
        snapshot_set=snapshot_set,
        priors=priors,
        bands=bands,
        options=options,
        diagnostics=result.diagnostics,
    )


def _run_estimators(
    transitions: TransitionSet, priors: Priors, options: FitOptions
) -> FitResult:
    result = FitResult()
    result.diagnostics["linked_pairs"] = transitions.linked_pairs
    smoothing = {
        "credibility_k": options.credibility_k,
        "min_exposure": options.min_exposure,
    }

    result.termination, result.termination_cells = hazards.fit_termination_hazard(
        transitions, priors.termination, **smoothing
    )
    result.promotion, result.promotion_cells = hazards.fit_promotion_hazard(
        transitions, priors.promotion, **smoothing
    )
    result.merit_by_level = compensation.fit_merit_by_level(
        transitions, priors, **smoothing
    )

    _fit_scalars(result, transitions, priors, options)
    _fit_enrollment(result, transitions, priors, options)
    _fit_deferral(result, transitions, priors, options)
    _record_structural_exclusions(result, priors)
    _record_data_warnings(result, transitions)
    return result


def _fit_scalars(
    result: FitResult,
    transitions: TransitionSet,
    priors: Priors,
    options: FitOptions,
) -> None:
    result.config_overrides[
        "workforce.total_termination_rate"
    ] = hazards.fit_scalar_rate(
        transitions.conn,
        "workforce.total_termination_rate",
        transitions.table,
        "terminated",
        float(priors.config_value("workforce.total_termination_rate", 0.12)),
        credibility_k=options.credibility_k,
        min_exposure=options.min_exposure,
    )

    if transitions.observability.has_termination_rows:
        result.config_overrides[
            "workforce.new_hire_termination_rate"
        ] = hazards.fit_scalar_rate(
            transitions.conn,
            "workforce.new_hire_termination_rate",
            transitions.new_hires_table,
            "terminated",
            float(priors.config_value("workforce.new_hire_termination_rate", 0.25)),
            credibility_k=options.credibility_k,
            min_exposure=options.min_exposure,
        )
    else:
        result.unfittable.append(
            Unfittable(
                name="workforce.new_hire_termination_rate",
                reason=transitions.observability.reasons()["new_hire_termination"],
                default_used=priors.config_value(
                    "workforce.new_hire_termination_rate", 0.25
                ),
            )
        )

    growth = compensation.fit_headcount_growth(
        transitions,
        float(priors.config_value("simulation.target_growth_rate", 0.03)),
        min_exposure=options.min_exposure,
    )
    if growth is not None:
        result.config_overrides["simulation.target_growth_rate"] = growth


def _fit_enrollment(
    result: FitResult,
    transitions: TransitionSet,
    priors: Priors,
    options: FitOptions,
) -> None:
    smoothing = {
        "credibility_k": options.credibility_k,
        "min_exposure": options.min_exposure,
    }
    if not transitions.observability.has_enrollment:
        reason = transitions.observability.reasons()["enrollment"]
        for name in (
            f"{behavior.VOLUNTARY_PREFIX}.*",
            behavior.OPT_OUT_TARGET_KEY,
        ):
            result.unfittable.append(
                Unfittable(name=name, reason=reason, default_used="base config value")
            )
        return

    posture = behavior.auto_enrollment_posture(priors)
    result.diagnostics["auto_enrollment_enabled"] = posture.enabled
    result.diagnostics["auto_enrollment_scope"] = posture.scope

    voluntary = behavior.fit_voluntary_enrollment(
        transitions, priors, posture, **smoothing
    )
    if voluntary is None:
        result.unfittable.append(
            Unfittable(
                name=f"{behavior.VOLUNTARY_PREFIX}.*",
                reason=(
                    f"auto-enrollment covers every eligible employee (scope "
                    f"'{posture.scope}'), so nobody in the observation window made "
                    "a voluntary enrollment decision"
                ),
                default_used="base config value",
            )
        )
    else:
        for value in voluntary.values():
            result.config_overrides[value.name] = value
        result.diagnostics["voluntary_exposure"] = voluntary.total_exposure
        result.diagnostics["voluntary_events"] = voluntary.total_events

    opt_out = behavior.fit_opt_out_target(transitions, priors, posture, **smoothing)
    if opt_out is None:
        result.unfittable.append(
            Unfittable(
                name=behavior.OPT_OUT_TARGET_KEY,
                reason=(
                    "auto-enrollment is disabled in the base config, so no "
                    "employee in the observation window was auto-enrolled and "
                    "there is nothing to opt out of"
                ),
                default_used=priors.config_value(behavior.OPT_OUT_TARGET_KEY, 0.09),
            )
        )
    else:
        result.config_overrides[opt_out.name] = opt_out
        result.warnings.append(
            "Auto-enrollment is enabled in the base config, so first-year "
            "non-participation was fitted as the opt-out rate. This is a proxy: "
            "the census records participation, not who was auto-enrolled and then "
            "opted out. Confirm auto-enrollment actually covered every new hire in "
            "the observation window before trusting this rate."
        )

    result.unfittable.append(behavior.job_level_multipliers_unfittable())


def _fit_deferral(
    result: FitResult,
    transitions: TransitionSet,
    priors: Priors,
    options: FitOptions,
) -> None:
    smoothing = {
        "credibility_k": options.credibility_k,
        "min_exposure": options.min_exposure,
    }
    if not transitions.observability.has_deferral_rate:
        reason = transitions.observability.reasons()["deferral"]
        result.unfittable.append(
            Unfittable(
                name="default_deferral_rates.*",
                reason=reason,
                default_used="seeded default_deferral_rates.csv",
            )
        )
        result.unfittable.append(
            Unfittable(
                name="deferral_auto_escalation.increment_amount",
                reason=reason,
                default_used=priors.config_value(
                    "deferral_auto_escalation.increment_amount", 0.01
                ),
            )
        )
    else:
        result.deferral_rates = behavior.fit_default_deferral_rates(
            transitions, priors, **smoothing
        )
        escalation = behavior.fit_escalation(transitions, priors, **smoothing)
        if escalation is None:
            result.unfittable.append(
                Unfittable(
                    name="deferral_auto_escalation.increment_amount",
                    reason=(
                        "no employee was enrolled with a known deferral rate in "
                        "two consecutive snapshots, so no escalation is observable"
                    ),
                    default_used=priors.config_value(
                        "deferral_auto_escalation.increment_amount", 0.01
                    ),
                )
            )
        else:
            result.config_overrides[
                escalation.increment_amount.name
            ] = escalation.increment_amount
            result.diagnostics["escalation_adoption_rate"] = escalation.adoption_rate
            result.diagnostics["escalation_exposure"] = escalation.exposure

    result.unfittable.append(behavior.match_response_unfittable(priors))


def _record_structural_exclusions(result: FitResult, priors: Priors) -> None:
    """Constants the fit holds fixed, so the report can say so out loud."""
    result.unfittable.append(
        Unfittable(
            name="config_termination_hazard_base.level_discount_factor / "
            "min_level_discount_multiplier",
            reason=(
                "level is assigned from compensation banding, so a level effect "
                "cannot be separated from the banding itself; these constants are "
                "held fixed and act as the offset the hazard is fitted against"
            ),
            default_used=priors.termination.level_constants,
        )
    )
    result.unfittable.append(
        Unfittable(
            name="config_promotion_hazard_base.level_dampener_factor",
            reason="held fixed for the same reason as the termination level discount",
            default_used=priors.promotion.level_constants,
        )
    )
    result.unfittable.append(
        Unfittable(
            name="compensation.cola_rate",
            reason=(
                "COLA is a policy input the plan sponsor sets, not a behaviour to "
                "recover. It is held at the configured value and merit absorbs the "
                "remainder of observed compensation growth"
            ),
            default_used=priors.config_value("compensation.cola_rate", 0.0),
        )
    )


def _record_data_warnings(result: FitResult, transitions: TransitionSet) -> None:
    if not transitions.observability.has_explicit_level:
        result.warnings.append(
            "No 'level_id' column in the snapshots, so job level was inferred from "
            "compensation banding — the same rule the simulator's baseline uses. A "
            "promotion is then any move across a compensation band, which an "
            "ordinary merit raise can trigger on its own, so the fitted promotion "
            "hazard is an upper bound. Supply level_id in the census to measure "
            "promotions directly."
        )
    if transitions.unmatched_reappearances:
        result.warnings.append(
            f"{transitions.unmatched_reappearances:,} employee(s) appear in a later "
            "snapshot with a hire date predating that year — rehires or reused IDs. "
            "They are in neither the experienced exposure nor the new-hire cohort, "
            "so they contribute to no fitted rate."
        )
    vanished_row = transitions.conn.execute(
        f"SELECT COUNT(*) FROM {transitions.table} WHERE vanished"
    ).fetchone()
    vanished = int(vanished_row[0]) if vanished_row is not None else 0
    if vanished:
        share = vanished / transitions.linked_pairs if transitions.linked_pairs else 0.0
        result.warnings.append(
            f"{vanished:,} employee(s) ({share:.1%} of exposure) disappear from the "
            "next snapshot with no termination row. They are counted as "
            "terminations; if the census instead drops leavers silently, this is "
            "the expected reading, and if it does not, the termination fit is "
            "inflated."
        )


def format_summary(run: FitRun) -> list[tuple[str, str]]:
    """Compact key/value summary for CLI output."""
    result = run.result
    fitted = result.all_fitted()
    thin = [v for v in fitted if v.basis in ("pooled", "prior")]
    return [
        ("Snapshot years", ", ".join(str(y) for y in run.snapshot_set.years)),
        ("Transitions linked", f"{run.result.diagnostics.get('linked_pairs', 0):,}"),
        ("Parameters fitted", str(len(fitted))),
        ("Thin / prior-backed", str(len(thin))),
        ("Not fittable", str(len(result.unfittable))),
        ("Pack fingerprint", run.pack.manifest.fingerprint[:12]),
    ]
