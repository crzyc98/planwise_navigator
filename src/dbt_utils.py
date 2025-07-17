"""
dbt Command Execution and Project Management Utilities

This module provides centralized utilities for executing dbt commands with
standardized error handling, logging, and configuration management. It abstracts
the complexity of dbt command construction and provides both synchronous and
streaming execution patterns.

Functions:
    execute_dbt_command: Execute dbt commands with standardized error handling
    execute_dbt_command_streaming: Execute dbt commands with streaming output
"""

from typing import Dict, List, Any
from dagster import OpExecutionContext


def execute_dbt_command(
    context: OpExecutionContext,
    command: List[str],
    vars_dict: Dict[str, Any],
    full_refresh: bool = False,
    description: str = "",
) -> None:
    """
    Execute a dbt command with standardized error handling and logging.

    This utility centralizes dbt command execution patterns used throughout
    the simulation pipeline. It handles variable string construction,
    full_refresh flag addition, and provides consistent error reporting.

    Args:
        context: Dagster operation execution context
        command: Base dbt command as list (e.g., ["run", "--select", "model_name"])
        vars_dict: Variables to pass to dbt as --vars (e.g., {"simulation_year": 2025})
        full_refresh: Whether to add --full-refresh flag to command
        description: Human-readable description for logging and error messages

    Raises:
        Exception: When dbt command fails with details from stdout/stderr

    Examples:
        Basic model run:
        >>> execute_dbt_command(context, ["run", "--select", "my_model"], {}, False, "my model")

        With variables and full refresh:
        >>> execute_dbt_command(
        ...     context,
        ...     ["run", "--select", "int_hiring_events"],
        ...     {"simulation_year": 2025, "random_seed": 42},
        ...     True,
        ...     "hiring events for 2025"
        ... )

        Snapshot execution:
        >>> execute_dbt_command(
        ...     context,
        ...     ["snapshot", "--select", "scd_workforce_state"],
        ...     {"simulation_year": 2025},
        ...     False,
        ...     "workforce state snapshot"
        ... )
    """
    # Build command with variables
    full_command = command.copy()

    if vars_dict:
        vars_string = "{" + ", ".join([f"{k}: {v}" for k, v in vars_dict.items()]) + "}"
        full_command.extend(["--vars", vars_string])

    if full_refresh:
        full_command.append("--full-refresh")

    # Log execution start
    context.log.info(f"Executing: dbt {' '.join(full_command)}")
    if description:
        context.log.info(f"Description: {description}")

    # Execute command
    dbt = context.resources.dbt
    invocation = dbt.cli(full_command, context=context).wait()

    # Handle errors with standardized format
    if invocation.process is None or invocation.process.returncode != 0:
        stdout = invocation.get_stdout() or ""
        stderr = invocation.get_stderr() or ""

        error_msg = f"Failed to run {' '.join(command)}"
        if description:
            error_msg += f" for {description}"
        error_msg += f". Exit code: {invocation.process.returncode if invocation.process else 'N/A'}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

        context.log.error(error_msg)
        raise Exception(error_msg)

    context.log.info(f"Successfully completed: dbt {' '.join(command)}")


def execute_dbt_command_streaming(
    context: OpExecutionContext,
    command: List[str],
    vars_dict: Dict[str, Any] = None,
    full_refresh: bool = False,
    description: str = "",
):
    """
    Execute a dbt command with streaming output and standardized error handling.

    This utility provides streaming execution for dbt commands, particularly useful
    for long-running operations like full builds. It maintains the same interface
    as execute_dbt_command but yields results as they become available.

    Args:
        context: Dagster operation execution context
        command: Base dbt command as list (e.g., ["build"])
        vars_dict: Variables to pass to dbt as --vars (optional)
        full_refresh: Whether to add --full-refresh flag to command
        description: Human-readable description for logging and error messages

    Yields:
        Results from dbt command execution as they become available

    Examples:
        Basic build with streaming:
        >>> yield from execute_dbt_command_streaming(context, ["build"], {}, False, "full dbt build")

        With variables:
        >>> yield from execute_dbt_command_streaming(
        ...     context,
        ...     ["run", "--select", "model_name"],
        ...     {"simulation_year": 2025},
        ...     False,
        ...     "model execution with streaming"
        ... )
    """
    # Build command with variables
    full_command = command.copy()

    if vars_dict:
        vars_string = "{" + ", ".join([f"{k}: {v}" for k, v in vars_dict.items()]) + "}"
        full_command.extend(["--vars", vars_string])

    if full_refresh:
        full_command.append("--full-refresh")

    # Log execution start
    context.log.info(f"Executing (streaming): dbt {' '.join(full_command)}")
    if description:
        context.log.info(f"Description: {description}")

    # Execute command with streaming
    dbt = context.resources.dbt
    try:
        yield from dbt.cli(full_command, context=context).stream()
        context.log.info(f"Successfully completed (streaming): dbt {' '.join(command)}")
    except Exception as e:
        error_msg = f"Failed to run {' '.join(command)}"
        if description:
            error_msg += f" for {description}"
        error_msg += f". Error: {str(e)}"

        context.log.error(error_msg)
        raise Exception(error_msg) from e
