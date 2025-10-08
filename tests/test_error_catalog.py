"""
Unit tests for error catalog and resolution system (E074-02).

Tests pattern matching, resolution hint discovery, and frequency tracking.
"""

from __future__ import annotations

import re
import pytest
from navigator_orchestrator.error_catalog import (
    ErrorCatalog,
    ErrorPattern,
    get_error_catalog,
)
from navigator_orchestrator.exceptions import ResolutionHint, ErrorCategory


class TestErrorPattern:
    """Test ErrorPattern dataclass and matching"""

    def test_pattern_creation(self):
        """Test creating error pattern"""
        pattern = ErrorPattern(
            pattern=re.compile(r"database.*locked", re.IGNORECASE),
            category=ErrorCategory.DATABASE,
            title="Database Lock",
            description="Lock conflict detected",
            resolution_hints=[
                ResolutionHint(
                    title="Close Connections",
                    description="Close IDE connections",
                    steps=["Close VS Code"]
                )
            ]
        )

        assert pattern.category == ErrorCategory.DATABASE
        assert pattern.frequency == 0

    def test_pattern_matching_success(self):
        """Test successful pattern matching"""
        pattern = ErrorPattern(
            pattern=re.compile(r"database.*locked", re.IGNORECASE),
            category=ErrorCategory.DATABASE,
            title="Database Lock",
            description="Test",
            resolution_hints=[]
        )

        assert pattern.matches("Database is locked")
        assert pattern.matches("DATABASE IS LOCKED")
        assert pattern.matches("The database was locked by another process")

    def test_pattern_matching_failure(self):
        """Test pattern non-matching"""
        pattern = ErrorPattern(
            pattern=re.compile(r"out of memory", re.IGNORECASE),
            category=ErrorCategory.RESOURCE,
            title="Memory Error",
            description="Test",
            resolution_hints=[]
        )

        assert not pattern.matches("Database is locked")
        assert not pattern.matches("Compilation error")


