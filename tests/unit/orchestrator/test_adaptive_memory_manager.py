"""Tests for planalign_orchestrator.adaptive_memory_manager module.

Covers batch-size configuration lookup, memory pressure-level thresholds,
recommendation serialization/filtering, statistics reset, profile export, the
factory threshold math, and monitoring lifecycle.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from planalign_orchestrator.adaptive_memory_manager import (
    AdaptiveConfig,
    AdaptiveMemoryManager,
    BatchSizeConfig,
    MemoryPressureLevel,
    MemoryRecommendation,
    MemoryThresholds,
    OptimizationLevel,
    create_adaptive_memory_manager,
)

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manager(tmp_path, **config_kwargs) -> AdaptiveMemoryManager:
    config = AdaptiveConfig(**config_kwargs)
    return AdaptiveMemoryManager(
        config, logger=MagicMock(), reports_dir=tmp_path / "memory"
    )


# ---------------------------------------------------------------------------
# BatchSizeConfig
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level,expected",
    [
        (OptimizationLevel.LOW, 250),
        (OptimizationLevel.MEDIUM, 500),
        (OptimizationLevel.HIGH, 1000),
        (OptimizationLevel.FALLBACK, 100),
    ],
)
def test_batch_size_config_get_size(level, expected):
    assert BatchSizeConfig().get_size(level) == expected


# ---------------------------------------------------------------------------
# MemoryRecommendation
# ---------------------------------------------------------------------------


def test_memory_recommendation_to_dict_roundtrip():
    rec = MemoryRecommendation(
        recommendation_type="gc",
        description="trigger gc",
        action="collect",
        priority="high",
        estimated_savings_mb=120.0,
        confidence=0.9,
    )
    d = rec.to_dict()
    assert d["type"] == "gc"
    assert d["priority"] == "high"
    assert d["estimated_savings_mb"] == 120.0
    # timestamp is serialised as ISO-8601 string
    datetime.fromisoformat(d["timestamp"])


# ---------------------------------------------------------------------------
# _calculate_pressure_level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rss_mb,available_mb,expected",
    [
        (100.0, 8000.0, MemoryPressureLevel.LOW),
        (2100.0, 8000.0, MemoryPressureLevel.MODERATE),  # rss over moderate
        (3100.0, 8000.0, MemoryPressureLevel.HIGH),  # rss over high
        (3600.0, 8000.0, MemoryPressureLevel.CRITICAL),  # rss over critical
        (100.0, 400.0, MemoryPressureLevel.CRITICAL),  # <500MB available
        (100.0, 900.0, MemoryPressureLevel.HIGH),  # <1GB available
        (100.0, 1500.0, MemoryPressureLevel.MODERATE),  # <2GB available
    ],
)
def test_calculate_pressure_level(tmp_path, rss_mb, available_mb, expected):
    mgr = _manager(tmp_path)
    assert mgr._calculate_pressure_level(rss_mb, available_mb) == expected


# ---------------------------------------------------------------------------
# Statistics / state accessors
# ---------------------------------------------------------------------------


def test_initial_batch_size_matches_medium_level(tmp_path):
    mgr = _manager(tmp_path)
    assert mgr.get_current_optimization_level() == OptimizationLevel.MEDIUM
    assert mgr.get_current_batch_size() == BatchSizeConfig().medium


def test_reset_statistics_clears_counters_and_recommendations(tmp_path):
    mgr = _manager(tmp_path)
    mgr._stats["total_gc_collections"] = 5
    mgr._recommendations.append(MemoryRecommendation("gc", "d", "a"))

    mgr.reset_statistics()

    assert mgr._stats["total_gc_collections"] == 0
    assert mgr._recommendations == []


def test_get_recommendations_recent_only_filters_old(tmp_path):
    mgr = _manager(tmp_path)
    old = MemoryRecommendation("gc", "old", "a")
    old.timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
    fresh = MemoryRecommendation("gc", "fresh", "a")
    mgr._recommendations.extend([old, fresh])

    recent = mgr.get_recommendations(recent_only=True)
    assert [r["description"] for r in recent] == ["fresh"]

    everything = mgr.get_recommendations(recent_only=False)
    assert len(everything) == 2


def test_get_memory_statistics_structure(tmp_path):
    mgr = _manager(tmp_path)
    stats = mgr.get_memory_statistics()
    assert set(stats) >= {"current", "trends", "stats", "monitoring_active"}
    assert stats["monitoring_active"] is False
    assert stats["stats"]["total_gc_collections"] == 0


# ---------------------------------------------------------------------------
# export_memory_profile
# ---------------------------------------------------------------------------


def test_export_memory_profile_writes_json(tmp_path):
    mgr = _manager(tmp_path)
    out = mgr.export_memory_profile()

    assert out.exists()
    data = json.loads(out.read_text())
    assert "metadata" in data
    assert "statistics" in data
    assert "history" in data


# ---------------------------------------------------------------------------
# Monitoring lifecycle
# ---------------------------------------------------------------------------


def test_start_monitoring_noop_when_disabled(tmp_path):
    mgr = _manager(tmp_path, enabled=False)
    mgr.start_monitoring()
    assert mgr._monitoring_active is False


def test_stop_monitoring_is_idempotent(tmp_path):
    mgr = _manager(tmp_path)
    # Never started; stop should not raise and leaves state clean.
    mgr.stop_monitoring()
    assert mgr._monitoring_active is False
    assert mgr._monitoring_thread is None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_derives_thresholds_from_memory_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # factory uses default reports/memory under cwd
    mgr = create_adaptive_memory_manager(memory_limit_gb=10.0, logger=MagicMock())
    t = mgr.config.thresholds
    assert t.moderate_mb == pytest.approx(10 * 1024 * 0.5)
    assert t.high_mb == pytest.approx(10 * 1024 * 0.75)
    assert t.critical_mb == pytest.approx(10 * 1024 * 0.9)


def test_factory_uses_defaults_without_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mgr = create_adaptive_memory_manager(logger=MagicMock())
    assert mgr.config.thresholds.critical_mb == MemoryThresholds().critical_mb
