"""
Event Registry - Centralized Event Type Registration

This module provides the EventRegistry class for registering and looking up
event generators. It implements a singleton pattern to ensure consistent
state across the application.

Usage:
    from planalign_orchestrator.generators import EventRegistry, EventGenerator

    # Register via decorator
    @EventRegistry.register("my_event")
    class MyEventGenerator(EventGenerator):
        event_type = "my_event"
        execution_order = 50
        ...

    # Lookup
    generator = EventRegistry.get("my_event")
    all_types = EventRegistry.list_all()

    # Scenario-specific disable
    EventRegistry.disable("sabbatical", scenario_id="baseline")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Dict, List, Set, Type

if TYPE_CHECKING:
    from planalign_orchestrator.generators.base import EventGenerator

logger = logging.getLogger(__name__)


class EventRegistry:
    """
    Centralized registration and lookup for event generators.

    Singleton pattern ensures consistent state across the application.
    All event generators must be registered here to be included in
    simulation event generation.

    Class Attributes:
        _generators: Map of event_type to generator class
        _instances: Cached generator instances (lazy-loaded)
        _disabled: Map of scenario_id to set of disabled event_types

    Thread Safety:
        Not thread-safe. Designed for single-threaded orchestration.
        Registration should happen at import time, before execution.
    """

    _generators: Dict[str, Type["EventGenerator"]] = {}
    _instances: Dict[str, "EventGenerator"] = {}
    _disabled: Dict[str, Set[str]] = {}  # scenario_id -> disabled event_types

    @classmethod
    def register(
        cls, event_type: str
    ) -> Callable[[Type["EventGenerator"]], Type["EventGenerator"]]:
        """
        Decorator to register an event generator class.

        Args:
            event_type: Unique event type identifier. Must:
                - Start with a lowercase letter
                - Contain only lowercase letters, numbers, underscores
                - Not already be registered

        Returns:
            Decorator function that registers the class

        Raises:
            ValueError: If event_type already registered or invalid format

        Example:
            @EventRegistry.register("sabbatical")
            class SabbaticalEventGenerator(EventGenerator):
                event_type = "sabbatical"
                execution_order = 35
                ...
        """

        def decorator(
            generator_class: Type["EventGenerator"],
        ) -> Type["EventGenerator"]:
            # Validate event_type format
            if not event_type:
                raise ValueError("Event type cannot be empty")

            if not event_type[0].islower():
                raise ValueError(
                    f"Event type must start with lowercase letter: '{event_type}'"
                )

            # Check for duplicate registration
            if event_type in cls._generators:
                existing = cls._generators[event_type].__name__
                raise ValueError(
                    f"Event type '{event_type}' already registered by {existing}. "
                    f"Cannot register {generator_class.__name__}."
                )

            # Register the generator class
            cls._generators[event_type] = generator_class
            logger.debug(f"Registered event generator: {event_type} -> {generator_class.__name__}")

            return generator_class

        return decorator

    @classmethod
    def get(cls, event_type: str) -> "EventGenerator":
        """
        Get generator instance by event type.

        Instances are cached after first creation. Returns the same
        instance for subsequent calls with the same event_type.

        Args:
            event_type: Event type identifier

        Returns:
            EventGenerator instance (cached)

        Raises:
            KeyError: If event type not registered (FR-007)
        """
        if event_type not in cls._generators:
            available = ", ".join(sorted(cls._generators.keys())) or "(none)"
            raise KeyError(
                f"Event type '{event_type}' not registered. "
                f"Available event types: [{available}]. "
                f"Did you forget to import the generator module or use @EventRegistry.register()?"
            )

        # Lazy instantiation with caching
        if event_type not in cls._instances:
            cls._instances[event_type] = cls._generators[event_type]()

        return cls._instances[event_type]

    @classmethod
    def get_class(cls, event_type: str) -> Type["EventGenerator"]:
        """
        Get generator class (not instance) by event type.

        Useful when you need to inspect class attributes without
        instantiating the generator.

        Args:
            event_type: Event type identifier

        Returns:
            EventGenerator class

        Raises:
            KeyError: If event type not registered
        """
        if event_type not in cls._generators:
            available = ", ".join(sorted(cls._generators.keys())) or "(none)"
            raise KeyError(
                f"Event type '{event_type}' not registered. "
                f"Available event types: [{available}]."
            )
        return cls._generators[event_type]

    @classmethod
    def list_all(cls) -> List[str]:
        """
        List all registered event types.

        Returns:
            Sorted list of event type strings
        """
        return sorted(cls._generators.keys())

    @classmethod
    def list_enabled(cls, scenario_id: str) -> List[str]:
        """
        List event types enabled for a specific scenario.

        Excludes any event types that have been disabled for the
        given scenario_id.

        Args:
            scenario_id: Scenario identifier

        Returns:
            Sorted list of enabled event type strings
        """
        disabled = cls._disabled.get(scenario_id, set())
        return sorted(et for et in cls._generators.keys() if et not in disabled)

    @classmethod
    def list_ordered(cls, scenario_id: str) -> List["EventGenerator"]:
        """
        Get enabled generators ordered by execution_order.

        Returns instantiated generators sorted by their execution_order
        attribute. Lower execution_order runs first.

        Args:
            scenario_id: Scenario identifier

        Returns:
            List of EventGenerator instances sorted by execution_order
        """
        enabled = cls.list_enabled(scenario_id)
        generators = [cls.get(et) for et in enabled]
        return sorted(generators, key=lambda g: g.execution_order)

    @classmethod
    def disable(cls, event_type: str, scenario_id: str) -> None:
        """
        Disable an event type for a specific scenario.

        Disabled event types will not be included in list_enabled()
        or list_ordered() for the specified scenario.

        Args:
            event_type: Event type to disable
            scenario_id: Scenario for which to disable

        Note:
            Does not validate that event_type is registered.
            Silently creates disable entry for future registration.
        """
        if scenario_id not in cls._disabled:
            cls._disabled[scenario_id] = set()
        cls._disabled[scenario_id].add(event_type)
        logger.info(f"Disabled event type '{event_type}' for scenario '{scenario_id}'")

    @classmethod
    def enable(cls, event_type: str, scenario_id: str) -> None:
        """
        Enable an event type for a specific scenario.

        Removes a previous disable() call. If the event type was not
        disabled, this is a no-op.

        Args:
            event_type: Event type to enable
            scenario_id: Scenario for which to enable
        """
        if scenario_id in cls._disabled:
            cls._disabled[scenario_id].discard(event_type)
            logger.info(f"Enabled event type '{event_type}' for scenario '{scenario_id}'")

    @classmethod
    def is_enabled(cls, event_type: str, scenario_id: str) -> bool:
        """
        Check if an event type is enabled for a scenario.

        Args:
            event_type: Event type to check
            scenario_id: Scenario identifier

        Returns:
            True if event type is registered and not disabled
        """
        if event_type not in cls._generators:
            return False
        disabled = cls._disabled.get(scenario_id, set())
        return event_type not in disabled

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registrations and cached instances.

        Primarily used for testing to reset registry state between tests.
        Should NOT be called in production code.
        """
        cls._generators.clear()
        cls._instances.clear()
        cls._disabled.clear()
        logger.debug("EventRegistry cleared")

    @classmethod
    def clear_instances(cls) -> None:
        """
        Clear cached instances without clearing registrations.

        Useful when you need fresh generator instances but want to
        keep registrations intact.
        """
        cls._instances.clear()

    @classmethod
    def count(cls) -> int:
        """Return the number of registered event types."""
        return len(cls._generators)

    @classmethod
    def list_by_mode(cls, mode: str, scenario_id: str) -> List["EventGenerator"]:
        """
        List enabled generators that support a specific execution mode.

        Args:
            mode: "sql" or "polars"
            scenario_id: Scenario identifier

        Returns:
            List of EventGenerator instances that support the mode,
            sorted by execution_order

        Example:
            sql_generators = EventRegistry.list_by_mode("sql", "baseline")
            polars_generators = EventRegistry.list_by_mode("polars", "baseline")
        """
        if mode not in ("sql", "polars"):
            raise ValueError(f"Invalid mode '{mode}'. Must be 'sql' or 'polars'")

        enabled = cls.list_enabled(scenario_id)
        generators = []

        for et in enabled:
            gen = cls.get(et)
            if mode == "sql" and gen.supports_sql:
                generators.append(gen)
            elif mode == "polars" and gen.supports_polars:
                generators.append(gen)

        return sorted(generators, key=lambda g: g.execution_order)

    @classmethod
    def summary(cls) -> str:
        """
        Return a summary string of registered generators.

        Useful for debugging and logging.

        Returns:
            Human-readable summary of registered generators
        """
        if not cls._generators:
            return "EventRegistry: No generators registered"

        lines = ["EventRegistry:"]
        for event_type in sorted(cls._generators.keys()):
            gen_class = cls._generators[event_type]
            order = getattr(gen_class, "execution_order", "?")
            sql = getattr(gen_class, "supports_sql", True)
            polars = getattr(gen_class, "supports_polars", False)
            modes = []
            if sql:
                modes.append("sql")
            if polars:
                modes.append("polars")
            mode_str = ",".join(modes) or "none"
            lines.append(f"  - {event_type} (order={order}, modes={mode_str}): {gen_class.__name__}")

        return "\n".join(lines)
