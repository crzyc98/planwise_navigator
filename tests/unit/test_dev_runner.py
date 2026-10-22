"""Offline regression checks for selecting a checkout's development environment."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/dev.py"
SPEC = importlib.util.spec_from_file_location("dev_runner", SCRIPT)
DEV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEV)


class DevRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "worktree"
        self.primary = Path(self.temp.name) / "main"
        for root in (self.root, self.primary):
            root.mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname="fidelity-planalign-engine"\n'
                'requires-python=">=3.12"\ndependencies=["duckdb==1.5.6"]\n'
            )
            (root / "uv.lock").write_text("same lock")
        self.venv = self.primary / ".venv"
        (self.venv / "bin").mkdir(parents=True)
        (self.venv / "bin/python").touch()

    def test_matching_worktree_borrows_existing_environment(self) -> None:
        self.assertEqual(DEV.choose_environment(self.root, self.primary), self.venv)
        self.assertFalse((self.root / ".venv").exists())

    def test_local_environment_takes_precedence(self) -> None:
        local = self.root / ".venv"
        (local / "bin").mkdir(parents=True)
        (local / "bin/python").touch()
        self.assertEqual(DEV.choose_environment(self.root, self.primary), local)

    def test_changed_lock_refuses_fallback(self) -> None:
        (self.root / "uv.lock").write_text("different lock")
        with self.assertRaisesRegex(ValueError, "uv.lock differs"):
            DEV.choose_environment(self.root, self.primary)

    def test_changed_dependencies_refuse_fallback(self) -> None:
        config = self.root / "pyproject.toml"
        config.write_text(config.read_text().replace("1.5.6", "1.4.0"))
        with self.assertRaisesRegex(ValueError, "dependencies differ"):
            DEV.choose_environment(self.root, self.primary)

    def test_broken_local_environment_is_not_silently_replaced(self) -> None:
        (self.root / ".venv").symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "Broken local"):
            DEV.choose_environment(self.root, self.primary)

    def test_environment_overrides_inherited_python_and_preserves_database(
        self,
    ) -> None:
        inherited = {
            "PATH": "/usr/bin",
            "PYTHONPATH": "/wrong/checkout",
            "PYTHONHOME": "/wrong/python",
            "DATABASE_PATH": "/isolated/run.duckdb",
        }
        with patch.dict(os.environ, inherited, clear=True):
            env = DEV.environment(self.root, self.venv)
        self.assertEqual(env["PYTHONPATH"], str(self.root))
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(self.venv / "bin"))
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["DATABASE_PATH"], inherited["DATABASE_PATH"])

    def test_missing_required_path_prevents_command_execution(self) -> None:
        args = ["dev.py", "--require", str(self.root / "absent"), "--", "python"]
        with (
            patch.object(sys, "argv", args),
            patch.object(
                DEV, "git_path", side_effect=[self.root, self.primary / ".git"]
            ),
            patch.object(DEV, "verify") as verify,
            patch.object(DEV.subprocess, "run") as run,
        ):
            self.assertEqual(DEV.main(), 2)
        verify.assert_not_called()
        run.assert_not_called()

    def test_child_status_and_cwd_are_preserved(self) -> None:
        with (
            patch.object(sys, "argv", ["dev.py", "--", "rg", "missing"]),
            patch.object(
                DEV, "git_path", side_effect=[self.root, self.primary / ".git"]
            ),
            patch.object(DEV, "verify"),
            patch.object(
                DEV.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)
            ) as run,
        ):
            self.assertEqual(DEV.main(), 1)
        self.assertEqual(run.call_args.args[0], ["rg", "missing"])
        self.assertNotIn("cwd", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
