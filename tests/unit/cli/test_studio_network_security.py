"""Regression tests for PlanAlign Studio's network-security defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from planalign_cli.commands import studio

pytestmark = pytest.mark.fast


def test_bind_host_defaults_to_loopback(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_HOST", raising=False)

    assert studio._resolve_bind_host(None) == "127.0.0.1"


def test_bind_host_uses_environment_and_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("PLANALIGN_API_HOST", "192.0.2.10")

    assert studio._resolve_bind_host(None) == "192.0.2.10"
    assert studio._resolve_bind_host("localhost") == "localhost"


def test_non_loopback_without_token_prints_security_warning(
    monkeypatch, capsys
) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)

    studio._warn_for_unsafe_bind("0.0.0.0")

    assert "SECURITY WARNING" in capsys.readouterr().out


def test_loopback_and_authenticated_bindings_do_not_warn(monkeypatch, capsys) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
    studio._warn_for_unsafe_bind("127.0.0.1")
    monkeypatch.setenv("PLANALIGN_API_TOKEN", "secret")
    studio._warn_for_unsafe_bind("0.0.0.0")

    assert capsys.readouterr().out == ""


def test_vite_config_uses_safe_host_defaults_and_explicit_allowlist() -> None:
    root = Path(__file__).parents[3]
    source = (root / "planalign_studio" / "vite.config.ts").read_text(encoding="utf-8")

    assert "env.PLANALIGN_API_HOST || '127.0.0.1'" in source
    assert "PLANALIGN_STUDIO_ALLOWED_HOSTS" in source
    assert "allowedHosts: true" not in source
    assert "host: '0.0.0.0'" not in source


def test_api_runner_defaults_to_loopback() -> None:
    root = Path(__file__).parents[3]
    source = (root / "planalign_api" / "run.py").read_text(encoding="utf-8")

    assert 'parser.add_argument("--host", default="127.0.0.1"' in source
