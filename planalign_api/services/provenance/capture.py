"""Execution-time capture of immutable, aggregate-only run provenance."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from _version import __version__

from planalign_api.models.provenance import (
    AnnualEventCount,
    AnnualWorkforceReconciliation,
    CapturedValidationResult,
    ConfigurationEvidence,
    EvidenceFinding,
    ExecutionTimingEvidence,
    InputFingerprint,
    RunIdentityEvidence,
    RunProvenanceManifest,
    SeedFingerprint,
    SoftwareEvidence,
    StageCompletion,
    utc_now,
)

MANIFEST_NAME = "provenance.json"
MAX_HASH_BYTES = 10 * 1024 * 1024 * 1024
_SECRET_PARTS = ("password", "secret", "token", "credential", "api_key")
_PII_PARTS = (
    "employee_id",
    "employee_ssn",
    "social_security",
    "email_address",
    "first_name",
    "last_name",
)
_PATH_KEYS = ("path", "directory", "dir", "file")


class CaptureError(RuntimeError):
    """Raised when execution evidence cannot be captured safely."""


def sha256_file(path: Path, *, max_bytes: int = MAX_HASH_BYTES) -> tuple[str, int]:
    """Hash one stable regular file without following symlinks."""
    if path.is_symlink() or not path.is_file():
        raise CaptureError("input is not a regular file")
    before = path.stat()
    if before.st_size > max_bytes:
        raise CaptureError("input exceeds provenance hashing limit")
    digest = hashlib.sha256()
    read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            read += len(chunk)
            if read > max_bytes:
                raise CaptureError("input changed or exceeds provenance hashing limit")
            digest.update(chunk)
    after = path.stat()
    stable = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    current = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if stable != current or read != before.st_size:
        raise CaptureError("input changed while provenance was captured")
    return digest.hexdigest(), read


def safe_effective_config(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a deterministic config projection with secrets and paths generalized."""
    redactions: list[str] = []

    def project(value: Any, path: str, key: str = "") -> Any:
        lowered = key.lower()
        if any(part in lowered for part in _SECRET_PARTS + _PII_PARTS):
            redactions.append(path)
            return "<redacted>"
        if any(part in lowered for part in _PATH_KEYS) and isinstance(value, str):
            redactions.append(path)
            return "<redacted-path>"
        if isinstance(value, dict):
            return {
                str(k): project(v, f"{path}.{k}" if path else str(k), str(k))
                for k, v in sorted(value.items())
            }
        if isinstance(value, list):
            return [project(v, f"{path}[{index}]") for index, v in enumerate(value)]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    return project(copy.deepcopy(config), ""), sorted(set(redactions))


def config_fingerprint(config: dict[str, Any]) -> str:
    """Use the simulation engine's result-affecting config fingerprint."""
    try:
        from planalign_orchestrator.config import SimulationConfig
        from planalign_orchestrator.run_metadata import compute_config_fingerprint

        return compute_config_fingerprint(SimulationConfig.model_validate(config))
    except (ValueError, TypeError, KeyError):
        pass
    payload = json.dumps(
        config, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture_source_state(project_root: Path) -> SoftwareEvidence:
    """Capture commit and clean/dirty state without recording filenames or diffs."""
    try:
        sha = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            .stdout.strip()
            .lower()
        )
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=project_root,
            check=True,
            capture_output=True,
            timeout=10,
        ).stdout
        if status:
            fingerprint = _dirty_tree_fingerprint(project_root, status)
            return SoftwareEvidence(
                planalign_version=__version__,
                git_commit_sha=sha,
                working_tree_state="dirty",
                working_tree_fingerprint=fingerprint,
            )
        return SoftwareEvidence(
            planalign_version=__version__,
            git_commit_sha=sha,
            working_tree_state="clean",
            working_tree_fingerprint=None,
        )
    except (OSError, subprocess.SubprocessError, ValueError, CaptureError):
        return SoftwareEvidence(planalign_version=__version__)


