"""Run development commands with the active checkout's verified Python environment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib


def git_path(argument: str) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", argument],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve()


def dependency_contract(root: Path) -> dict:
    config = tomllib.loads((root / "pyproject.toml").read_text())
    project = config["project"]
    if project["name"] != "fidelity-planalign-engine":
        raise ValueError(f"Not a PlanAlign checkout: {root}")
    return {
        key: project.get(key)
        for key in ("requires-python", "dependencies", "optional-dependencies")
    }


def choose_environment(root: Path, primary: Path) -> Path:
    """Never silently borrow dependencies from a different dependency contract."""
    contract = dependency_contract(root)
    local = root / ".venv"
    if local.exists() or local.is_symlink():
        if not (local / "bin/python").is_file():
            raise ValueError(f"Broken local environment: {local}")
        return local
    if contract != dependency_contract(primary):
        raise ValueError("Worktree dependencies differ; provision its own .venv first.")
    current, shared = root / "uv.lock", primary / "uv.lock"
    if current.exists() != shared.exists():
        raise ValueError("uv.lock differs; provision a worktree .venv first.")
    if current.exists() and current.read_bytes() != shared.read_bytes():
        raise ValueError("uv.lock differs; provision a worktree .venv first.")
    shared_env = primary / ".venv"
    if not (shared_env / "bin/python").is_file():
        raise ValueError(f"No usable Python environment at {local} or {shared_env}")
    return shared_env


def environment(root: Path, venv: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv)
    env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    # Do not inherit another checkout's module path or Python installation prefix.
    env["PYTHONPATH"] = str(root)
    env.pop("PYTHONHOME", None)
    return env


def verify(root: Path, venv: Path, env: dict[str, str]) -> None:
    probe = """
import importlib.util, json, sys
modules = ('yaml', 'duckdb', 'pandas', 'pydantic', 'pytest', 'dbt')
missing = [name for name in modules if importlib.util.find_spec(name) is None]
origin = importlib.util.find_spec('planalign_core')
print(json.dumps({'python': sys.executable, 'missing': missing,
                  'source': origin.origin if origin else None,
                  'version': list(sys.version_info[:2])}))
"""
    result = subprocess.run(
        [str(venv / "bin/python"), "-c", probe],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    if report["version"] < [3, 12]:
        raise ValueError("PlanAlign requires Python 3.12 or newer.")
    if report["missing"]:
        raise ValueError(
            f"Environment {venv} is missing: {', '.join(report['missing'])}"
        )
    source = report["source"]
    if not source or not Path(source).resolve().is_relative_to(root):
        raise ValueError(f"PlanAlign imports resolve outside the checkout: {source}")
    print(
        f"Checkout: {root}\nPython: {report['python']}\nImports: {source}",
        file=sys.stderr,
        flush=True,
    )
    if venv.parent != root:
        print(
            "Using main-checkout dependencies; do not install into this shared environment.",
            file=sys.stderr,
            flush=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check without running a command."
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="PATH",
        help="Fail before running if a required path is absent (relative to cwd).",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.check and not args.command:
        parser.error("pass --check or -- followed by a command")
    return args


def main() -> int:
    args = parse_args()
    try:
        root = git_path("--show-toplevel")
        primary = git_path("--git-common-dir").parent
        for required in args.require:
            if not Path(required).exists():
                raise ValueError(
                    f"Required path missing: {required}. Discover it with rg --files first."
                )
        venv = choose_environment(root, primary)
        env = environment(root, venv)
        verify(root, venv, env)
        if args.check:
            runner = shlex.quote(str(Path(__file__).resolve()))
            print(f"Run commands: python3 {runner} -- <command>")
            for relative in ("dbt/dbt_packages", "planalign_studio/node_modules"):
                if not (root / relative).is_dir():
                    print(
                        f"Not provisioned: {relative}; prepare it before dbt/Studio work."
                    )
            return 0
        # Preserve cwd (especially dbt/) and the exact exit code, including search misses.
        return subprocess.run(args.command, env=env, check=False).returncode
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Development preflight failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
