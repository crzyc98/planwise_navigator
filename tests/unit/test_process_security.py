"""Unit tests for process-level umask configuration (planalign_core.process_security).

The root conftest restores the umask after every test.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from planalign_core import process_security

pytestmark = pytest.mark.fast


def _current_umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


@pytest.mark.skipif(os.name != "posix", reason="POSIX umask semantics only")
def test_restrict_file_permissions_sets_default_077(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(process_security.UMASK_ENV_VAR, raising=False)
    os.umask(0o022)

    process_security.restrict_file_permissions()

    assert _current_umask() == 0o077
    created_file = tmp_path / "secret.txt"
    created_file.write_text("census", encoding="utf-8")
    created_dir = tmp_path / "private_dir"
    created_dir.mkdir()
    assert stat.S_IMODE(created_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(created_dir.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX umask semantics only")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("027", 0o027),
        ("0027", 0o027),
        ("0o027", 0o027),
        ("0O022", 0o022),
        (" 027 ", 0o027),
        ("", 0o077),
        ("   ", 0o077),
    ],
)
def test_restrict_file_permissions_honours_env_var(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    monkeypatch.setenv(process_security.UMASK_ENV_VAR, raw)
    os.umask(0o002)

    process_security.restrict_file_permissions()

    assert _current_umask() == expected


@pytest.mark.skipif(os.name != "posix", reason="POSIX umask semantics only")
@pytest.mark.parametrize("bad_value", ["088", "abc", "-022", "+022", "1000", "0x22"])
def test_restrict_file_permissions_invalid_value_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    bad_value: str,
) -> None:
    monkeypatch.setenv(process_security.UMASK_ENV_VAR, bad_value)
    os.umask(0o022)

    with caplog.at_level(logging.WARNING, logger=process_security.__name__):
        process_security.restrict_file_permissions()

    assert _current_umask() == 0o077
    assert any(
        process_security.UMASK_ENV_VAR in record.message
        and "falling back" in record.message
        for record in caplog.records
    )


def test_restrict_file_permissions_noop_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _fail_umask(mask: int) -> int:
        nonlocal called
        called = True
        return mask

    monkeypatch.setattr(process_security.os, "name", "nt")
    monkeypatch.setattr(process_security.os, "umask", _fail_umask)

    process_security.restrict_file_permissions()

    assert called is False


def test_cli_main_applies_umask_before_running_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import planalign_cli.main as cli_module

    events: list[str] = []
    monkeypatch.setattr(
        process_security,
        "restrict_file_permissions",
        lambda: events.append("umask"),
    )
    monkeypatch.setattr(cli_module, "app", lambda: events.append("app"))

    cli_module.cli_main()

    assert events == ["umask", "app"]


def test_api_lifespan_applies_umask_on_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    import planalign_api.config as api_config
    import planalign_api.main as api_main
    from planalign_api.services import calibration_jobs
    from planalign_api.services.calibration_process import ProcessRegistry

    called: list[str] = []
    monkeypatch.setattr(
        api_main,
        "restrict_file_permissions",
        lambda: called.append("umask"),
    )
    monkeypatch.setattr(
        api_config,
        "settings",
        api_config.APISettings(workspaces_root=tmp_path / "workspaces"),
    )
    monkeypatch.setattr(calibration_jobs, "registry", ProcessRegistry())

    with TestClient(api_main.create_app()):
        assert called == ["umask"]


def test_api_run_main_applies_umask_before_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import planalign_api.run as api_run

    events: list[str] = []
    monkeypatch.setattr(
        api_run,
        "restrict_file_permissions",
        lambda: events.append("umask"),
    )
    monkeypatch.setattr(
        api_run.uvicorn,
        "run",
        lambda *_args, **_kwargs: events.append("uvicorn"),
    )
    monkeypatch.setattr("sys.argv", ["planalign-api"])

    api_run.main()

    assert events == ["umask", "uvicorn"]