def _dirty_tree_fingerprint(project_root: Path, status: bytes) -> str:
    """Bind tracked diffs and untracked file bytes without retaining either."""
    digest = hashlib.sha256(status)
    diff = subprocess.run(
        ["git", "diff", "--binary", "--no-ext-diff", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        timeout=20,
    ).stdout
    digest.update(diff)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=project_root,
        check=True,
        capture_output=True,
        timeout=10,
    ).stdout.split(b"\0")
    total = len(status) + len(diff)
    for raw_name in sorted(name for name in untracked if name):
        relative = raw_name.decode("utf-8", errors="strict")
        path = project_root / relative
        file_hash, size = sha256_file(path)
        total += size
        if total > MAX_HASH_BYTES:
            raise CaptureError("working tree exceeds provenance hashing limit")
        digest.update(raw_name)
        digest.update(file_hash.encode("ascii"))
    return digest.hexdigest()


def fingerprint_input(
    path: Path, *, logical_name: str | None = None
) -> InputFingerprint:
    digest, size = sha256_file(path)
    return InputFingerprint(
        logical_name=logical_name or path.name,
        sha256=digest,
        size_bytes=size,
        record_count=_parquet_record_count(path),
        format=path.suffix.lstrip(".").lower() or None,
    )


def _parquet_record_count(path: Path) -> int | None:
    if path.suffix.lower() != ".parquet":
        return None
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]

        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception:
        return None


def fingerprint_seed_directory(seed_root: Path) -> list[SeedFingerprint]:
    root = seed_root.resolve(strict=True)
    fingerprints: list[SeedFingerprint] = []
    for path in sorted(seed_root.rglob("*")):
        if path.is_symlink():
            raise CaptureError("seed directory contains a symlink")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        if root not in resolved.parents:
            raise CaptureError("seed input escapes the effective seed directory")
        digest, size = sha256_file(path)
        fingerprints.append(
            SeedFingerprint(
                logical_name=path.relative_to(seed_root).as_posix(),
                sha256=digest,
                size_bytes=size,
            )
        )
    return fingerprints


def initialize_manifest(
    *,
    run_dir: Path,
    run_id: str,
    workspace_id: str,
    scenario_id: str,
    config: dict[str, Any],
    seed_root: Path,
    project_root: Path,
) -> "ProvenanceRecorder":
    """Create the manifest after effective inputs exist and before execution starts."""
    UUID(run_id)
    simulation = config.get("simulation", {})
    setup = config.get("setup", {})
    plan_design_id = (
        config.get("plan_design_id")
        or config.get("plan_design", {}).get("plan_design_id")
        or "default"
    )
    effective, redactions = safe_effective_config(config)
    findings: list[EvidenceFinding] = []
    census = None
    census_path = setup.get("census_parquet_path")
    try:
        if census_path:
            suffix = Path(census_path).suffix.lower()
            census = fingerprint_input(
                Path(census_path),
                logical_name=f"census{suffix}" if suffix else "census",
            )
    except (OSError, CaptureError) as exc:
        findings.append(_finding("census_input", "unavailable", str(exc)))
    try:
        seeds = fingerprint_seed_directory(seed_root)
    except (OSError, CaptureError) as exc:
        seeds = []
        findings.append(_finding("seed_files", "unavailable", str(exc)))
    random_seed = simulation.get("random_seed")
    if not isinstance(random_seed, int) or isinstance(random_seed, bool):
        random_seed = None
        findings.append(
            _finding(
                "random_seed",
                "unavailable",
                "simulation.random_seed was not an integer",
            )
        )
    started = utc_now()
    manifest = RunProvenanceManifest(
        run_id=run_id,
        capture_state="capturing",
        run_identity=RunIdentityEvidence(
            run_id=run_id,
            workspace_id=workspace_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            status="running",
            intended_start_year=simulation.get("start_year"),
            intended_end_year=simulation.get("end_year"),
        ),
        execution_timing=ExecutionTimingEvidence(started_at=started),
        software=capture_source_state(project_root),
        configuration=ConfigurationEvidence(
            effective=effective,
            fingerprint=config_fingerprint(config),
            fingerprint_method="sha256-canonical-effective-config-v1",
            redactions=redactions,
        ),
        random_seed=random_seed,
        census_input=census,
        seed_files=seeds,
        capture_findings=findings,
        started_at=started,
    )
    recorder = ProvenanceRecorder(run_dir)
    recorder.write(manifest)
    return recorder


