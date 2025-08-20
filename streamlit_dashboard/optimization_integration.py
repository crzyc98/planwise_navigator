"""
Optimization Integration Utilities
Provides integration between optimization interfaces and the PlanWise Navigator DuckDB system.

This module handles:
- DuckDB integration with existing simulation data
- Caching strategies for performance
- Data validation and quality checks
- Legacy compatibility
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import time
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import duckdb
import pandas as pd
import streamlit as st
from optimization_results_manager import get_optimization_results_manager
from optimization_storage import (OptimizationRun, OptimizationStatus,
                                  OptimizationType, get_optimization_storage)

# Set up logging
logger = logging.getLogger(__name__)


class DuckDBIntegration:
    """Integration layer for DuckDB operations with optimization results."""

    def __init__(
        self,
        db_path: str = "/Users/nicholasamaral/planwise_navigator/simulation.duckdb",
    ):
        """Initialize DuckDB integration."""
        self.db_path = Path(db_path)
        self.schema = "main"
        self._connection_pool = {}

    def get_connection(self):
        """Get a DuckDB connection with proper context management."""
        return duckdb.connect(str(self.db_path))

    def validate_simulation_data_quality(self, run_id: str) -> Dict[str, Any]:
        """Validate the quality of simulation data associated with an optimization run."""
        quality_metrics = {
            "workforce_snapshot_integrity": False,
            "event_data_consistency": False,
            "parameter_application_success": False,
            "data_completeness_score": 0.0,
            "warnings": [],
            "errors": [],
        }

        try:
            with self.get_connection() as conn:
                # Check workforce snapshot integrity
                workforce_check = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(DISTINCT simulation_year) as year_count,
                        MIN(simulation_year) as min_year,
                        MAX(simulation_year) as max_year,
                        COUNT(DISTINCT employee_id) as unique_employees
                    FROM fct_workforce_snapshot
                    WHERE simulation_year >= 2025
                """
                ).fetchone()

                if workforce_check and workforce_check[0] > 0:
                    quality_metrics["workforce_snapshot_integrity"] = True
                    quality_metrics["data_completeness_score"] += 0.3
                else:
                    quality_metrics["warnings"].append(
                        "No recent workforce snapshot data found"
                    )

                # Check event data consistency
                events_check = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(DISTINCT event_type) as event_types,
                        COUNT(DISTINCT simulation_year) as event_years
                    FROM fct_yearly_events
                    WHERE simulation_year >= 2025
                """
                ).fetchone()

                if events_check and events_check[0] > 0:
                    quality_metrics["event_data_consistency"] = True
                    quality_metrics["data_completeness_score"] += 0.3
                else:
                    quality_metrics["warnings"].append("Limited event data available")

                # Check parameter application
                params_check = conn.execute(
                    """
                    SELECT
                        COUNT(*) as param_count,
                        COUNT(DISTINCT simulation_year) as param_years,
                        MAX(last_updated) as last_param_update
                    FROM int_effective_parameters
                    WHERE simulation_year >= 2025
                """
                ).fetchone()

                if params_check and params_check[0] > 0:
                    quality_metrics["parameter_application_success"] = True
                    quality_metrics["data_completeness_score"] += 0.4
                else:
                    quality_metrics["errors"].append(
                        "Parameter application may have failed"
                    )

                # Additional consistency checks
                self._check_data_consistency(conn, quality_metrics)

        except Exception as e:
            quality_metrics["errors"].append(f"Database validation error: {str(e)}")
            logger.error(f"Data quality validation failed for run {run_id}: {e}")

        return quality_metrics

    def _check_data_consistency(self, conn, quality_metrics: Dict[str, Any]):
        """Perform additional data consistency checks."""
        try:
            # Check for reasonable workforce growth patterns
            growth_check = conn.execute(
                """
                SELECT
                    simulation_year,
                    COUNT(*) as headcount,
                    LAG(COUNT(*)) OVER (ORDER BY simulation_year) as prev_headcount
                FROM fct_workforce_snapshot
                WHERE simulation_year BETWEEN 2025 AND 2029
                GROUP BY simulation_year
                ORDER BY simulation_year
            """
            ).fetchall()

            if growth_check:
                for year_data in growth_check[1:]:  # Skip first year (no previous data)
                    current_hc = year_data[1]
                    prev_hc = year_data[2]
                    if prev_hc and current_hc:
                        growth_rate = (current_hc - prev_hc) / prev_hc
                        if abs(growth_rate) > 0.5:  # More than 50% change
                            quality_metrics["warnings"].append(
                                f"Unusual growth rate in {year_data[0]}: {growth_rate:.1%}"
                            )

            # Check for parameter value reasonableness
            param_check = conn.execute(
                """
                SELECT parameter_name, parameter_value
                FROM int_effective_parameters
                WHERE simulation_year = 2025
                AND parameter_name LIKE '%merit_rate%'
            """
            ).fetchall()

            for param_name, param_value in param_check:
                if param_value < 0 or param_value > 0.2:  # Outside 0-20% range
                    quality_metrics["warnings"].append(
                        f"Unusual parameter value: {param_name} = {param_value:.1%}"
                    )

        except Exception as e:
            quality_metrics["warnings"].append(f"Consistency check error: {str(e)}")

    def get_simulation_summary(self, year: int = 2025) -> Dict[str, Any]:
        """Get a summary of simulation data for a specific year."""
        try:
            with self.get_connection() as conn:
                # Workforce summary
                workforce_summary = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_headcount,
                        AVG(current_compensation) as avg_compensation,
                        SUM(current_compensation) as total_compensation,
                        COUNT(DISTINCT level_id) as job_levels,
                        COUNT(CASE WHEN detailed_status_code = 'continuous_active' THEN 1 END) as continuing_employees,
                        COUNT(CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 END) as new_hires,
                        COUNT(CASE WHEN detailed_status_code LIKE '%termination%' THEN 1 END) as terminations
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                """,
                    [year],
                ).fetchone()

                # Event summary
                event_summary = conn.execute(
                    """
                    SELECT
                        event_type,
                        COUNT(*) as event_count
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                    GROUP BY event_type
                """,
                    [year],
                ).fetchall()

                # Parameter summary
                param_summary = conn.execute(
                    """
                    SELECT
                        parameter_name,
                        parameter_value
                    FROM int_effective_parameters
                    WHERE simulation_year = ?
                    AND parameter_name IN (
                        'merit_rate_level_1', 'merit_rate_level_2', 'cola_rate',
                        'new_hire_salary_adjustment', 'promotion_probability_level_1'
                    )
                """,
                    [year],
                ).fetchall()

                return {
                    "year": year,
                    "workforce": {
                        "total_headcount": workforce_summary[0]
                        if workforce_summary
                        else 0,
                        "avg_compensation": workforce_summary[1]
                        if workforce_summary
                        else 0,
                        "total_compensation": workforce_summary[2]
                        if workforce_summary
                        else 0,
                        "job_levels": workforce_summary[3] if workforce_summary else 0,
                        "continuing_employees": workforce_summary[4]
                        if workforce_summary
                        else 0,
                        "new_hires": workforce_summary[5] if workforce_summary else 0,
                        "terminations": workforce_summary[6]
                        if workforce_summary
                        else 0,
                    },
                    "events": {event[0]: event[1] for event in event_summary},
                    "parameters": {param[0]: param[1] for param in param_summary},
                }

        except Exception as e:
            logger.error(f"Failed to get simulation summary for year {year}: {e}")
            return {"error": str(e)}

    def get_multi_year_summary(
        self, start_year: int = 2025, end_year: int = 2029
    ) -> Dict[str, Any]:
        """Get simulation summary across multiple years."""
        summaries = {}
        for year in range(start_year, end_year + 1):
            summaries[year] = self.get_simulation_summary(year)

        # Calculate year-over-year metrics
        yoy_metrics = {}
        years = sorted(summaries.keys())
        for i in range(1, len(years)):
            current_year = years[i]
            prev_year = years[i - 1]

            if (
                "error" not in summaries[current_year]
                and "error" not in summaries[prev_year]
            ):
                current_hc = summaries[current_year]["workforce"]["total_headcount"]
                prev_hc = summaries[prev_year]["workforce"]["total_headcount"]

                current_comp = summaries[current_year]["workforce"][
                    "total_compensation"
                ]
                prev_comp = summaries[prev_year]["workforce"]["total_compensation"]

                yoy_metrics[current_year] = {
                    "headcount_growth": (current_hc - prev_hc) / prev_hc
                    if prev_hc > 0
                    else 0,
                    "compensation_growth": (current_comp - prev_comp) / prev_comp
                    if prev_comp > 0
                    else 0,
                }

        return {
            "year_summaries": summaries,
            "yoy_metrics": yoy_metrics,
            "overall": {
                "years_analyzed": len(
                    [s for s in summaries.values() if "error" not in s]
                ),
                "total_years": len(summaries),
                "data_quality": "good"
                if all("error" not in s for s in summaries.values())
                else "partial",
            },
        }


