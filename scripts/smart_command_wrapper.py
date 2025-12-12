#!/usr/bin/env python3
"""
Smart Command Wrapper for Fidelity PlanAlign Engine

This wrapper eliminates trial-and-error command execution by:
1. Validating the environment before executing any command
2. Automatically setting up the correct working directory
3. Activating virtual environment when needed
4. Setting required environment variables
5. Providing clear error messages when setup fails

Usage as a standalone tool:
    ./scripts/smart_command_wrapper.py "dbt run"
    ./scripts/smart_command_wrapper.py "dagster dev"

Usage as a Python module:
    from scripts.smart_command_wrapper import SmartCommandWrapper

    wrapper = SmartCommandWrapper()
    result = wrapper.execute("dbt run")
    if not result.success:
        print("Command failed:", result.error_message)
"""

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

# Import our environment detection utility
try:
    from .smart_environment import CommandType, SmartEnvironment
except ImportError:
    # Handle case where we're running directly
    sys.path.append(str(Path(__file__).parent))
    from smart_environment import CommandType, SmartEnvironment


@dataclass
class CommandResult:
    """Result of command execution."""

    success: bool
    returncode: int
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None
    command: Optional[str] = None
    working_dir: Optional[Path] = None
    duration_seconds: Optional[float] = None
    environment_setup: Optional[Dict] = None


