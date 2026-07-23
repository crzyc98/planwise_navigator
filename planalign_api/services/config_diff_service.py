"""Read-only effective configuration diff and provenance service."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Optional

import duckdb
import yaml
from pydantic import ValidationError

from _version import __version__
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.run_metadata import (
    RUN_METADATA_TABLE,
    DriftStatus,
    compute_config_fingerprint,
    evaluate_drift,
)

from ..models.comparison import ConfigDelta, ConfigDiffResponse, ScenarioProvenance
from ..models.workspace import Workspace
from ..storage.workspace_storage import WorkspaceStorage
from .database_path_resolver import (
    DatabasePathResolver,
    create_api_database_path_resolver,
)

logger = logging.getLogger(__name__)

_MISSING = object()
_COSMETIC_PATHS = {
    "name",
    "description",
    "scenario_id",
    "plan_design_id",
    "created_at",
    "updated_at",
    "run_timestamp",
    "timestamp",
}


class ConfigDiffService:
    """Compare two effective configs and read their run provenance."""

    def __init__(
        self,
        storage: WorkspaceStorage,
        db_resolver: Optional[DatabasePathResolver] = None,
    ) -> None:
        self.storage = storage
        self.db_resolver = db_resolver or create_api_database_path_resolver(storage)

    def compare(
        self,
        workspace_id: str,
        scenario_a: str,
        scenario_b: str,
        scenario_names: dict[str, str],
        *,
        workspace: Optional[Workspace] = None,
    ) -> ConfigDiffResponse:
        """Return effective config differences and read-only provenance.

        ``workspace``, if the caller already fetched it (e.g. for its own
        existence check), lets both scenarios' configs be merged without
        re-reading workspace.json/base_config.yaml from disk per scenario.
        """
        config_a = self._get_config(workspace_id, scenario_a, workspace)
        config_b = self._get_config(workspace_id, scenario_b, workspace)
        differences, unchanged_count = _diff_configs(config_a, config_b)
        provenance = {
            scenario_a: self._read_provenance(workspace_id, scenario_a, config_a),
            scenario_b: self._read_provenance(workspace_id, scenario_b, config_b),
        }
        seeds_match = _seeds_match(provenance[scenario_a], provenance[scenario_b])
        return ConfigDiffResponse(
            scenario_a=scenario_a,
            scenario_b=scenario_b,
            scenario_names=scenario_names,
            differences=differences,
            unchanged_count=unchanged_count,
            provenance=provenance,
            seeds_match=seeds_match,
            drift_warning=any(item.drift_warning for item in provenance.values()),
        )

    def _get_config(
        self,
        workspace_id: str,
        scenario_id: str,
        workspace: Optional[Workspace] = None,
    ) -> dict[str, Any]:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if resolved.config_path is not None:
            try:
                archived = yaml.safe_load(
                    resolved.config_path.read_text(encoding="utf-8")
                )
            except (OSError, yaml.YAMLError) as exc:
                raise ValueError(
                    f"Unable to read selected-run config for {scenario_id}"
                ) from exc
            if isinstance(archived, dict):
                return archived
        config = (
            self.storage.get_merged_config_for(workspace, scenario_id)
            if workspace is not None
            else self.storage.get_merged_config(workspace_id, scenario_id)
        )
        if config is None:
            raise ValueError(f"Unable to resolve effective config for {scenario_id}")
        return config

    def _read_provenance(
        self,
        workspace_id: str,
        scenario_id: str,
        effective_config: dict[str, Any],
    ) -> ScenarioProvenance:
        resolved = self.db_resolver.resolve(workspace_id, scenario_id)
        if not resolved.exists or resolved.source not in {"scenario", "run"}:
            return ScenarioProvenance(available=False)
        try:
            with duckdb.connect(str(resolved.path), read_only=True) as connection:
                rows = connection.execute(
                    "SELECT run_timestamp, run_type, config_fingerprint, "
                    "random_seed, full_reset, planalign_version "
                    f"FROM {RUN_METADATA_TABLE} "
                    "ORDER BY run_timestamp DESC LIMIT 2"
                ).fetchall()
        except duckdb.Error as exc:
            logger.info("Run provenance unavailable for %s: %s", scenario_id, exc)
            return ScenarioProvenance(available=False)
        return _build_provenance(rows, effective_config)


def _diff_configs(
    config_a: Mapping[str, Any], config_b: Mapping[str, Any]
) -> tuple[list[ConfigDelta], int]:
    differences: list[ConfigDelta] = []
    unchanged_count = _walk_diff(config_a, config_b, "", differences)
    return sorted(differences, key=lambda item: item.path), unchanged_count


def _walk_diff(
    value_a: Any,
    value_b: Any,
    path: str,
    differences: list[ConfigDelta],
) -> int:
    if isinstance(value_a, Mapping) and isinstance(value_b, Mapping):
        unchanged = 0
        for key in sorted(set(value_a) | set(value_b)):
            child_path = f"{path}.{key}" if path else str(key)
            if _is_cosmetic(child_path):
                continue
            unchanged += _walk_diff(
                value_a.get(key, _MISSING),
                value_b.get(key, _MISSING),
                child_path,
                differences,
            )
        return unchanged
    if value_a is not _MISSING and value_b is not _MISSING and value_a == value_b:
        return 1
    differences.append(_make_delta(path, value_a, value_b))
    return 0


def _make_delta(path: str, value_a: Any, value_b: Any) -> ConfigDelta:
    if value_a is _MISSING:
        return ConfigDelta(path=path, a=None, b=value_b, status="only_b")
    if value_b is _MISSING:
        return ConfigDelta(path=path, a=value_a, b=None, status="only_a")
    return ConfigDelta(path=path, a=value_a, b=value_b, status="changed")


def _is_cosmetic(path: str) -> bool:
    return path in _COSMETIC_PATHS or path.rsplit(".", 1)[-1] in {
        "created_at",
        "updated_at",
        "timestamp",
    }


def _build_provenance(
    rows: list[tuple[Any, ...]], effective_config: dict[str, Any]
) -> ScenarioProvenance:
    if not rows:
        return ScenarioProvenance(available=False)
    timestamp, run_type, fingerprint, seed, full_reset, version = rows[0]
    reasons = _current_drift_reasons(effective_config, fingerprint, seed, version)
    if len(rows) > 1 and _is_mixed_generation(rows[0], rows[1]):
        reasons.append("mixed_generation")
    return ScenarioProvenance(
        available=True,
        config_fingerprint=str(fingerprint)[:12],
        random_seed=seed,
        run_timestamp=_coerce_datetime(timestamp),
        drift_warning=bool(reasons),
        drift_reasons=reasons,
    )


def _current_drift_reasons(
    effective_config: dict[str, Any],
    fingerprint: str,
    seed: Optional[int],
    stored_version: Optional[str],
) -> list[str]:
    simulation = effective_config.get("simulation")
    current_seed = (
        simulation.get("random_seed") if isinstance(simulation, dict) else None
    )
    try:
        current_fingerprint = compute_config_fingerprint(
            SimulationConfig.model_validate(effective_config)
        )
    except (ValidationError, ValueError, TypeError):
        current_fingerprint = None

    drift = evaluate_drift(
        fingerprint, seed, current_fingerprint or fingerprint, current_seed
    )
    reasons: list[str] = []
    if current_seed is not None and drift.seed_changed:
        reasons.append("current_seed_mismatch")
    # get_merged_config injects backward-compat defaults (e.g. employer_match,
    # employer_core_contribution) that didn't exist when older scenarios were
    # run, which would otherwise always fingerprint as "changed" even with no
    # user-visible edit. Only trust a fingerprint mismatch when the stored run
    # and the current app are on the same schema version.
    if (
        current_fingerprint is not None
        and stored_version == __version__
        and drift.config_changed
    ):
        reasons.append("current_config_mismatch")
    return reasons


def _is_mixed_generation(latest: tuple[Any, ...], prior: tuple[Any, ...]) -> bool:
    _, run_type, fingerprint, seed, full_reset, _version = latest
    _, _, prior_fingerprint, prior_seed, _, _prior_version = prior
    if full_reset or run_type == "calibration":
        return False
    drift = evaluate_drift(prior_fingerprint, prior_seed, fingerprint, seed)
    return drift.status is DriftStatus.DRIFT


def _seeds_match(a: ScenarioProvenance, b: ScenarioProvenance) -> Optional[bool]:
    if not a.available or not b.available:
        return None
    if a.random_seed is None or b.random_seed is None:
        return None
    return a.random_seed == b.random_seed


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
