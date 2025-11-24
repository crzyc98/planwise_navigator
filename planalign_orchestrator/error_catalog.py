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
        """Initialize catalog with known error patterns"""

        # Database lock errors
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(conflicting lock|database.*lock|cannot acquire lock|lock.*database)", re.IGNORECASE),
            category=ErrorCategory.DATABASE,
            title="Database Lock Conflict",
            description="Another process has locked the database",
            resolution_hints=[
                ResolutionHint(
                    title="Close IDE Database Connections",
                    description="DuckDB does not support concurrent write connections",
                    steps=[
                        "Close database explorer in VS Code/Windsurf/DataGrip",
                        "Check for other Python processes: ps aux | grep duckdb",
                        "Kill stale connections: pkill -f 'duckdb.*simulation.duckdb'",
                        "Retry simulation"
                    ],
                    estimated_resolution_time="1-2 minutes"
                )
            ]
        ))

        # Memory errors
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(out of memory|memory exhausted|cannot allocate|memoryerror|unable to allocate)", re.IGNORECASE),
            category=ErrorCategory.RESOURCE,
            title="Memory Exhaustion",
            description="Insufficient memory for current operation",
            resolution_hints=[
                ResolutionHint(
                    title="Reduce Memory Footprint",
                    description="Adjust configuration to reduce memory usage",
                    steps=[
                        "Set dbt threads to 1: orchestrator.threading.dbt_threads: 1",
                        "Enable adaptive memory: optimization.adaptive_memory.enabled: true",
                        "Reduce batch size: optimization.batch_size: 250",
                        "Use subset mode: --vars '{dev_employee_limit: 1000}'"
                    ],
                    estimated_resolution_time="10 minutes"
                )
            ]
        ))

        # Compilation errors
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(compilation error|syntax error|jinja.*error)", re.IGNORECASE),
            category=ErrorCategory.CONFIGURATION,
            title="dbt Compilation Failure",
            description="Model contains syntax or Jinja template errors",
            resolution_hints=[
                ResolutionHint(
                    title="Debug Model Compilation",
                    description="Identify and fix SQL/Jinja syntax errors",
                    steps=[
                        "Review error message for line number and specific issue",
                        "Test compilation: dbt compile --select <model>",
                        "Check for missing CTEs or incorrect ref() calls",
                        "Verify dbt_vars: dbt compile --vars '{simulation_year: 2025}'"
                    ],
                    estimated_resolution_time="15 minutes"
                )
            ]
        ))

        # Missing dependency errors
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(depends on.*not found|upstream model.*missing|upstream model.*not found|no model named)", re.IGNORECASE),
            category=ErrorCategory.DEPENDENCY,
            title="Missing Model Dependency",
            description="Required upstream model not found",
            resolution_hints=[
                ResolutionHint(
                    title="Verify Model Dependencies",
                    description="Ensure all upstream models exist and are selected",
                    steps=[
                        "Check dbt lineage: dbt docs generate && dbt docs serve",
                        "Verify model exists: ls dbt/models/**/<model>.sql",
                        "Run full build: dbt build --full-refresh",
                        "Check model selection syntax: dbt run --select +<model>"
                    ],
                    estimated_resolution_time="10 minutes"
                )
            ]
        ))

        # Data quality test failures
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(test failed|failing tests|failure in test|data quality|validation.*failed)", re.IGNORECASE),
            category=ErrorCategory.DATA_QUALITY,
            title="Data Quality Test Failure",
            description="One or more data quality tests failed",
            resolution_hints=[
                ResolutionHint(
                    title="Investigate Test Failures",
                    description="Review failed tests and affected data",
                    steps=[
                        "View test results: dbt test --select <model>",
                        "Query failed records: SELECT * FROM <model> WHERE ...",
                        "Check upstream data quality",
                        "Determine if failure is expected (e.g., new data pattern)",
                        "Adjust test thresholds if needed or fix data issue"
                    ],
                    estimated_resolution_time="20 minutes"
                )
            ]
        ))

        # Network/proxy errors
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(proxy.*error|SSL.*error|SSL.*certificate.*verif|certificate.*verif|connection.*timed out)", re.IGNORECASE),
            category=ErrorCategory.NETWORK,
            title="Network Configuration Error",
            description="Network request failed due to proxy/SSL issues",
            resolution_hints=[
                ResolutionHint(
                    title="Configure Corporate Network",
                    description="Set up proxy and SSL certificates",
                    steps=[
                        "Check proxy settings: echo $HTTP_PROXY $HTTPS_PROXY",
                        "Test connection: curl -x $HTTP_PROXY https://example.com",
                        "Set CA bundle: export REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt",
                        "Update network config: config/network_config.yaml"
                    ],
                    estimated_resolution_time="15 minutes"
                )
            ]
        ))

        # Checkpoint errors
        self.patterns.append(ErrorPattern(
            pattern=re.compile(r"(checkpoint.*corrupt|checkpoint.*invalid|checkpoint.*version)", re.IGNORECASE),
            category=ErrorCategory.STATE,
            title="Checkpoint Corruption",
            description="Checkpoint file is corrupted or incompatible",
            resolution_hints=[
                ResolutionHint(
                    title="Reset Checkpoint State",
                    description="Clean corrupted checkpoints and restart",
                    steps=[
                        "List checkpoints: planwise checkpoints list",
                        "Clean checkpoints: planwise checkpoints cleanup",
                        "Delete checkpoint dir: rm -rf .navigator_checkpoints/",
                        "Restart simulation without --resume flag"
                    ],
                    estimated_resolution_time="5 minutes"
                )
            ]
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