def _finding(field: str, code: str, reason: str) -> EvidenceFinding:
    safe_reason = reason.replace(str(Path.home()), "<home>")[:300]
    return EvidenceFinding(field_path=field, code=code, reason=safe_reason, required=True)  # type: ignore[arg-type]


def _validation_disposition(
    results: list[CapturedValidationResult],
) -> str:
    """Aggregate all captured yearly outcomes with failure precedence."""
    if not results:
        return "incomplete"
    if any(
        not result.passed and result.severity.lower() == "error" for result in results
    ):
        return "failed"
    if any(not result.passed for result in results):
        return "passed_with_warnings"
    return "passed"


class ProvenanceRecorder:
    """Atomic execution-only updater for a run's provenance manifest."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.path = run_dir / MANIFEST_NAME

    def read(self) -> RunProvenanceManifest:
        return RunProvenanceManifest.model_validate_json(
            self.path.read_text(encoding="utf-8")
        )

    def write(self, manifest: RunProvenanceManifest) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = manifest.model_dump_json(indent=2).encode("utf-8") + b"\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=".provenance-", suffix=".tmp", dir=self.run_dir
        )
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def ingest(self, record: dict[str, Any]) -> None:
        manifest = self.read()
        if record.get("run_id") != str(manifest.run_id):
            manifest.capture_findings.append(
                _finding(
                    "structured_records.run_id",
                    "unbound",
                    "structured execution evidence did not match the authoritative run ID",
                )
            )
            self.write(manifest)
            return
        kind = record.get("record")
        year = record.get("year")
        if kind == "run_started":
            manifest.execution_timing.started_at = (
                record.get("ts") or manifest.started_at
            )
        elif kind == "year_completed" and isinstance(year, int):
            manifest.run_identity.completed_years.append(year)
            counts = record.get("event_counts") or {}
            if not counts:
                counts = {"TOTAL": 0}
            manifest.event_counts = [
                item for item in manifest.event_counts if item.simulation_year != year
            ]
            manifest.event_counts.extend(
                AnnualEventCount(
                    simulation_year=year, event_type=str(name), count=int(count)
                )
                for name, count in sorted(counts.items())
                if int(count) >= 0
            )
            reconciliation = record.get("workforce_reconciliation")
            if isinstance(reconciliation, dict):
                manifest.workforce_reconciliations = [
                    item
                    for item in manifest.workforce_reconciliations
                    if item.simulation_year != year
                ]
                manifest.workforce_reconciliations.append(
                    AnnualWorkforceReconciliation(
                        simulation_year=year, **reconciliation
                    )
                )
        elif kind == "validation_results" and isinstance(year, int):
            manifest.validation_results = [
                item
                for item in manifest.validation_results
                if item.simulation_year != year
            ]
            for result in record.get("results", []):
                manifest.validation_results.append(
                    CapturedValidationResult(
                        simulation_year=year,
                        check_name=str(result.get("check_name", "unknown")),
                        severity=str(result.get("severity", "unknown")),
                        passed=bool(result.get("passed")),
                        affected_record_count=result.get("affected_record_count"),
                    )
                )
            manifest.validation_disposition = _validation_disposition(  # type: ignore[assignment]
                manifest.validation_results
            )
        elif kind == "stage_completed":
            manifest.execution_timing.terminal_stage = str(record.get("stage"))
            completion = StageCompletion(
                simulation_year=year if isinstance(year, int) else None,
                stage=str(record.get("stage", "UNKNOWN")),
                completed_at=record.get("ts"),
                duration_seconds=record.get("duration_seconds"),
            )
            manifest.completed_stages.append(completion)
            manifest.execution_timing.stage_completions.append(completion)
        self.write(RunProvenanceManifest.model_validate(manifest.model_dump()))

    def finalize(
        self,
        status: str,
        *,
        completed_at: Any = None,
        duration_seconds: float | None = None,
    ) -> None:
        manifest = self.read()
        state = status if status in {"completed", "failed", "cancelled"} else "failed"
        finalized = completed_at or utc_now()
        manifest.finalized_at = finalized
        manifest.execution_timing.completed_at = finalized
        manifest.execution_timing.duration_seconds = duration_seconds
        manifest.run_identity.status = status
        manifest.capture_state = state  # type: ignore[assignment]
        self.write(manifest)
