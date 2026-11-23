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
    monkeypatch.setenv("PLANALIGN_API_TOKEN", "test-studio-api-token")
    studio._warn_for_unsafe_bind("0.0.0.0")

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_token", ["", "   ", "too-short-tok"])
def test_studio_rejects_invalid_api_token_before_launch(
    monkeypatch, capsys, bad_token: str
) -> None:
    monkeypatch.setenv("PLANALIGN_API_TOKEN", bad_token)

    with pytest.raises(SystemExit) as exc_info:
        studio._validate_configured_api_token()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "PLANALIGN_API_TOKEN" in out
    assert "16" in out
    if bad_token.strip():
        assert bad_token.strip() not in out


def test_studio_accepts_unset_or_valid_api_token(monkeypatch) -> None:
    monkeypatch.delenv("PLANALIGN_API_TOKEN", raising=False)
    studio._validate_configured_api_token()

    monkeypatch.setenv("PLANALIGN_API_TOKEN", "test-studio-api-token")
    studio._validate_configured_api_token()


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


def test_studio_reload_watches_evidence_pack_sources() -> None:
    root = Path(__file__).parents[3]
    source = (root / "planalign_cli" / "commands" / "studio.py").read_text(
        encoding="utf-8"
    )

    assert '"planalign_evidence"' in source
    assert '"planalign_ensemble"' in source


def test_vite_proxy_sends_the_api_its_own_host() -> None:
    # The API's Host allowlist relies on the proxy rewriting Host to its target.
    source = (
        Path(__file__).parents[3] / "planalign_studio" / "vite.config.ts"
    ).read_text()

    assert source.count("changeOrigin: true") == 2
