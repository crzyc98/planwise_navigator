"""Generate paired provenance reports for one exact archived run."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import UUID

import typer
from rich.console import Console

from planalign_api.config import get_settings
from planalign_api.services.provenance.locator import (
    ArchiveUnstableError,
    IdentityConflictError,
    RunNotFoundError,
    locate_run_archive,
)
from planalign_api.services.provenance.render import render_json, render_markdown
from planalign_api.services.provenance.report import build_provenance_report

console = Console()


def generate_provenance_report(
    run_id: str,
    output_dir: Path,
    workspaces_root: Path | None = None,
    force: bool = False,
) -> None:
    """Write deterministic JSON and Markdown without modifying the archive."""
    root = workspaces_root or get_settings().workspaces_root
    try:
        if str(UUID(run_id)) != run_id.lower():
            raise ValueError("run ID must use canonical UUID form")
        if not root.is_dir():
            raise ValueError("workspace root must be an existing directory")
    except (ValueError, AttributeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    try:
        archive = locate_run_archive(root, run_id)
    except RunNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(3) from exc
    except (IdentityConflictError, ArchiveUnstableError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(4) from exc

    try:
        destination = output_dir.resolve()
        run_dir = archive.run_dir.resolve()
        if destination == run_dir or run_dir in destination.parents:
            raise ValueError("output directory must be outside the run archive")
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / f"{run_id}-provenance.json"
        md_path = destination / f"{run_id}-provenance.md"
        if not force and (json_path.exists() or md_path.exists()):
            raise ValueError(
                "report output already exists; use --force to replace both files"
            )
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    try:
        report = build_provenance_report(root, run_id)
        _publish_pair(json_path, render_json(report), md_path, render_markdown(report))
    except (IdentityConflictError, ArchiveUnstableError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(4) from exc
    except Exception as exc:
        console.print(f"[red]Provenance report generation failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    label = report.verification_disposition.replace("_", " ").title()
    console.print(f"[bold]{label}[/bold] — run {run_id} ({report.evidence.run.status})")
    console.print(f"SHA-256: {report.digest.value}")
    console.print(f"Missing evidence: {len(report.missing_evidence)}")
    console.print(f"JSON: {json_path}")
    console.print(f"Markdown: {md_path}")


def _publish_pair(json_path: Path, json_text: str, md_path: Path, md_text: str) -> None:
    """Stage both files, then atomically replace destinations with cleanup."""
    temp_paths: list[Path] = []
    published: list[Path] = []
    previous = {
        target: target.read_bytes() if target.exists() else None
        for target in (json_path, md_path)
    }
    try:
        for target, content in ((json_path, json_text), (md_path, md_text)):
            fd, name = tempfile.mkstemp(
                prefix=f".{target.name}-", suffix=".tmp", dir=target.parent
            )
            temp = Path(name)
            temp_paths.append(temp)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                if not content.endswith("\n"):
                    stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        for temp, target in zip(temp_paths, (json_path, md_path)):
            os.replace(temp, target)
            published.append(target)
        temp_paths.clear()
    except Exception:
        for target in published:
            old = previous[target]
            if old is None:
                target.unlink(missing_ok=True)
            else:
                fd, name = tempfile.mkstemp(
                    prefix=f".{target.name}-restore-", dir=target.parent
                )
                with os.fdopen(fd, "wb") as stream:
                    stream.write(old)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, target)
        raise
    finally:
        for temp in temp_paths:
            temp.unlink(missing_ok=True)