class OptimizationCache:
    """Caching system for optimization results and simulation data."""

    def __init__(self, cache_dir: str = "/tmp/planwise_optimization_cache"):
        """Initialize the cache system."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.session_cache = {}
        self.cache_ttl = timedelta(hours=24)  # 24-hour cache TTL

    def _get_cache_key(self, key_data: Dict[str, Any]) -> str:
        """Generate a cache key from data."""
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{cache_key}.pkl"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if a cache file is still valid."""
        if not cache_path.exists():
            return False

        file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        return datetime.now() - file_time < self.cache_ttl

    def get_cached_simulation_results(
        self, parameters: Dict[str, float], year: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached simulation results for specific parameters and year."""
        cache_key_data = {
            "type": "simulation_results",
            "parameters": parameters,
            "year": year,
        }
        cache_key = self._get_cache_key(cache_key_data)

        # Check session cache first
        if cache_key in self.session_cache:
            return self.session_cache[cache_key]

        # Check file cache
        cache_path = self._get_cache_path(cache_key)
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    cached_data = pickle.load(f)
                    self.session_cache[cache_key] = cached_data
                    return cached_data
            except Exception as e:
                logger.warning(f"Failed to load cached simulation results: {e}")

        return None

    def cache_simulation_results(
        self, parameters: Dict[str, float], year: int, results: Dict[str, Any]
    ):
        """Cache simulation results for specific parameters and year."""
        cache_key_data = {
            "type": "simulation_results",
            "parameters": parameters,
            "year": year,
        }
        cache_key = self._get_cache_key(cache_key_data)

        # Store in session cache
        self.session_cache[cache_key] = results

        # Store in file cache
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(results, f)
        except Exception as e:
            logger.warning(f"Failed to cache simulation results: {e}")

    def get_cached_optimization_result(
        self, config_hash: str
    ) -> Optional[OptimizationRun]:
        """Get cached optimization result by configuration hash."""
        cache_key_data = {"type": "optimization_result", "config_hash": config_hash}
        cache_key = self._get_cache_key(cache_key_data)

        # Check session cache first
        if cache_key in self.session_cache:
            return self.session_cache[cache_key]

        # Check file cache
        cache_path = self._get_cache_path(cache_key)
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    cached_data = pickle.load(f)
                    self.session_cache[cache_key] = cached_data
                    return cached_data
            except Exception as e:
                logger.warning(f"Failed to load cached optimization result: {e}")

        return None

    def cache_optimization_result(self, config_hash: str, result: OptimizationRun):
        """Cache optimization result by configuration hash."""
        cache_key_data = {"type": "optimization_result", "config_hash": config_hash}
        cache_key = self._get_cache_key(cache_key_data)

        # Store in session cache
        self.session_cache[cache_key] = result

        # Store in file cache
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(result, f)
        except Exception as e:
            logger.warning(f"Failed to cache optimization result: {e}")

    def clear_cache(self, cache_type: str = None):
        """Clear cache (session and/or file cache)."""
        # Clear session cache
        if cache_type is None or cache_type == "session":
            self.session_cache.clear()

        # Clear file cache
        if cache_type is None or cache_type == "file":
            try:
                for cache_file in self.cache_dir.glob("*.pkl"):
                    cache_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to clear file cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        file_cache_count = len(list(self.cache_dir.glob("*.pkl")))
        file_cache_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.pkl"))

        return {
            "session_cache_size": len(self.session_cache),
            "file_cache_count": file_cache_count,
            "file_cache_size_mb": file_cache_size / (1024 * 1024),
            "cache_directory": str(self.cache_dir),
        }


def cached_function(cache_key_func=None, ttl_minutes=60):
    """Decorator for caching function results."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if cache_key_func:
                cache_key_data = cache_key_func(*args, **kwargs)
            else:
                cache_key_data = {
                    "function": func.__name__,
                    "args": args,
                    "kwargs": kwargs,
                }

            cache_key = hashlib.md5(
                json.dumps(cache_key_data, sort_keys=True, default=str).encode()
            ).hexdigest()

            # Check session state cache
            cache_session_key = f"function_cache_{func.__name__}"
            if cache_session_key not in st.session_state:
                st.session_state[cache_session_key] = {}

            cache = st.session_state[cache_session_key]

            # Check if cached result exists and is still valid
            if cache_key in cache:
                cached_result, cached_time = cache[cache_key]
                if datetime.now() - cached_time < timedelta(minutes=ttl_minutes):
                    return cached_result

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache[cache_key] = (result, datetime.now())

            # Cleanup old cache entries (keep only last 50)
            if len(cache) > 50:
                oldest_keys = sorted(cache.keys(), key=lambda k: cache[k][1])[
                    : len(cache) - 50
                ]
                for old_key in oldest_keys:
                    del cache[old_key]

            return result

        return wrapper

    return decorator


class LegacyCompatibility:
    """Provides compatibility with legacy optimization result formats."""

    @staticmethod
    def convert_legacy_format(legacy_data: Dict[str, Any]) -> OptimizationRun:
        """Convert legacy optimization result format to new OptimizationRun format."""
        # This function handles conversion from old pickle/JSON formats
        # that might exist in the system

        from optimization_storage import (OptimizationConfiguration,
                                          OptimizationEngine,
                                          OptimizationMetadata,
                                          OptimizationResults, OptimizationRun,
                                          OptimizationStatus, OptimizationType)

        # Extract metadata
        metadata = OptimizationMetadata(
            scenario_id=legacy_data.get("scenario_id", "legacy_import"),
            optimization_type=OptimizationType.MANUAL_ADJUSTMENT,
            optimization_engine=OptimizationEngine.MANUAL,
            status=OptimizationStatus.COMPLETED,
            description="Imported from legacy format",
            tags=["legacy", "imported"],
        )

        # Extract configuration
        configuration = OptimizationConfiguration(
            initial_parameters=legacy_data.get("initial_parameters", {}),
            algorithm_config=legacy_data.get("algorithm_config", {}),
        )

        # Extract results
        results = OptimizationResults(
            objective_value=legacy_data.get("objective_value"),
            optimal_parameters=legacy_data.get("optimal_parameters", {}),
            risk_level=legacy_data.get("risk_level", "MEDIUM"),
        )

        return OptimizationRun(
            metadata=metadata, configuration=configuration, results=results
        )

    @staticmethod
    def import_legacy_results(file_path: str) -> List[str]:
        """Import legacy optimization results from file."""
        imported_runs = []

        try:
            with open(file_path, "rb") as f:
                legacy_data = pickle.load(f)

            # Handle different legacy formats
            if isinstance(legacy_data, list):
                # Multiple results
                for item in legacy_data:
                    run = LegacyCompatibility.convert_legacy_format(item)
                    storage = get_optimization_storage()
                    run_id = storage.save_run_with_session_cache(run)
                    imported_runs.append(run_id)
            else:
                # Single result
                run = LegacyCompatibility.convert_legacy_format(legacy_data)
                storage = get_optimization_storage()
                run_id = storage.save_run_with_session_cache(run)
                imported_runs.append(run_id)

        except Exception as e:
            logger.error(f"Failed to import legacy results from {file_path}: {e}")
            raise

        return imported_runs


# Singleton instances
_duckdb_integration = None
_optimization_cache = None


def get_duckdb_integration() -> DuckDBIntegration:
    """Get the singleton DuckDB integration instance."""
    global _duckdb_integration
    if _duckdb_integration is None:
        _duckdb_integration = DuckDBIntegration()
    return _duckdb_integration


def get_optimization_cache() -> OptimizationCache:
    """Get the singleton optimization cache instance."""
    global _optimization_cache
    if _optimization_cache is None:
        _optimization_cache = OptimizationCache()
    return _optimization_cache


# Streamlit integration functions
@st.cache_data(ttl=300)  # 5-minute cache
def get_cached_simulation_summary(year: int) -> Dict[str, Any]:
    """Get simulation summary with Streamlit caching."""
    db_integration = get_duckdb_integration()
    return db_integration.get_simulation_summary(year)


@st.cache_data(ttl=600)  # 10-minute cache
def get_cached_multi_year_summary(start_year: int, end_year: int) -> Dict[str, Any]:
    """Get multi-year simulation summary with Streamlit caching."""
    db_integration = get_duckdb_integration()
    return db_integration.get_multi_year_summary(start_year, end_year)


def validate_optimization_environment() -> Dict[str, Any]:
    """Validate the optimization environment setup."""
    validation_results = {
        "database_accessible": False,
        "tables_exist": False,
        "recent_data_available": False,
        "cache_operational": False,
        "storage_initialized": False,
        "warnings": [],
        "errors": [],
    }

    try:
        # Test database connection
        db_integration = get_duckdb_integration()
        with db_integration.get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
            validation_results["database_accessible"] = True

        # Check required tables
        required_tables = [
            "fct_workforce_snapshot",
            "fct_yearly_events",
            "int_effective_parameters",
            "optimization_runs",
            "optimization_results",
        ]

        with db_integration.get_connection() as conn:
            for table in required_tables:
                try:
                    result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                    if result[0] >= 0:  # Table exists and is accessible
                        continue
                except:
                    validation_results["errors"].append(f"Table {table} not accessible")
                    break
            else:
                validation_results["tables_exist"] = True

        # Check for recent data
        summary = get_cached_simulation_summary(2025)
        if (
            "error" not in summary
            and summary.get("workforce", {}).get("total_headcount", 0) > 0
        ):
            validation_results["recent_data_available"] = True
        else:
            validation_results["warnings"].append("No recent simulation data found")

        # Test cache system
        cache = get_optimization_cache()
        cache_stats = cache.get_cache_stats()
        validation_results["cache_operational"] = True

        # Test storage system
        storage = get_optimization_storage()
        recent_runs = storage.get_recent_runs(1)
        validation_results["storage_initialized"] = True

    except Exception as e:
        validation_results["errors"].append(f"Environment validation failed: {str(e)}")

    return validation_results


if __name__ == "__main__":
    # Test the integration
    print("Testing DuckDB Integration...")

    # Test environment validation
    validation = validate_optimization_environment()
    print(f"Environment validation: {validation}")

    # Test simulation summary
    db_integration = get_duckdb_integration()
    summary = db_integration.get_simulation_summary(2025)
    print(f"2025 simulation summary: {summary}")

    # Test cache
    cache = get_optimization_cache()
    cache_stats = cache.get_cache_stats()
    print(f"Cache stats: {cache_stats}")
