"""Structured progress protocol for fit/backtest subprocesses (#588)."""

from __future__ import annotations

import json

import pytest

from planalign_fit import progress

pytestmark = pytest.mark.fast


def test_emit_is_silent_unless_enabled(monkeypatch, capsys):
    monkeypatch.delenv(progress.ENV_FLAG, raising=False)
    progress.emit("stage", stage="fitting")
    assert capsys.readouterr().out == ""


def test_emit_writes_one_sentinel_line(monkeypatch, capsys):
    monkeypatch.setenv(progress.ENV_FLAG, "1")
    progress.emit("seed_started", seed=42, index=1, total=3, years=[2024])
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert out.startswith(progress.SENTINEL)
    record = json.loads(out[len(progress.SENTINEL) :])
    assert record == {
        "v": 1,
        "event": "seed_started",
        "seed": 42,
        "index": 1,
        "total": 3,
        "years": [2024],
    }


def test_parse_round_trips(monkeypatch, capsys):
    monkeypatch.setenv(progress.ENV_FLAG, "1")
    progress.emit("stage", stage="scoring")
    line = capsys.readouterr().out
    assert progress.parse_progress_line(line) == {
        "v": 1,
        "event": "stage",
        "stage": "scoring",
    }


@pytest.mark.parametrize(
    "line",
    [
        "plain log output",
        'PLANALIGN_TELEMETRY|{"event": "stage"}',
        progress.SENTINEL + "not json",
        progress.SENTINEL + "[1, 2]",
        progress.SENTINEL + '{"stage": "no event key"}',
    ],
)
def test_parse_ignores_everything_else(line):
    assert progress.parse_progress_line(line) is None