class SmartCommandWrapper:
    """
    Intelligent command wrapper that handles environment setup automatically.

    This class prevents trial-and-error execution by:
    - Validating environment before any command execution
    - Setting up correct working directories
    - Activating virtual environments
    - Setting environment variables
    - Providing detailed error reporting
    """

    def __init__(self, working_dir: Optional[Path] = None, verbose: bool = False):
        """
        Initialize the command wrapper.

        Args:
            working_dir: Starting directory for environment detection
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.environment = SmartEnvironment(working_dir)
        self._validated = False
        self._validation_result = None

    def _log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {level}: {message}")

    def validate_environment(self) -> bool:
        """
        Validate the environment and cache results.

        Returns:
            True if environment is valid, False otherwise
        """
        if not self._validated:
            self._log("Validating environment...")
            self._validation_result = self.environment.validate()
            self._validated = True

            if self._validation_result:
                self._log("Environment validation successful")
                if self.verbose:
                    self.environment.print_environment_summary()
            else:
                self._log("Environment validation failed", "ERROR")
                for error in self.environment.get_validation_errors():
                    self._log(f"  - {error}", "ERROR")

        return self._validation_result

    def get_environment_status(self) -> Dict:
        """
        Get detailed environment status for debugging.

        Returns:
            Dictionary with environment configuration and validation status
        """
        if not self._validated:
            self.validate_environment()

        config = self.environment.config
        if not config:
            return {"status": "failed", "error": "Environment detection failed"}

        return {
            "status": "valid" if config.is_valid else "invalid",
            "project_root": str(config.project_root),
            "venv_path": str(config.venv_path) if config.venv_path else None,
            "dbt_path": str(config.dbt_path),
            "python_executable": str(config.python_executable)
            if config.python_executable
            else None,
            "database_files": {
                name: str(path) for name, path in config.database_files.items()
            },
            "errors": config.errors,
            "validation_timestamp": datetime.now().isoformat(),
        }

    def dry_run(self, command_line: str) -> Dict:
        """
        Perform a dry run to show what would be executed.

        Args:
            command_line: Command to analyze

        Returns:
            Dictionary with execution plan details
        """
        self._log(f"Performing dry run for: {command_line}")

        if not self.validate_environment():
            return {
                "valid": False,
                "errors": self.environment.get_validation_errors(),
                "setup_instructions": self.environment.get_setup_instructions(),
            }

        command_type = self.environment.classify_command(command_line)
        context = self.environment.get_execution_context(command_type)

        # Prepare the actual command that would be executed
        cmd_parts = shlex.split(command_line)

        if context["requires_venv"] and context["executable"]:
            if cmd_parts[0] in ["python", "dbt", "dagster", "pytest"]:
                if cmd_parts[0] == "python":
                    cmd_parts[0] = str(context["executable"])
                else:
                    venv_bin = context["executable"].parent
                    cmd_parts[0] = str(venv_bin / cmd_parts[0])

        return {
            "valid": True,
            "original_command": command_line,
            "resolved_command": " ".join(cmd_parts),
            "command_type": command_type.value,
            "working_directory": str(context["working_dir"]),
            "environment_variables": context["environment_vars"],
            "requires_venv": context["requires_venv"],
            "executable": str(context["executable"]) if context["executable"] else None,
        }

    def execute(
        self,
        command_line: str,
        capture_output: bool = False,
        timeout: Optional[int] = None,
        check_returncode: bool = True,
    ) -> CommandResult:
        """
        Execute a command with intelligent environment setup.

        Args:
            command_line: Command to execute
            capture_output: Whether to capture stdout/stderr
            timeout: Command timeout in seconds
            check_returncode: Whether to treat non-zero return codes as failures

        Returns:
            CommandResult with execution details
        """
        start_time = datetime.now()
        self._log(f"Executing command: {command_line}")

        # Validate environment first
        if not self.validate_environment():
            return CommandResult(
                success=False,
                returncode=-1,
                error_message=f"Environment validation failed: {'; '.join(self.environment.get_validation_errors())}",
                command=command_line,
            )

        # Get execution context
        command_type = self.environment.classify_command(command_line)
        context = self.environment.get_execution_context(command_type)

        self._log(f"Command type: {command_type.value}")
        self._log(f"Working directory: {context['working_dir']}")
        if context["environment_vars"]:
            self._log(f"Environment variables: {context['environment_vars']}")

        # Prepare command with proper executable paths
        cmd_parts = shlex.split(command_line)
        original_command = cmd_parts[0]

        if context["requires_venv"] and context["executable"]:
            if cmd_parts[0] in [
                "python",
                "dbt",
                "dagster",
                "pytest",
                "pip",
            ]:
                if cmd_parts[0] == "python":
                    cmd_parts[0] = str(context["executable"])
                else:
                    # Use the virtual environment's bin directory
                    venv_bin = context["executable"].parent
                    tool_path = venv_bin / cmd_parts[0]
                    if tool_path.exists():
                        cmd_parts[0] = str(tool_path)
                    else:
                        self._log(f"Tool not found in venv: {tool_path}", "WARNING")

        resolved_command = " ".join(cmd_parts)
        self._log(f"Resolved command: {resolved_command}")

        # Set up environment
        env = os.environ.copy()
        env.update(context["environment_vars"])

        # Add virtual environment to PATH if using venv
        if context["requires_venv"] and context["executable"]:
            venv_bin = str(context["executable"].parent)
            current_path = env.get("PATH", "")
            env["PATH"] = f"{venv_bin}:{current_path}"

        try:
            # Execute the command
            self._log(f"Running in directory: {context['working_dir']}")

            process_kwargs = {"cwd": context["working_dir"], "env": env, "text": True}

            if capture_output:
                process_kwargs.update(
                    {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
                )

            if timeout:
                process_kwargs["timeout"] = timeout

            result = subprocess.run(cmd_parts, **process_kwargs)

            duration = (datetime.now() - start_time).total_seconds()
            self._log(
                f"Command completed in {duration:.2f}s with return code {result.returncode}"
            )

            success = result.returncode == 0 if check_returncode else True

            return CommandResult(
                success=success,
                returncode=result.returncode,
                stdout=result.stdout if capture_output else None,
                stderr=result.stderr if capture_output else None,
                error_message=None
                if success
                else f"Command failed with return code {result.returncode}",
                command=resolved_command,
                working_dir=context["working_dir"],
                duration_seconds=duration,
                environment_setup={
                    "command_type": command_type.value,
                    "working_dir": str(context["working_dir"]),
                    "environment_vars": context["environment_vars"],
                    "requires_venv": context["requires_venv"],
                },
            )

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return CommandResult(
                success=False,
                returncode=-1,
                error_message=f"Command timed out after {timeout} seconds",
                command=resolved_command,
                working_dir=context["working_dir"],
                duration_seconds=duration,
            )

        except FileNotFoundError as e:
            return CommandResult(
                success=False,
                returncode=-1,
                error_message=f"Command not found: {original_command}. Error: {e}",
                command=command_line,
                working_dir=context["working_dir"],
            )

        except Exception as e:
            return CommandResult(
                success=False,
                returncode=-1,
                error_message=f"Unexpected error executing command: {e}",
                command=command_line,
                working_dir=context["working_dir"],
            )

    def execute_sequence(
        self,
        commands: List[str],
        stop_on_failure: bool = True,
        capture_output: bool = False,
    ) -> List[CommandResult]:
        """
        Execute a sequence of commands with proper environment setup.

        Args:
            commands: List of commands to execute
            stop_on_failure: Whether to stop if a command fails
            capture_output: Whether to capture command output

        Returns:
            List of CommandResult objects
        """
        self._log(f"Executing command sequence: {len(commands)} commands")
        results = []

        for i, command in enumerate(commands, 1):
            self._log(f"Command {i}/{len(commands)}: {command}")
            result = self.execute(command, capture_output=capture_output)
            results.append(result)

            if not result.success and stop_on_failure:
                self._log(
                    f"Stopping sequence due to failure: {result.error_message}", "ERROR"
                )
                break

        successful = sum(1 for r in results if r.success)
        self._log(f"Command sequence completed: {successful}/{len(results)} successful")

        return results

    def get_setup_help(self) -> str:
        """
        Get help text for setting up the environment.

        Returns:
            Formatted help text with setup instructions
        """
        if not self._validated:
            self.validate_environment()

        help_text = ["🔧 Fidelity PlanAlign Engine Environment Setup Help", "=" * 50]

        if self._validation_result:
            help_text.extend(
                [
                    "✅ Your environment is properly configured!",
                    "",
                    "Available commands:",
                    "  • dbt run                    # Run dbt models",
                    "  • dagster dev               # Start Dagster development server",
                    "  • python script.py         # Run Python scripts",
                    "  • pytest tests/            # Run tests",
                    "",
                    "All commands will automatically use the correct:",
                    "  - Working directory (project root or dbt/)",
                    "  - Virtual environment activation",
                    "  - Environment variables (DAGSTER_HOME, etc.)",
                ]
            )
        else:
            help_text.extend(["❌ Environment setup required. Issues found:", ""])

            for error in self.environment.get_validation_errors():
                help_text.append(f"   - {error}")

            help_text.extend(["", "🛠️ Setup Instructions:", ""])

            for instruction in self.environment.get_setup_instructions():
                help_text.append(f"   {instruction}")

            help_text.extend(
                ["", "After setup, run this script again to validate the environment."]
            )

        return "\n".join(help_text)


def main():
    """Command-line interface for the smart command wrapper."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart command wrapper for Fidelity PlanAlign Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "dbt run"                    # Run dbt with proper environment
  %(prog)s "dagster dev"                # Start Dagster development server
  %(prog)s --dry-run "python main.py"   # Show what would be executed
  %(prog)s --validate                   # Check environment setup
  %(prog)s --help-setup                 # Show setup instructions
        """,
    )

    parser.add_argument("command", nargs="?", help="Command to execute")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show execution plan without running"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Validate environment and exit"
    )
    parser.add_argument(
        "--help-setup", action="store_true", help="Show environment setup help"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--capture-output",
        action="store_true",
        help="Capture and display command output",
    )
    parser.add_argument("--timeout", type=int, help="Command timeout in seconds")
    parser.add_argument(
        "--working-dir", help="Override working directory for environment detection"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    # Handle special modes
    if not args.command and not args.validate and not args.help_setup:
        parser.print_help()
        sys.exit(1)

    # Initialize wrapper
    working_dir = Path(args.working_dir) if args.working_dir else None
    wrapper = SmartCommandWrapper(working_dir=working_dir, verbose=args.verbose)

    if args.help_setup:
        print(wrapper.get_setup_help())
        sys.exit(0)

    if args.validate:
        if wrapper.validate_environment():
            if args.json:
                print(json.dumps(wrapper.get_environment_status(), indent=2))
            else:
                print("✅ Environment validation successful")
                if args.verbose:
                    wrapper.environment.print_environment_summary()
            sys.exit(0)
        else:
            if args.json:
                print(json.dumps(wrapper.get_environment_status(), indent=2))
            else:
                print("❌ Environment validation failed")
                for error in wrapper.environment.get_validation_errors():
                    print(f"   - {error}")
                print("\nRun with --help-setup for setup instructions")
            sys.exit(1)

    if args.dry_run:
        plan = wrapper.dry_run(args.command)
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            if plan["valid"]:
                print("🔍 Execution Plan:")
                print(f"   Command: {plan['original_command']}")
                print(f"   Resolved: {plan['resolved_command']}")
                print(f"   Type: {plan['command_type']}")
                print(f"   Working Dir: {plan['working_directory']}")
                if plan["environment_variables"]:
                    print(f"   Environment: {plan['environment_variables']}")
                print(f"   Requires venv: {plan['requires_venv']}")
            else:
                print("❌ Cannot execute command due to environment issues:")
                for error in plan["errors"]:
                    print(f"   - {error}")
        sys.exit(0)

    # Execute command
    result = wrapper.execute(
        args.command, capture_output=args.capture_output, timeout=args.timeout
    )

    if args.json:
        # Convert result to JSON-serializable format
        result_dict = {
            "success": result.success,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error_message": result.error_message,
            "command": result.command,
            "working_dir": str(result.working_dir) if result.working_dir else None,
            "duration_seconds": result.duration_seconds,
            "environment_setup": result.environment_setup,
        }
        print(json.dumps(result_dict, indent=2))
    else:
        if result.success:
            print(f"✅ Command completed successfully (exit code: {result.returncode})")
            if result.duration_seconds:
                print(f"   Duration: {result.duration_seconds:.2f}s")
        else:
            print(f"❌ Command failed: {result.error_message}")
            if args.verbose and result.stderr:
                print("stderr:", result.stderr)

        if args.capture_output and result.stdout:
            print("\nOutput:")
            print(result.stdout)

    sys.exit(result.returncode if result.returncode is not None else 1)


if __name__ == "__main__":
    main()
