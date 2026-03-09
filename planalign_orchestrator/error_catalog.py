"""
Error catalog with resolution patterns for common production issues.

Provides:
- Pattern matching for known error signatures
- Automated resolution suggestions
- Error frequency tracking
- Self-service diagnostic tools
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern
import re

from .exceptions import NavigatorError, ResolutionHint, ErrorCategory


@dataclass
class ErrorPattern:
    """Pattern for identifying and resolving known errors"""

    pattern: Pattern[str]
    category: ErrorCategory
    title: str
    description: str
    resolution_hints: List[ResolutionHint]
    frequency: int = 0  # Track how often this pattern matches

    def matches(self, error_message: str) -> bool:
        """Check if error message matches this pattern"""
        return self.pattern.search(error_message) is not None


class ErrorCatalog:
    """
    Central repository of known error patterns and resolutions.

    Usage:
        catalog = ErrorCatalog()
        hints = catalog.find_resolution_hints("Conflicting lock is held")
        # Returns resolution steps for database lock issues
    """

    def __init__(self):
        self.patterns: List[ErrorPattern] = []
        self._initialize_patterns()

    def _initialize_patterns(self) -> None:
        """Initialize catalog with known error patterns."""
        pattern_definitions = [
            {
                "regex": r"(conflicting lock|database.*lock|cannot acquire lock|lock.*database)",
                "category": ErrorCategory.DATABASE,
                "title": "Database Lock Conflict",
                "description": "Another process has locked the database",
                "hint_title": "Close IDE Database Connections",
                "hint_description": "DuckDB does not support concurrent write connections",
                "steps": [
                    "Close database explorer in VS Code/Windsurf/DataGrip",
                    "Check for other Python processes: ps aux | grep duckdb",
                    "Kill stale connections: pkill -f 'duckdb.*simulation.duckdb'",
                    "Retry simulation",
                ],
                "time": "1-2 minutes",
            },
            {
                "regex": r"(out of memory|memory exhausted|cannot allocate|memoryerror|unable to allocate)",
                "category": ErrorCategory.RESOURCE,
                "title": "Memory Exhaustion",
                "description": "Insufficient memory for current operation",
                "hint_title": "Reduce Memory Footprint",
                "hint_description": "Adjust configuration to reduce memory usage",
                "steps": [
                    "Set dbt threads to 1: orchestrator.threading.dbt_threads: 1",
                    "Enable adaptive memory: optimization.adaptive_memory.enabled: true",
                    "Reduce batch size: optimization.batch_size: 250",
                    "Use subset mode: --vars '{dev_employee_limit: 1000}'",
                ],
                "time": "10 minutes",
            },
            {
                "regex": r"(compilation error|syntax error|jinja.*error)",
                "category": ErrorCategory.CONFIGURATION,
                "title": "dbt Compilation Failure",
                "description": "Model contains syntax or Jinja template errors",
                "hint_title": "Debug Model Compilation",
                "hint_description": "Identify and fix SQL/Jinja syntax errors",
                "steps": [
                    "Review error message for line number and specific issue",
                    "Test compilation: dbt compile --select <model>",
                    "Check for missing CTEs or incorrect ref() calls",
                    "Verify dbt_vars: dbt compile --vars '{simulation_year: 2025}'",
                ],
                "time": "15 minutes",
            },
            {
                "regex": r"(depends on.*not found|upstream model.*missing|upstream model.*not found|no model named)",
                "category": ErrorCategory.DEPENDENCY,
                "title": "Missing Model Dependency",
                "description": "Required upstream model not found",
                "hint_title": "Verify Model Dependencies",
                "hint_description": "Ensure all upstream models exist and are selected",
                "steps": [
                    "Check dbt lineage: dbt docs generate && dbt docs serve",
                    "Verify model exists: ls dbt/models/**/<model>.sql",
                    "Run full build: dbt build --full-refresh",
                    "Check model selection syntax: dbt run --select +<model>",
                ],
                "time": "10 minutes",
            },
            {
                "regex": r"(test failed|failing tests|failure in test|data quality|validation.*failed)",
                "category": ErrorCategory.DATA_QUALITY,
                "title": "Data Quality Test Failure",
                "description": "One or more data quality tests failed",
                "hint_title": "Investigate Test Failures",
                "hint_description": "Review failed tests and affected data",
                "steps": [
                    "View test results: dbt test --select <model>",
                    "Query failed records: SELECT * FROM <model> WHERE ...",
                    "Check upstream data quality",
                    "Determine if failure is expected (e.g., new data pattern)",
                    "Adjust test thresholds if needed or fix data issue",
                ],
                "time": "20 minutes",
            },
            {
                "regex": r"(proxy.*error|SSL.*error|SSL.*certificate.*verif|certificate.*verif|connection.*timed out)",
                "category": ErrorCategory.NETWORK,
                "title": "Network Configuration Error",
                "description": "Network request failed due to proxy/SSL issues",
                "hint_title": "Configure Corporate Network",
                "hint_description": "Set up proxy and SSL certificates",
                "steps": [
                    "Check proxy settings: echo $HTTP_PROXY $HTTPS_PROXY",
                    "Test connection: curl -x $HTTP_PROXY https://example.com",
                    "Set CA bundle: export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt",
                    "Update network config: config/network_config.yaml",
                ],
                "time": "15 minutes",
            },
            {
                "regex": r"(checkpoint.*corrupt|checkpoint.*invalid|checkpoint.*version)",
                "category": ErrorCategory.STATE,
                "title": "Checkpoint Corruption",
                "description": "Checkpoint file is corrupted or incompatible",
                "hint_title": "Reset Checkpoint State",
                "hint_description": "Clean corrupted checkpoints and restart",
                "steps": [
                    "List checkpoints: planwise checkpoints list",
                    "Clean checkpoints: planwise checkpoints cleanup",
                    "Delete checkpoint dir: rm -rf .planalign_checkpoints/",
                    "Restart simulation without --resume flag",
                ],
                "time": "5 minutes",
            },
        ]

        for defn in pattern_definitions:
            self.patterns.append(ErrorPattern(
                pattern=re.compile(defn["regex"], re.IGNORECASE),
                category=defn["category"],
                title=defn["title"],
                description=defn["description"],
                resolution_hints=[
                    ResolutionHint(
                        title=defn["hint_title"],
                        description=defn["hint_description"],
                        steps=defn["steps"],
                        estimated_resolution_time=defn["time"],
                    )
                ],
            ))

    def find_resolution_hints(self, error_message: str) -> List[ResolutionHint]:
        """
        Find resolution hints for given error message.

        Returns list of resolution hints from matching patterns.
        Updates frequency counter for matched patterns.
        """
        hints = []
        for pattern in self.patterns:
            if pattern.matches(error_message):
                pattern.frequency += 1
                hints.extend(pattern.resolution_hints)
        return hints

    def get_pattern_statistics(self) -> Dict[str, int]:
        """Get error pattern frequency statistics"""
        return {
            pattern.title: pattern.frequency
            for pattern in sorted(self.patterns, key=lambda p: p.frequency, reverse=True)
        }

    def add_pattern(self, pattern: ErrorPattern) -> None:
        """Add custom error pattern to catalog"""
        self.patterns.append(pattern)


# Global error catalog instance
_global_catalog: Optional[ErrorCatalog] = None


def get_error_catalog() -> ErrorCatalog:
    """Get global error catalog instance (singleton)"""
    global _global_catalog
    if _global_catalog is None:
        _global_catalog = ErrorCatalog()
    return _global_catalog
