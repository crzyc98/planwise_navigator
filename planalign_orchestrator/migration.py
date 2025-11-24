#!/usr/bin/env python3
"""
Migration and compatibility utilities for the Navigator Orchestrator refactor.

Provides helpers to verify configuration compatibility, checkpoint format, and
to run sanity comparisons across versions when possible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import load_simulation_config


@dataclass
class MigrationResult:
    success: bool
    error: Optional[str] = None
    completed_steps: Optional[List[str]] = None


class MigrationManager:
    def __init__(self, *, checkpoints_dir: Path | str = Path(".navigator_checkpoints")):
        self.checkpoints_dir = Path(checkpoints_dir)

    def validate_config_compatibility(self, config_path: Path | str) -> Dict[str, Any]:
        """Load config and report on fields relevant to the modular orchestrator."""
        cfg = load_simulation_config(Path(config_path))
        report = {
            "has_identifiers": bool(cfg.scenario_id and cfg.plan_design_id),
            "simulation_years": (cfg.simulation.start_year, cfg.simulation.end_year),
        }
        return report

    def migrate_checkpoints(self) -> MigrationResult:
        """Ensure checkpoint directory exists and sanitize stale entries."""
        try:
            self.checkpoints_dir.mkdir(exist_ok=True)
            # Basic sweep: drop obviously corrupt JSON files
            removed: List[str] = []
            for p in self.checkpoints_dir.glob("year_*.json"):
                try:
                    json.loads(p.read_text())
                except Exception:
                    removed.append(p.name)
                    p.unlink(missing_ok=True)
            return MigrationResult(
                success=True, completed_steps=["checkpoints_dir", *removed]
            )
        except Exception as e:
            return MigrationResult(success=False, error=str(e))

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for p in sorted(self.checkpoints_dir.glob("year_*.json")):
            try:
                data = json.loads(p.read_text())
                rows.append({"file": p.name, **data})
            except Exception:
                rows.append({"file": p.name, "error": "unreadable"})
        return rows