class TestErrorCatalog:
    """Test ErrorCatalog initialization and pattern matching"""

    def test_catalog_initialization(self):
        """Test catalog initializes with default patterns"""
        catalog = ErrorCatalog()

        assert len(catalog.patterns) > 0
        assert all(isinstance(p, ErrorPattern) for p in catalog.patterns)

    def test_database_lock_pattern(self):
        """Test database lock error pattern matching"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Conflicting lock is held in database")

        assert len(hints) > 0
        assert any("Close IDE" in hint.title for hint in hints)

    def test_memory_exhaustion_pattern(self):
        """Test memory exhaustion pattern matching"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Out of memory error occurred")

        assert len(hints) > 0
        assert any("Memory" in hint.title for hint in hints)

    def test_compilation_error_pattern(self):
        """Test dbt compilation error pattern"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Compilation error in dbt model")

        assert len(hints) > 0
        assert any("Compilation" in hint.title or "Syntax" in hint.title for hint in hints)

    def test_dependency_error_pattern(self):
        """Test missing dependency error pattern"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Upstream model not found")

        assert len(hints) > 0
        assert any("Dependency" in hint.title or "Model" in hint.title for hint in hints)

    def test_data_quality_pattern(self):
        """Test data quality test failure pattern"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Data quality tests failed")

        assert len(hints) > 0
        assert any("Test" in hint.title or "Quality" in hint.title for hint in hints)

    def test_network_error_pattern(self):
        """Test network/proxy error pattern"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("SSL certificate verification failed")

        assert len(hints) > 0
        assert any("Network" in hint.title or "Proxy" in hint.title for hint in hints)

    def test_checkpoint_error_pattern(self):
        """Test checkpoint corruption pattern"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Checkpoint file is corrupted")

        assert len(hints) > 0
        assert any("Checkpoint" in hint.title for hint in hints)

    def test_no_match_returns_empty(self):
        """Test that unmatched errors return empty hints"""
        catalog = ErrorCatalog()

        hints = catalog.find_resolution_hints("Some completely unknown error xyz123")

        # Should return empty list for unknown errors
        assert hints == []

    def test_frequency_tracking(self):
        """Test error pattern frequency tracking"""
        catalog = ErrorCatalog()

        # Match database lock error multiple times
        catalog.find_resolution_hints("Database is locked")
        catalog.find_resolution_hints("Conflicting lock detected")
        catalog.find_resolution_hints("Cannot acquire database lock")

        # Check that frequency was tracked
        stats = catalog.get_pattern_statistics()
        assert "Database Lock Conflict" in stats
        assert stats["Database Lock Conflict"] == 3

    def test_multiple_pattern_matching(self):
        """Test that a single error can match multiple patterns"""
        catalog = ErrorCatalog()

        # Some error messages might match multiple patterns
        hints = catalog.find_resolution_hints("Database locked and out of memory")

        # Should get hints from both database and memory patterns
        assert len(hints) >= 2

    def test_add_custom_pattern(self):
        """Test adding custom error pattern"""
        catalog = ErrorCatalog()

        custom_pattern = ErrorPattern(
            pattern=re.compile(r"custom error type", re.IGNORECASE),
            category=ErrorCategory.CONFIGURATION,
            title="Custom Error",
            description="Custom error description",
            resolution_hints=[
                ResolutionHint(
                    title="Custom Fix",
                    description="Apply custom fix",
                    steps=["Step 1", "Step 2"]
                )
            ]
        )

        initial_count = len(catalog.patterns)
        catalog.add_pattern(custom_pattern)

        assert len(catalog.patterns) == initial_count + 1

        # Verify the custom pattern works
        hints = catalog.find_resolution_hints("Custom error type detected")
        assert len(hints) > 0
        assert any("Custom Fix" in hint.title for hint in hints)


class TestGlobalCatalog:
    """Test global error catalog singleton"""

    def test_get_global_catalog(self):
        """Test getting global catalog instance"""
        catalog1 = get_error_catalog()
        catalog2 = get_error_catalog()

        # Should return same instance
        assert catalog1 is catalog2

    def test_global_catalog_has_patterns(self):
        """Test global catalog is initialized with patterns"""
        catalog = get_error_catalog()

        assert len(catalog.patterns) > 0


class TestResolutionHintQuality:
    """Test quality and completeness of resolution hints"""

    def test_hints_have_steps(self):
        """Test that all resolution hints have actionable steps"""
        catalog = ErrorCatalog()

        for pattern in catalog.patterns:
            for hint in pattern.resolution_hints:
                assert len(hint.steps) > 0, f"Pattern {pattern.title} has hint without steps"

    def test_hints_have_descriptions(self):
        """Test that all hints have descriptions"""
        catalog = ErrorCatalog()

        for pattern in catalog.patterns:
            for hint in pattern.resolution_hints:
                assert hint.description, f"Pattern {pattern.title} has hint without description"
                assert len(hint.description) > 10, f"Pattern {pattern.title} has too short description"

    def test_hints_have_estimated_time(self):
        """Test that hints include estimated resolution time"""
        catalog = ErrorCatalog()

        for pattern in catalog.patterns:
            for hint in pattern.resolution_hints:
                assert hint.estimated_resolution_time, f"Pattern {pattern.title} missing time estimate"


class TestPatternCoverage:
    """Test that catalog covers major error categories"""

    def test_database_category_coverage(self):
        """Test coverage of database errors"""
        catalog = ErrorCatalog()

        database_patterns = [p for p in catalog.patterns if p.category == ErrorCategory.DATABASE]
        assert len(database_patterns) >= 1

    def test_resource_category_coverage(self):
        """Test coverage of resource errors"""
        catalog = ErrorCatalog()

        resource_patterns = [p for p in catalog.patterns if p.category == ErrorCategory.RESOURCE]
        assert len(resource_patterns) >= 1

    def test_configuration_category_coverage(self):
        """Test coverage of configuration errors"""
        catalog = ErrorCatalog()

        config_patterns = [p for p in catalog.patterns if p.category == ErrorCategory.CONFIGURATION]
        assert len(config_patterns) >= 1

    def test_data_quality_category_coverage(self):
        """Test coverage of data quality errors"""
        catalog = ErrorCatalog()

        dq_patterns = [p for p in catalog.patterns if p.category == ErrorCategory.DATA_QUALITY]
        assert len(dq_patterns) >= 1

    def test_network_category_coverage(self):
        """Test coverage of network errors"""
        catalog = ErrorCatalog()

        network_patterns = [p for p in catalog.patterns if p.category == ErrorCategory.NETWORK]
        assert len(network_patterns) >= 1

    def test_state_category_coverage(self):
        """Test coverage of state management errors"""
        catalog = ErrorCatalog()

        state_patterns = [p for p in catalog.patterns if p.category == ErrorCategory.STATE]
        assert len(state_patterns) >= 1


class TestRealWorldErrorMessages:
    """Test catalog with real-world error messages"""

    def test_duckdb_lock_error(self):
        """Test real DuckDB lock error message"""
        catalog = ErrorCatalog()

        error_msg = "duckdb.IOException: IO Error: Conflicting lock is held in WAL file"
        hints = catalog.find_resolution_hints(error_msg)

        assert len(hints) > 0
        assert any("Close" in hint.title for hint in hints)

    def test_python_memory_error(self):
        """Test Python MemoryError message"""
        catalog = ErrorCatalog()

        error_msg = "MemoryError: Unable to allocate 512 MiB for array"
        hints = catalog.find_resolution_hints(error_msg)

        assert len(hints) > 0
        assert any("Memory" in hint.title for hint in hints)

    def test_dbt_compilation_error_message(self):
        """Test real dbt compilation error"""
        catalog = ErrorCatalog()

        error_msg = "Compilation Error in model int_baseline_workforce (models/intermediate/int_baseline_workforce.sql)"
        hints = catalog.find_resolution_hints(error_msg)

        assert len(hints) > 0

    def test_dbt_test_failure_message(self):
        """Test dbt test failure message"""
        catalog = ErrorCatalog()

        error_msg = "Failure in test not_null_fct_yearly_events_employee_id"
        hints = catalog.find_resolution_hints(error_msg)

        assert len(hints) > 0
