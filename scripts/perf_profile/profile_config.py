"""Typed schema for Feature 116 run-cost profile artifacts.

These models are the normative contract between the measurement scripts and
the report builder (specs/116-profile-run-cost/contracts/timing-data.md).
`build_report.py` must fail loudly on any mismatch — never coerce silently.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator
import yaml

ROOT = Path(__file__).resolve().parents[2]
SHARED_DEV_DB = ROOT / "dbt" / "simulation.duckdb"
OUTPUT_DIR = ROOT / "var" / "perf_profile"
SAMPLES_DIR = OUTPUT_DIR / "samples"
DB_DIR = OUTPUT_DIR / "db"
REPORT_PATH = ROOT / "docs" / "perf" / "run_cost_profile.md"
TINY_CENSUS_CSV = ROOT / "tests" / "fixtures" / "invariant_census.csv"
DEV_CENSUS_PARQUET = ROOT / "data" / "census_preprocessed.parquet"
LARGE_CENSUS_PARQUET = OUTPUT_DIR / "census_large.parquet"

DECOMPOSITION_TOLERANCE = 0.10  # FR-003: components must cover total within 10%
MIN_WARM_REPS = {
    "tiny": 3,
    "dev": 3,
    "large": 2,
    "custom": 3,
}  # spec FR-002 + large edge case; 'custom' = arbitrary census/config (#455 rework)

# Which orchestrator-construction seam a sample was measured through.
#   wrapper — planalign_cli.integration.OrchestratorWrapper, the real product
#             path used by `planalign simulate` and (via subprocess) Studio.
#   factory — planalign_orchestrator.create_orchestrator, the historical
#             Feature 116 path (kept only for reconciliation; #455 rework).
Construction = Literal["wrapper", "factory"]


def canonical_payload_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fingerprint_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_yaml_fingerprint(path: Path) -> str:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return canonical_payload_fingerprint(payload)


def fingerprint_seed_tree(path: Path) -> str:
    entries = [
        {
            "path": item.relative_to(path).as_posix(),
            "sha256": fingerprint_file(item),
        }
        for item in sorted(path.rglob("*"))
        if item.is_file()
    ]
    return canonical_payload_fingerprint(entries)


class CensusSize(str, Enum):
    TINY = "tiny"
    DEV = "dev"
    LARGE = "large"
    CUSTOM = "custom"


class ModelTiming(BaseModel):
    unique_id: str
    execute_s: float = Field(ge=0)
    compile_s: float = Field(ge=0)
    status: str


class Invocation(BaseModel):
    seq: int = Field(ge=0)
    year: Optional[int] = None
    stage: Optional[str] = None
    command: str
    wall_s: float = Field(ge=0)
    models: List[ModelTiming] = Field(default_factory=list)

    @property
    def execute_s(self) -> float:
        return sum(m.execute_s for m in self.models)


class EnvNote(BaseModel):
    machine: str
    os: str
    python: str
    dbt_core: str
    dbt_duckdb: str
    duckdb: str
    git_sha: str
    shared_db_sha256_before: Optional[str] = None


class ProfileFingerprints(BaseModel):
    method: Literal["sha256-canonical-v1"] = "sha256-canonical-v1"
    code: str
    dirty_tree: Optional[str] = None
    normalized_config: str
    census: str
    seeds: str
    construction: Optional[str] = None
    database: Optional[str] = None
    invocation_schedule: Optional[str] = None
    per_node_execution: Optional[str] = None


class TimingSample(BaseModel):
    sample_id: str
    census_size: CensusSize
    census_rows: int = Field(gt=0)
    census_parquet: str
    horizon: Tuple[int, int]
    repetition: int = Field(ge=0)
    warm: bool
    db_path: str
    total_wall_s: float = Field(gt=0)
    invocations: List[Invocation] = Field(default_factory=list)
    env: EnvNote
    completed: bool = True
    error: Optional[str] = None
    # #455 rework: which construction seam + which config this sample measured.
    # Defaults keep historical Feature 116 (factory-path) samples valid.
    construction: Construction = "factory"
    config_label: str = "reference"
    config_path: Optional[str] = None
    cpu_s: Optional[float] = Field(default=None, ge=0)
    peak_rss_mb: Optional[float] = Field(default=None, ge=0)
    construction_signature: Optional[Dict[str, Any]] = None
    executed_schedule: List[Dict[str, Any]] = Field(default_factory=list)
    product_invocation_count: Optional[int] = Field(default=None, ge=0)
    fingerprints: Optional[ProfileFingerprints] = None

    @property
    def invocation_wall_s(self) -> float:
        return sum(i.wall_s for i in self.invocations)

    @property
    def computation_s(self) -> float:
        return sum(i.execute_s for i in self.invocations)

    @property
    def overhead_s(self) -> float:
        """Per-invocation cost not attributable to model execute time."""
        return self.invocation_wall_s - self.computation_s

    @property
    def residue_s(self) -> float:
        """Wall time outside dbt invocations (orchestrator Python, state mgmt)."""
        return self.total_wall_s - self.invocation_wall_s

    @property
    def overhead_share(self) -> float:
        """Overhead as a share of total wall time (the decision metric)."""
        return self.overhead_s / self.total_wall_s

    @model_validator(mode="after")
    def _check_decomposition(self) -> "TimingSample":
        if not self.completed:
            return self
        if self.residue_s < -1e-6:
            raise ValueError(
                f"{self.sample_id}: invocation wall ({self.invocation_wall_s:.1f}s) "
                f"exceeds total wall ({self.total_wall_s:.1f}s)"
            )
        covered = self.computation_s + self.overhead_s + max(self.residue_s, 0.0)
        if (
            abs(covered - self.total_wall_s)
            > DECOMPOSITION_TOLERANCE * self.total_wall_s
        ):
            raise ValueError(
                f"{self.sample_id}: decomposition covers {covered:.1f}s of "
                f"{self.total_wall_s:.1f}s (> {DECOMPOSITION_TOLERANCE:.0%} residue)"
            )
        return self


class FloorStats(BaseModel):
    """M3 fixed-cost cross-check: minimal-invocation floor (FR-004)."""

    selector: str
    reps: int = Field(ge=5)
    wall_s: List[float]
    execute_s: List[float]
    invocations_per_year: int = Field(gt=0)

    @property
    def floor_s(self) -> List[float]:
        return [w - e for w, e in zip(self.wall_s, self.execute_s)]

    @property
    def median_floor_s(self) -> float:
        vals = sorted(self.floor_s)
        return vals[len(vals) // 2]


class CampaignSummary(BaseModel):
    """Campaign-level record (campaign.json): SC-007 evidence + floor stats."""

    started_at: str
    finished_at: Optional[str] = None
    shared_db_sha256_before: Optional[str] = None
    shared_db_sha256_after: Optional[str] = None
    shared_db_unchanged: Optional[bool] = None
    sizes_run: List[str] = Field(default_factory=list)
    floor: Optional[FloorStats] = None
    # #455 rework: production-path campaign provenance.
    campaign_id: str = "legacy"
    constructions_run: List[str] = Field(default_factory=list)
    config_labels_run: List[str] = Field(default_factory=list)


class ProbeResult(BaseModel):
    stage: str
    year: int
    census_size: CensusSize
    standard_wall_s: float = Field(gt=0)
    direct_wall_s: float = Field(gt=0)
    equivalent: bool
    diffs: List[str] = Field(default_factory=list)
    nodes_executed: int = Field(gt=0)

    @property
    def speedup(self) -> float:
        return self.standard_wall_s / self.direct_wall_s

    @model_validator(mode="after")
    def _diffs_iff_inequivalent(self) -> "ProbeResult":
        if self.equivalent and self.diffs:
            raise ValueError("equivalent=true must not carry diffs")
        if not self.equivalent and not self.diffs:
            raise ValueError("equivalent=false requires named diffs")
        return self
