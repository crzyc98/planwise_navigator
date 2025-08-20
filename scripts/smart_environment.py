#!/usr/bin/env python3
"""
Smart Environment Detection and Setup Utility for PlanWise Navigator

This utility prevents trial-and-error command execution by:
1. Detecting the correct project structure and paths upfront
2. Validating prerequisites before attempting operations
3. Setting up the environment (venv activation, correct working directory)
4. Providing clear error messages if setup requirements aren't met

Usage:
    from scripts.smart_environment import SmartEnvironment

    env = SmartEnvironment()
    if env.validate():
        # Execute commands using env.get_command_wrapper()
        result = env.execute_command("dbt run")
    else:
        print("Environment validation failed:", env.get_validation_errors())
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


class CommandType(Enum):
    """Categories of commands with specific directory and environment requirements."""

    DAGSTER = "dagster"  # Run from project root with venv
    DBT = "dbt"  # Run from dbt/ directory with venv
    STREAMLIT = "streamlit"  # Run from project root with venv
    PYTHON = "python"  # Run from project root with venv
    SYSTEM = "system"  # System commands (git, etc.)


@dataclass
class EnvironmentConfig:
    """Configuration for the detected environment."""

    project_root: Path
    venv_path: Optional[Path]
    dbt_path: Path
    python_executable: Optional[Path]
    dagster_home: Path
    database_files: Dict[str, Path]
    is_valid: bool = False
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class SmartEnvironment:
    """
    Smart environment detection and command execution utility.

    Eliminates trial-and-error by validating the environment upfront
    and providing intelligent command execution wrappers.
    """

    def __init__(self, start_path: Optional[Path] = None):
        self.start_path = Path(start_path) if start_path else Path.cwd()
        self.config: Optional[EnvironmentConfig] = None
        self._detected = False

        # Command mappings - defines which directory each command type needs
        self.command_mappings = {
            CommandType.DAGSTER: {
                "commands": ["dagster", "definitions.py"],
                "working_dir": "project_root",
                "requires_venv": True,
                "environment_vars": {"DAGSTER_HOME": "dagster_home"},
            },
            CommandType.DBT: {
                "commands": ["dbt"],
                "working_dir": "dbt_path",
                "requires_venv": True,
                "environment_vars": {},
            },
            CommandType.STREAMLIT: {
                "commands": ["streamlit"],
                "working_dir": "project_root",
                "requires_venv": True,
                "environment_vars": {},
            },
            CommandType.PYTHON: {
                "commands": ["python", "pytest"],
                "working_dir": "project_root",
                "requires_venv": True,
                "environment_vars": {},
            },
            CommandType.SYSTEM: {
                "commands": ["git", "make", "ls", "cat"],
                "working_dir": "current",
                "requires_venv": False,
                "environment_vars": {},
            },
        }

    def detect_project_root(self, start_path: Path) -> Optional[Path]:
        """
        Find the project root by looking for key indicator files.

        Returns the path to project root or None if not found.
        """
        current = start_path.resolve()

        # Key files that indicate project root
        indicators = [
            "CLAUDE.md",  # Primary indicator
            "definitions.py",  # Dagster entry point
            "dbt/dbt_project.yml",  # dbt project structure
            "pyproject.toml",  # Python project
            "Makefile",  # Build configuration
        ]

        # Walk up the directory tree
        for _ in range(10):  # Reasonable limit to prevent infinite loops
            # Check if this directory has the indicators
            indicator_count = 0
            for indicator in indicators:
                if (current / indicator).exists():
                    indicator_count += 1

            # If we find multiple indicators, this is likely the project root
            if indicator_count >= 2:
                return current

            # Move up one level
            parent = current.parent
            if parent == current:  # Reached filesystem root
                break
            current = parent

        return None

    def detect_environment(self) -> EnvironmentConfig:
        """
        Detect and validate the complete environment configuration.

        Returns EnvironmentConfig with validation results.
        """
        errors = []

        # 1. Find project root
        project_root = self.detect_project_root(self.start_path)
        if not project_root:
            errors.append(
                f"Could not find PlanWise Navigator project root from {self.start_path}"
            )
            return EnvironmentConfig(
                project_root=self.start_path,
                venv_path=None,
                dbt_path=self.start_path / "dbt",
                python_executable=None,
                dagster_home=self.start_path / ".dagster",
                database_files={},
                errors=errors,
            )

        # 2. Check for virtual environment
        venv_path = project_root / "venv"
        python_executable = None
        if venv_path.exists() and (venv_path / "bin" / "activate").exists():
            python_executable = venv_path / "bin" / "python"
            if not python_executable.exists():
                errors.append(
                    f"Virtual environment found but Python executable missing: {python_executable}"
                )
        else:
            errors.append(f"Virtual environment not found at {venv_path}")
            # Fallback to system Python
            python_executable = shutil.which("python3") or shutil.which("python")
            if python_executable:
                python_executable = Path(python_executable)
            else:
                errors.append("No Python executable found in system PATH")

        # 3. Validate dbt directory
        dbt_path = project_root / "dbt"
        if not dbt_path.exists():
            errors.append(f"dbt directory not found: {dbt_path}")
        elif not (dbt_path / "dbt_project.yml").exists():
            errors.append(
                f"dbt project configuration not found: {dbt_path / 'dbt_project.yml'}"
            )

        # 4. Check Dagster home
        dagster_home = project_root / ".dagster"

        # 5. Find database files
        database_files = {}
        db_candidates = [
            ("simulation", project_root / "simulation.duckdb"),
            ("dbt_simulation", project_root / "dbt" / "simulation.duckdb"),
            (
                "streamlit_simulation",
                project_root / "streamlit_dashboard" / "simulation.duckdb",
            ),
        ]

        for name, path in db_candidates:
            if path.exists():
                database_files[name] = path

        # 6. Validate key tools if venv exists
        if venv_path.exists() and python_executable:
            try:
                # Test if key packages are available
                cmd = [str(python_executable), "-c", "import dagster, dbt, streamlit"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    errors.append(
                        "Required packages not available in virtual environment"
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                errors.append("Could not validate Python environment")

        config = EnvironmentConfig(
            project_root=project_root,
            venv_path=venv_path if venv_path.exists() else None,
            dbt_path=dbt_path,
            python_executable=python_executable,
            dagster_home=dagster_home,
            database_files=database_files,
            errors=errors,
            is_valid=len(errors) == 0,
        )

        return config

    def validate(self) -> bool:
        """
        Validate the environment and cache the results.

        Returns True if environment is valid, False otherwise.
        """
        if not self._detected:
            self.config = self.detect_environment()
            self._detected = True

        return self.config.is_valid

    def get_validation_errors(self) -> List[str]:
        """Get list of validation errors."""
        if not self._detected:
            self.validate()
        return self.config.errors if self.config else ["Environment not detected"]

    def classify_command(self, command_line: str) -> CommandType:
        """
        Classify a command to determine its execution requirements.

        Args:
            command_line: The command line to classify (e.g., "dbt run", "dagster dev")

        Returns:
            CommandType enum indicating the command category
        """
        # Extract the main command (first token)
        main_command = command_line.strip().split()[0] if command_line.strip() else ""

        for cmd_type, config in self.command_mappings.items():
            if main_command in config["commands"]:
                return cmd_type

        # Special cases
        if "python" in main_command and any(
            keyword in command_line for keyword in ["dagster", "definitions.py"]
        ):
            return CommandType.DAGSTER
        if command_line.strip().endswith(".py"):
            return CommandType.PYTHON

        return CommandType.SYSTEM

    def get_execution_context(
        self, command_type: CommandType
    ) -> Dict[str, Union[Path, Dict[str, str]]]:
        """
        Get the execution context for a command type.

        Returns dictionary with working_dir, environment_vars, and executable info.
        """
        if not self._detected:
            self.validate()

        if not self.config:
            raise RuntimeError("Environment not properly detected")

        cmd_config = self.command_mappings[command_type]

        # Determine working directory
        working_dir_key = cmd_config["working_dir"]
        if working_dir_key == "project_root":
            working_dir = self.config.project_root
        elif working_dir_key == "dbt_path":
            working_dir = self.config.dbt_path
        else:  # "current"
            working_dir = Path.cwd()

        # Build environment variables
        env_vars = {}
        for var_name, config_key in cmd_config["environment_vars"].items():
            if config_key == "dagster_home":
                env_vars[var_name] = str(self.config.dagster_home)

        # Determine executable
        executable = None
        if cmd_config["requires_venv"] and self.config.python_executable:
            executable = self.config.python_executable

        return {
            "working_dir": working_dir,
            "environment_vars": env_vars,
            "executable": executable,
            "requires_venv": cmd_config["requires_venv"],
        }

    def execute_command(
        self, command_line: str, capture_output: bool = False
    ) -> subprocess.CompletedProcess:
        """
        Execute a command with proper environment setup.

        Args:
            command_line: Command to execute
            capture_output: Whether to capture stdout/stderr

        Returns:
            subprocess.CompletedProcess result
        """
        if not self.validate():
            raise RuntimeError(
                f"Environment validation failed: {self.get_validation_errors()}"
            )

        command_type = self.classify_command(command_line)
        context = self.get_execution_context(command_type)

        # Prepare command
        cmd_parts = command_line.split()

        # For venv-required commands, prefix with venv python if needed
        if context["requires_venv"] and context["executable"]:
            if cmd_parts[0] in ["python", "dbt", "dagster", "streamlit", "pytest"]:
                # Replace the executable with venv version
                if cmd_parts[0] == "python":
                    cmd_parts[0] = str(context["executable"])
                else:
                    # For other commands, use venv's bin directory
                    venv_bin = context["executable"].parent
                    cmd_parts[0] = str(venv_bin / cmd_parts[0])

        # Set up environment
        env = os.environ.copy()
        env.update(context["environment_vars"])

        # Execute with proper working directory
        try:
            result = subprocess.run(
                cmd_parts,
                cwd=context["working_dir"],
                env=env,
                capture_output=capture_output,
                text=True,
            )
            return result
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Command not found: {e}. Ensure virtual environment is set up correctly."
            )

    def get_setup_instructions(self) -> List[str]:
        """
        Get setup instructions for fixing environment issues.

        Returns list of setup commands to run.
        """
        if not self._detected:
            self.validate()

        if not self.config:
            return [
                "Environment detection failed - please run from PlanWise Navigator project directory"
            ]

        instructions = []

        # Virtual environment setup
        if not self.config.venv_path or not self.config.venv_path.exists():
            instructions.extend(
                [
                    "# Set up virtual environment:",
                    f"cd {self.config.project_root}",
                    "python3.11 -m venv venv",
                    "source venv/bin/activate",
                    "pip install --upgrade pip",
                    "pip install -r requirements.txt",
                    "pip install -r requirements-dev.txt",
                ]
            )

        # dbt setup
        if not self.config.dbt_path.exists():
            instructions.extend(["# dbt directory missing - check project structure"])
        elif not (self.config.dbt_path / "dbt_project.yml").exists():
            instructions.extend(
                [
                    "# Set up dbt project:",
                    f"cd {self.config.dbt_path}",
                    "dbt deps",
                    "dbt seed",
                ]
            )

        # Dagster home
        instructions.extend(
            [
                "# Ensure Dagster home directory exists:",
                f"mkdir -p {self.config.dagster_home}",
            ]
        )

        return instructions

    def print_environment_summary(self):
        """Print a summary of the detected environment."""
        if not self._detected:
            self.validate()

        if not self.config:
            print("❌ Environment detection failed")
            return

        print("🔍 PlanWise Navigator Environment Summary:")
        print("=" * 50)
        print(f"📁 Project Root: {self.config.project_root}")
        print(f"🐍 Python: {self.config.python_executable or 'Not found'}")
        print(f"📦 Virtual Env: {self.config.venv_path or 'Not found'}")
        print(f"🔧 dbt Directory: {self.config.dbt_path}")
        print(f"⚙️  Dagster Home: {self.config.dagster_home}")
        print(f"💾 Database Files: {len(self.config.database_files)} found")

        for name, path in self.config.database_files.items():
            print(f"   - {name}: {path}")

        if self.config.is_valid:
            print("✅ Environment is valid and ready for commands")
        else:
            print("❌ Environment has issues:")
            for error in self.config.errors:
                print(f"   - {error}")

            print("\n🛠️  Setup Instructions:")
            for instruction in self.get_setup_instructions():
                print(f"   {instruction}")


def main():
    """CLI interface for environment detection."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart environment detection for PlanWise Navigator"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate environment and exit"
    )
    parser.add_argument(
        "--summary", action="store_true", help="Print environment summary"
    )
    parser.add_argument("--setup", action="store_true", help="Print setup instructions")
    parser.add_argument("--execute", help="Execute command with smart environment")
    parser.add_argument("--working-dir", help="Override working directory")

    args = parser.parse_args()

    start_path = Path(args.working_dir) if args.working_dir else None
    env = SmartEnvironment(start_path)

    if args.summary:
        env.print_environment_summary()
    elif args.validate:
        if env.validate():
            print("✅ Environment validation passed")
            sys.exit(0)
        else:
            print("❌ Environment validation failed:")
            for error in env.get_validation_errors():
                print(f"   - {error}")
            sys.exit(1)
    elif args.setup:
        for instruction in env.get_setup_instructions():
            print(instruction)
    elif args.execute:
        try:
            result = env.execute_command(args.execute, capture_output=False)
            sys.exit(result.returncode)
        except Exception as e:
            print(f"❌ Command execution failed: {e}")
            sys.exit(1)
    else:
        env.print_environment_summary()


if __name__ == "__main__":
    main()
