"""Deterministic JSON, digest, Markdown, and ZIP renderers."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from planalign_api.models.provenance import (
    ProvenanceReport,
    ReportDigest,
    ReviewSignOff,
)

CANONICALIZATION = "planalign-provenance-json-v1"
_STAGE_ORDER = {
    name: index
    for index, name in enumerate(
        (
            "INITIALIZATION",
            "FOUNDATION",
            "EVENT_GENERATION",
            "STATE_ACCUMULATION",
            "VALIDATION",
            "REPORTING",
        )
    )
}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def canonical_payload(report: ProvenanceReport | dict[str, Any]) -> bytes:
    source = (
        report.model_dump(mode="python")
        if isinstance(report, ProvenanceReport)
        else report
    )
    payload = {
        "report_schema_version": source["report_schema_version"],
        "evidence": source["evidence"],
        "missing_evidence": source["missing_evidence"],
        "verification_disposition": source["verification_disposition"],
    }
    normalized = _normalize(payload)
    evidence = normalized["evidence"]
    evidence["run"]["completed_years"] = sorted(evidence["run"]["completed_years"])
    evidence["seed_files"] = sorted(
        evidence["seed_files"], key=lambda x: x["logical_name"]
    )
    evidence["event_counts"] = sorted(
        evidence["event_counts"], key=lambda x: (x["simulation_year"], x["event_type"])
    )
    evidence["workforce_reconciliations"] = sorted(
        evidence["workforce_reconciliations"], key=lambda x: x["simulation_year"]
    )
    evidence["validation_results"] = sorted(
        evidence["validation_results"],
        key=lambda x: (
            x["simulation_year"],
            x["check_name"],
            x["severity"],
            x["passed"],
        ),
    )
    evidence["timing"]["stage_completions"] = sorted(
        evidence["timing"]["stage_completions"],
        key=lambda x: (
            x["simulation_year"] or -1,
            _STAGE_ORDER.get(x["stage"], 999),
            x["completed_at"] or "",
        ),
    )
    normalized["missing_evidence"] = sorted(
        normalized["missing_evidence"],
        key=lambda x: (x["field_path"], x["code"], x["reason"]),
    )
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(k)): _normalize(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        if _CONTROL.search(normalized):
            raise ValueError(
                "canonical provenance strings cannot contain control characters"
            )
        return normalized
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical provenance numbers must be finite")
    return value


def attach_digest(report_data: dict[str, Any]) -> ProvenanceReport:
    digest = hashlib.sha256(canonical_payload(report_data)).hexdigest()
    report_data["digest"] = ReportDigest(value=digest).model_dump()
    report_data["sign_off"] = ReviewSignOff(report_digest=digest).model_dump()
    return ProvenanceReport.model_validate(report_data)


def render_json(report: ProvenanceReport) -> str:
    return report.model_dump_json(indent=2) + "\n"


def render_markdown(report: ProvenanceReport) -> str:
    e = report.evidence
    missing = (
        "None"
        if not report.missing_evidence
        else "\n".join(
            f"- `{item.field_path}` — {item.code}: {item.reason}"
            for item in report.missing_evidence
        )
    )
    seeds = (
        "\n".join(
            f"- `{x.logical_name}`: `{x.sha256}` ({x.size_bytes} bytes)"
            for x in e.seed_files
        )
        or "None"
    )
    events = (
        "\n".join(
            f"| {x.simulation_year} | {x.event_type} | {x.count} |"
            for x in e.event_counts
        )
        or "| — | — | — |"
    )
    recs = (
        "\n".join(
            f"| {x.simulation_year} | {x.opening_workforce} | {x.hires} | {x.terminations} | {x.expected_closing_workforce} | {x.actual_closing_workforce} | {x.variance} | {x.opening_source} |"
            for x in e.workforce_reconciliations
        )
        or "| — | — | — | — | — | — | — | — |"
    )
    validations = (
        "\n".join(
            f"| {x.simulation_year} | {x.check_name} | {x.severity} | {'PASS' if x.passed else 'FAIL'} | {x.affected_record_count} |"
            for x in e.validation_results
        )
        or "| — | — | — | — | — |"
    )
    stages = (
        "\n".join(
            f"| {x.simulation_year} | {x.stage} | {x.started_at} | {x.completed_at} | {x.duration_seconds} | {x.outcome} |"
            for x in e.timing.stage_completions
        )
        or "| — | — | — | — | — | — |"
    )
    config = json.dumps(
        e.configuration.effective, sort_keys=True, ensure_ascii=False, indent=2
    )
    return f"""# PlanAlign Run Provenance Audit Sheet

**Run ID:** `{e.run.run_id}`
**Archived status:** {e.run.status}
**Verification disposition:** **{report.verification_disposition.replace('_', ' ').title()}**

## Missing/Unavailable Evidence

{missing}

## Run Identity and Execution Timing

- Workspace: {e.run.workspace_id}
- Scenario design: {e.run.scenario_id}
- Plan design: {e.run.plan_design_id}
- Simulation years: {e.run.intended_start_year}–{e.run.intended_end_year}
- Completed years: {', '.join(map(str, e.run.completed_years)) or 'None'}
- Started: {e.timing.started_at}
- Completed: {e.timing.completed_at}
- Duration seconds: {e.timing.duration_seconds}
- Terminal stage: {e.timing.terminal_stage}

| Year | Stage | Started | Completed | Seconds | Outcome |
|---:|---|---|---|---:|---|
{stages}

## Software and Source State

- PlanAlign version: {e.software.planalign_version}
- Git commit SHA: {e.software.git_commit_sha}
- Working tree: {e.software.working_tree_state}
- Working-tree fingerprint: {e.software.working_tree_fingerprint}

## Effective Configuration and Fingerprint

- Fingerprint: `{e.configuration.fingerprint}`
- Method: {e.configuration.fingerprint_method}
- Redactions: {', '.join(e.configuration.redactions) or 'None'}
- Random seed: {e.random_seed}

```json
{config}
```

## Census Input and Effective Seed Files

- Census: {e.census_input.logical_name if e.census_input else None}
- Census SHA-256: `{e.census_input.sha256 if e.census_input else None}`
- Census records: {e.census_input.record_count if e.census_input else None}
- Census size bytes: {e.census_input.size_bytes if e.census_input else None}
- Census format: {e.census_input.format if e.census_input else None}

{seeds}

## Event Counts by Simulation Year and Event Type

| Year | Event type | Count |
|---:|---|---:|
{events}

## Annual Workforce Reconciliation

| Year | Opening | Hires | Terminations | Expected close | Actual close | Variance | Opening source |
|---:|---:|---:|---:|---:|---:|---:|---|
{recs}

## Captured Validation Results

Overall disposition: **{e.validation_disposition}**

| Year | Check | Severity | Outcome | Affected records |
|---:|---|---|---|---:|
{validations}

## Integrity Verification

- Algorithm: SHA-256
- Canonicalization: `{CANONICALIZATION}`
- Report digest: `{report.digest.value}`

Remove `digest` and `sign_off`, canonicalize the four covered report fields with `{CANONICALIZATION}`, and compare SHA-256 with the value above.

## Reviewer Sign-Off

Report digest approved: {report.digest.value}
Reviewer name: ______________________________
Decision:      ______________________________
Timestamp:     ______________________________
Comments:      ______________________________
               ______________________________
"""


def render_zip(run_id: str, report: ProvenanceReport, markdown: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for suffix, content in (("json", render_json(report)), ("md", markdown)):
            info = zipfile.ZipInfo(
                f"{run_id}-provenance.{suffix}", (1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content.encode("utf-8"))
    return buffer.getvalue()
