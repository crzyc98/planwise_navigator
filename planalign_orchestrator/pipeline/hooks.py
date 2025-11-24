#!/usr/bin/env python3
"""
Pipeline Hooks Module

Provides a flexible hook system for injecting custom behavior at various points in the
pipeline execution lifecycle. Supports pre/post hooks for simulation, year, and stage
events with proper error isolation and stage filtering.

This module enables extension of pipeline behavior without modifying core orchestration
logic, supporting use cases like custom logging, monitoring, validation, and cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List

from planalign_orchestrator.pipeline.workflow import WorkflowStage


class HookType(Enum):
    """Types of hooks that can be registered in the pipeline lifecycle.

    Hook types define the execution points where custom callbacks can be injected:
    - PRE_SIMULATION: Before entire multi-year simulation begins
    - POST_SIMULATION: After entire multi-year simulation completes
    - PRE_YEAR: Before processing each simulation year
    - POST_YEAR: After completing each simulation year
    - PRE_STAGE: Before executing each workflow stage
    - POST_STAGE: After completing each workflow stage
    """
    PRE_SIMULATION = "pre_simulation"
    POST_SIMULATION = "post_simulation"
    PRE_YEAR = "pre_year"
    POST_YEAR = "post_year"
    PRE_STAGE = "pre_stage"
    POST_STAGE = "post_stage"


@dataclass
class Hook:
    """Hook definition with callable and metadata.

    Attributes:
        hook_type: The type of hook determining when it executes
        callback: Function to execute with context dictionary as argument
        stage_filter: Optional workflow stage filter (only for PRE_STAGE/POST_STAGE hooks)
        name: Descriptive name for logging and debugging

    Notes:
        - Callbacks receive a context dictionary with execution state
        - Callbacks should handle their own errors to avoid breaking pipeline
        - stage_filter is only used for PRE_STAGE/POST_STAGE hooks
    """
    hook_type: HookType
    callback: Callable[[Dict[str, Any]], None]
    stage_filter: WorkflowStage | None = None
    name: str = "unnamed_hook"

    def __post_init__(self):
        """Validate hook configuration after initialization."""
        # Validate stage_filter is only used with stage hooks
        if self.stage_filter is not None:
            if self.hook_type not in (HookType.PRE_STAGE, HookType.POST_STAGE):
                raise ValueError(
                    f"stage_filter can only be used with PRE_STAGE/POST_STAGE hooks, "
                    f"got {self.hook_type}"
                )


class HookManager:
    """Manages registration and execution of pipeline hooks.

    Provides centralized hook management with:
    - Type-safe hook registration and validation
    - Error isolation to prevent hook failures from breaking pipeline
    - Stage filtering for targeted hook execution
    - Comprehensive logging for debugging and monitoring

    Example:
        >>> manager = HookManager(verbose=True)
        >>> def log_year(ctx: Dict[str, Any]) -> None:
        ...     print(f"Processing year {ctx['year']}")
        >>> hook = Hook(
        ...     hook_type=HookType.PRE_YEAR,
        ...     callback=log_year,
        ...     name="year_logger"
        ... )
        >>> manager.register_hook(hook)
        >>> manager.execute_hooks(HookType.PRE_YEAR, {"year": 2025})
    """

    def __init__(self, verbose: bool = False):
        """Initialize HookManager with empty hook registry.

        Args:
            verbose: Enable verbose logging for hook execution
        """
        self.verbose = verbose
        self._hooks: Dict[HookType, List[Hook]] = {
            hook_type: [] for hook_type in HookType
        }

    def register_hook(self, hook: Hook) -> None:
        """Register a hook for execution at specified lifecycle point.

        Args:
            hook: Hook instance to register

        Notes:
            - Hooks are executed in registration order
            - Multiple hooks can be registered for the same hook type
            - Hook validation occurs during Hook initialization
        """
        self._hooks[hook.hook_type].append(hook)
        if self.verbose:
            stage_info = f" [stage={hook.stage_filter.value}]" if hook.stage_filter else ""
            print(f"📌 Registered hook: {hook.name} ({hook.hook_type.value}){stage_info}")

    def execute_hooks(
        self,
        hook_type: HookType,
        context: Dict[str, Any]
    ) -> None:
        """Execute all hooks of a given type with error isolation.

        Args:
            hook_type: Type of hooks to execute
            context: Execution context dictionary passed to hook callbacks

        Notes:
            - Hooks are executed in registration order
            - Stage-filtered hooks only execute for matching stages
            - Hook errors are caught and logged but don't break pipeline
            - Context dictionary typically includes: year, stage, metrics, etc.
        """
        hooks = self._hooks[hook_type]
        if not hooks:
            return

        # Filter hooks by stage if applicable
        current_stage = context.get("stage")
        applicable_hooks = [
            h for h in hooks
            if h.stage_filter is None or h.stage_filter == current_stage
        ]

        if not applicable_hooks:
            return

        if self.verbose:
            stage_info = f" [stage={current_stage.value}]" if current_stage else ""
            print(f"🔗 Executing {len(applicable_hooks)} hook(s): {hook_type.value}{stage_info}")

        for hook in applicable_hooks:
            try:
                if self.verbose:
                    print(f"  ▶ Running hook: {hook.name}")
                hook.callback(context)
            except Exception as e:
                # Error isolation: Log error but continue pipeline execution
                error_msg = f"❌ Hook '{hook.name}' failed: {e}"
                print(error_msg)
                if self.verbose:
                    import traceback
                    traceback.print_exc()

    def clear_hooks(self, hook_type: HookType | None = None) -> None:
        """Clear registered hooks for specified type or all hooks.

        Args:
            hook_type: Specific hook type to clear, or None to clear all hooks

        Notes:
            - Useful for test cleanup and dynamic hook management
            - Clearing all hooks resets manager to initial state
        """
        if hook_type is None:
            # Clear all hooks
            for ht in HookType:
                self._hooks[ht] = []
            if self.verbose:
                print("🧹 Cleared all hooks")
        else:
            self._hooks[hook_type] = []
            if self.verbose:
                print(f"🧹 Cleared hooks: {hook_type.value}")

    def get_hook_count(self, hook_type: HookType) -> int:
        """Get count of registered hooks for a specific type.

        Args:
            hook_type: Type of hooks to count

        Returns:
            Number of registered hooks for specified type
        """
        return len(self._hooks[hook_type])

    def list_hooks(self) -> Dict[str, List[str]]:
        """Get a summary of all registered hooks by type.

        Returns:
            Dictionary mapping hook type names to lists of hook names

        Example:
            >>> manager.list_hooks()
            {
                'pre_simulation': ['setup_hook'],
                'pre_year': ['year_logger', 'year_validator'],
                'post_stage': ['stage_metrics']
            }
        """
        return {
            hook_type.value: [h.name for h in hooks]
            for hook_type, hooks in self._hooks.items()
            if hooks
        }
