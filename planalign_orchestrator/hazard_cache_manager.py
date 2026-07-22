#!/usr/bin/env python3
"""
Hazard Cache Management System for Navigator Orchestrator

Provides automatic change detection and caching for hazard dimension tables
to optimize performance by avoiding unnecessary recomputation of slow-changing
hazard rates and probabilities.

Epic E068D: Hazard Caches with Automatic Change Detection
"""

from __future__ import annotations

import hashlib
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Optional, Any
import pandas as pd
from threading import Lock

from .config import SimulationConfig
from .dbt_runner import DbtRunner, extract_dbt_failure_detail


class HazardCacheError(Exception):
    """Exception raised for hazard cache operations."""

    pass


class HazardCacheManager:
    """
    Manages hazard cache tables with automatic change detection.

    This class implements the hazard cache system that:
    1. Computes SHA256 hash of parameters affecting hazard calculations
    2. Compares current vs cached parameter hash
    3. Rebuilds cache tables only when parameters change
    4. Provides thread-safe cache operations
    """

    # Cache models to rebuild when parameters change
    CACHE_MODELS = [
        "dim_promotion_hazards",
        "dim_termination_hazards",
        "dim_merit_hazards",
        "dim_enrollment_hazards",
    ]

    # Metadata model to track cache state
    METADATA_MODEL = "hazard_cache_metadata"

    def __init__(
        self,
        config: SimulationConfig,
        dbt_runner: DbtRunner,
        *,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize hazard cache manager.

        Args:
            config: Simulation configuration containing hazard parameters
            dbt_runner: DbtRunner instance for executing dbt commands
            logger: Optional logger instance (creates new one if not provided)
        """
        self.config = config
        self.dbt_runner = dbt_runner
        self.logger = logger or logging.getLogger(__name__)
        self._cache_lock = Lock()  # Thread safety for cache operations

        # Cache for computed hashes to avoid recomputation
        self._current_hash_cache: Optional[str] = None
        self._cached_hash_cache: Optional[str] = None

    def compute_hazard_params_hash(self) -> str:
        """
        Compute SHA256 hash of all parameters affecting hazard calculations.

        This method collects parameters from multiple sources and creates a
        deterministic hash to detect parameter changes:

        - Simulation config (target_growth_rate, termination_rates, etc.)
        - comp_levers.csv file content if exists
        - hazard_parameters.yaml file content if exists (optional)

        Returns:
            SHA256 hash string of all hazard-affecting parameters
        """
        if self._current_hash_cache is not None:
            return self._current_hash_cache

        try:
            # Collect parameters from simulation config
            params: Dict[str, Any] = {"simulation_config": {}}

            # Core simulation parameters
            if hasattr(self.config, "simulation"):
                params["simulation_config"]["target_growth_rate"] = getattr(
                    self.config.simulation, "target_growth_rate", None
                )
                params["simulation_config"]["random_seed"] = getattr(
                    self.config.simulation, "random_seed", None
                )

            # Workforce parameters (termination rates)
            if hasattr(self.config, "workforce"):
                params["simulation_config"]["total_termination_rate"] = getattr(
                    self.config.workforce, "total_termination_rate", None
                )
                params["simulation_config"]["new_hire_termination_rate"] = getattr(
                    self.config.workforce, "new_hire_termination_rate", None
                )

            # Compensation parameters
            if hasattr(self.config, "compensation"):
                params["simulation_config"]["compensation"] = {
                    "cola_rate": getattr(self.config.compensation, "cola_rate", None),
                    "merit_budget": getattr(
                        self.config.compensation, "merit_budget", None
                    ),
                }

                # Promotion compensation settings
                if hasattr(self.config.compensation, "promotion_compensation"):
                    promo_comp = self.config.compensation.promotion_compensation
                    params["simulation_config"]["promotion_compensation"] = {
                        "base_increase_pct": getattr(
                            promo_comp, "base_increase_pct", None
                        ),
                        "distribution_range": getattr(
                            promo_comp, "distribution_range", None
                        ),
                        "max_cap_pct": getattr(promo_comp, "max_cap_pct", None),
                        "max_cap_amount": getattr(promo_comp, "max_cap_amount", None),
                        "distribution_type": getattr(
                            promo_comp, "distribution_type", None
                        ),
                        "level_overrides": getattr(promo_comp, "level_overrides", None),
                    }

            # Enrollment parameters
            if hasattr(self.config, "enrollment"):
                enrollment = self.config.enrollment
                params["simulation_config"]["enrollment"] = {}

                if hasattr(enrollment, "auto_enrollment"):
                    auto = enrollment.auto_enrollment
                    params["simulation_config"]["enrollment"]["auto_enrollment"] = {
                        "enabled": getattr(auto, "enabled", None),
                        "default_deferral_rate": getattr(
                            auto, "default_deferral_rate", None
                        ),
                        "window_days": getattr(auto, "window_days", None),
                        "opt_out_grace_period": getattr(
                            auto, "opt_out_grace_period", None
                        ),
                    }

                    # Opt-out rates
                    if hasattr(auto, "opt_out_rates"):
                        opt_out = auto.opt_out_rates
                        params["simulation_config"]["enrollment"]["opt_out_rates"] = {
                            "by_age": getattr(opt_out, "by_age", {}).dict()  # type: ignore[union-attr]
                            if hasattr(getattr(opt_out, "by_age", {}), "dict")
                            else getattr(opt_out, "by_age", {}),
                            "by_income": getattr(opt_out, "by_income", {}).dict()  # type: ignore[union-attr]
                            if hasattr(getattr(opt_out, "by_income", {}), "dict")
                            else getattr(opt_out, "by_income", {}),
                        }

            # Include comp_levers.csv if exists
            comp_levers_path = Path("dbt/seeds/comp_levers.csv")
            if comp_levers_path.exists():
                try:
                    comp_levers_df = pd.read_csv(comp_levers_path)
                    # Convert to dict and ensure deterministic ordering
                    params["comp_levers"] = comp_levers_df.sort_values(
                        by=list(comp_levers_df.columns)
                    ).to_dict("records")
                except Exception as e:
                    self.logger.warning(f"Could not read comp_levers.csv: {e}")
                    params["comp_levers"] = None
            else:
                params["comp_levers"] = None

            # Include hazard-specific configuration files if they exist
            hazard_config_path = Path("config/hazard_parameters.yaml")
            if hazard_config_path.exists():
                try:
                    with open(hazard_config_path, "r", encoding="utf-8") as f:
                        hazard_config = yaml.safe_load(f)
                        params["hazard_config"] = hazard_config
                except Exception as e:
                    self.logger.warning(f"Could not read hazard_parameters.yaml: {e}")
                    params["hazard_config"] = None
            else:
                params["hazard_config"] = None

            # Create deterministic hash using sorted keys and compact JSON
            params_json = json.dumps(params, sort_keys=True, separators=(",", ":"))
            hash_value = hashlib.sha256(params_json.encode("utf-8")).hexdigest()

            # Cache the computed hash
            self._current_hash_cache = hash_value

            self.logger.debug(f"Computed hazard params hash: {hash_value[:16]}...")
            return hash_value

        except Exception as e:
            self.logger.error(f"Failed to compute hazard params hash: {e}")
            raise HazardCacheError(f"Failed to compute parameters hash: {e}") from e

    def get_cached_params_hash(self) -> Optional[str]:
        """
        Get the parameters hash from the most recent cache build.

        Queries the hazard_cache_metadata table to retrieve the parameters
        hash from the last successful cache build.

        Returns:
            Parameters hash string if found, None if no cache exists or on error
        """
        if self._cached_hash_cache is not None:
            return self._cached_hash_cache

        try:
            # Use DuckDB connection directly since dbt operations might be complex
            from planalign_orchestrator.config import get_database_path
            import duckdb

            db_path = get_database_path()
            with duckdb.connect(str(db_path)) as conn:
                # Check if metadata table exists first
                table_check = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'hazard_cache_metadata'
                """
                ).fetchone()

                if table_check and table_check[0] > 0:
                    # Query cache metadata table for current hash
                    result = conn.execute(
                        """
                        SELECT params_hash
                        FROM hazard_cache_metadata
                        WHERE is_current = TRUE
                        ORDER BY built_at DESC
                        LIMIT 1
                    """
                    ).fetchall()

                    if result:
                        params_hash = result[0][0]
                        self._cached_hash_cache = params_hash
                        self.logger.debug(
                            f"Retrieved cached params hash: {params_hash[:16]}..."
                        )
                        return params_hash

            self.logger.debug(
                "No cached params hash found or metadata table doesn't exist"
            )
            return None

        except Exception as e:
            self.logger.warning(f"Could not retrieve cached params hash: {e}")
            return None

    def should_rebuild_caches(self) -> bool:
        """
        Determine if hazard caches need to be rebuilt.

        Compares current parameter hash with cached hash to determine
        if any parameters affecting hazard calculations have changed.

        Returns:
            True if caches need rebuild, False if caches are current
        """
        try:
            current_hash = self.compute_hazard_params_hash()
            cached_hash = self.get_cached_params_hash()

            needs_rebuild = current_hash != cached_hash

            # Log detailed comparison
            current_short = current_hash[:16] if current_hash else "None"
            cached_short = cached_hash[:16] if cached_hash else "None"

            self.logger.info(
                f"Hazard cache check: current_hash={current_short}..., "
                f"cached_hash={cached_short}..."
            )
            self.logger.info(f"Hazard caches need rebuild: {needs_rebuild}")

            if needs_rebuild and cached_hash:
                self.logger.info(
                    "Parameter changes detected - hazard cache rebuild required"
                )
            elif needs_rebuild and not cached_hash:
                self.logger.info(
                    "No existing cache found - initial hazard cache build required"
                )
            else:
                self.logger.info("Parameters unchanged - hazard caches are current")

            return needs_rebuild

        except Exception as e:
            self.logger.error(f"Error checking cache status: {e}")
            # Conservative approach: rebuild on error
            return True

    def _build_rebuild_error(self, prefix: str, result: Any) -> str:
        """Compose an actionable rebuild error message.

        Streaming dbt runs fold stderr into stdout, so ``result.stderr`` is
        usually empty. Pull the failing node + actual error text out of
        ``target/run_results.json`` and fall back to the captured streams so the
        operator never sees an empty diagnostic.
        """
        message = prefix
        detail = extract_dbt_failure_detail(self.dbt_runner.working_dir)
        if detail:
            message += f": {detail}"
        elif getattr(result, "stderr", ""):
            message += f": {result.stderr.strip()}"
        elif getattr(result, "stdout", ""):
            tail = result.stdout.strip()[-400:]
            message += f" (return code {result.return_code}). Tail: {tail}"
        return message

    def rebuild_hazard_caches(self) -> None:
        """
        Rebuild all hazard cache tables.

        This method:
        1. Computes current parameter hash
        2. Rebuilds all hazard dimension cache tables
        3. Updates cache metadata with new hash and timestamps
        4. Validates the rebuild was successful

        Raises:
            HazardCacheError: If any cache rebuild step fails
        """
        with self._cache_lock:
            try:
                self.logger.info("Starting hazard cache rebuild...")

                current_hash = self.compute_hazard_params_hash()
                self.logger.info(f"Rebuilding with params hash: {current_hash[:16]}...")

                # Set the parameters hash for dbt models (dbt vars)
                extra_vars = {"hazard_params_hash": current_hash}

                # The dim_*_hazards cache models all ref int_effective_parameters
                # (a FOUNDATION int_* table). On a fresh DB it isn't built yet, and
                # `dbt build --select <cache_model>` doesn't pull upstream, so
                # materialize it first or the cache rebuild fails with a catalog error.
                # Use `run` (not `build`) to match how the pipeline builds int_* models
                # — we only need the table to exist, not to run its schema tests here.
                dep = "int_effective_parameters"
                self.logger.info(f"Materializing {dep} (hazard cache dependency)...")
                result = self.dbt_runner.execute_command(
                    ["run", "--select", dep, "--full-refresh"],
                    dbt_vars=extra_vars,
                )
                if not result.success:
                    error_msg = self._build_rebuild_error(
                        f"Failed to build {dep}", result
                    )
                    self.logger.error(error_msg)
                    raise HazardCacheError(error_msg)

                # Feature 121 (Tier A): rebuild the four dim_*_hazards cache models
                # and the metadata model in a SINGLE `dbt build --full-refresh`
                # invocation instead of five separate ones. This is safe by
                # construction: every model here is full-refreshed, dbt resolves the
                # intra-selection order from the ref() DAG (each dim_*_hazards refs
                # int_effective_parameters, materialized just above; hazard_cache_metadata
                # refs the caches), so the built tables are byte-identical to the
                # per-model rebuild. It replaces five subprocess launches + project
                # parses with one. See
                # specs/121-reduce-dbt-invocations/contracts/hazard-cache-batch.md.
                batch_models = [*self.CACHE_MODELS, self.METADATA_MODEL]
                self.logger.info(
                    "Rebuilding hazard caches + metadata in one invocation: %s",
                    ", ".join(batch_models),
                )
                result = self.dbt_runner.execute_command(
                    ["build", "--select", *batch_models, "--full-refresh"],
                    dbt_vars=extra_vars,
                )

                if not result.success:
                    # extract_dbt_failure_detail (used by _build_rebuild_error) reads
                    # target/run_results.json, which dbt populates per node even for a
                    # batched selection, so the message still names the specific failing
                    # cache model (FR-012 failure attribution).
                    error_msg = self._build_rebuild_error(
                        "Failed to rebuild hazard caches", result
                    )
                    self.logger.error(error_msg)
                    raise HazardCacheError(error_msg)

                self.logger.info("Successfully rebuilt hazard caches + metadata")

                # Clear cached hash values to force refresh
                self._current_hash_cache = None
                self._cached_hash_cache = None

                self.logger.info("Hazard cache rebuild completed successfully")

                # Log cache statistics
                self._log_cache_statistics()

            except HazardCacheError:
                # Re-raise hazard cache errors as-is
                raise
            except Exception as e:
                error_msg = f"Unexpected error during cache rebuild: {e}"
                self.logger.error(error_msg)
                raise HazardCacheError(error_msg) from e

    def ensure_hazard_caches_current(self) -> None:
        """
        Ensure hazard caches are current, rebuilding if necessary.

        This is the main entry point for the orchestrator to ensure
        hazard caches are up-to-date before running simulations.
        """
        try:
            if self.should_rebuild_caches():
                self.rebuild_hazard_caches()
            else:
                self.logger.info("Hazard caches are current, skipping rebuild")
                # Still log cache statistics for monitoring
                self._log_cache_statistics()

        except HazardCacheError:
            # Re-raise hazard cache errors as-is
            raise
        except Exception as e:
            error_msg = f"Error ensuring cache currency: {e}"
            self.logger.error(error_msg)
            raise HazardCacheError(error_msg) from e

    def force_cache_rebuild(self) -> None:
        """
        Force a complete rebuild of all hazard caches regardless of hash status.

        This method is useful for manual cache refresh or recovery scenarios.
        """
        self.logger.info("Forcing hazard cache rebuild (ignoring hash status)")

        # Clear cached values to ensure fresh computation
        self._current_hash_cache = None
        self._cached_hash_cache = None

        self.rebuild_hazard_caches()

    def get_cache_status(self) -> Dict[str, Any]:
        """
        Get current cache status for monitoring and debugging.

        Returns:
            Dictionary containing cache status information
        """
        try:
            current_hash = self.compute_hazard_params_hash()
            cached_hash = self.get_cached_params_hash()
            needs_rebuild = current_hash != cached_hash

            return {
                "current_params_hash": current_hash,
                "cached_params_hash": cached_hash,
                "needs_rebuild": needs_rebuild,
                "cache_models": self.CACHE_MODELS,
                "metadata_model": self.METADATA_MODEL,
                "thread_safe": True,
            }

        except Exception as e:
            return {
                "error": str(e),
                "current_params_hash": None,
                "cached_params_hash": None,
                "needs_rebuild": True,
                "cache_models": self.CACHE_MODELS,
                "metadata_model": self.METADATA_MODEL,
                "thread_safe": True,
            }

    def _log_cache_statistics(self) -> None:
        """Log cache statistics for monitoring."""
        try:
            # Use DuckDB connection directly for statistics
            from planalign_orchestrator.config import get_database_path
            import duckdb

            db_path = get_database_path()
            with duckdb.connect(str(db_path)) as conn:
                # Check if metadata table exists first
                table_check = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'hazard_cache_metadata'
                """
                ).fetchone()

                if table_check and table_check[0] > 0:
                    # Query cache metadata for statistics
                    results = conn.execute(
                        """
                        SELECT
                            cache_name,
                            built_at,
                            row_count,
                            data_checksum
                        FROM hazard_cache_metadata
                        WHERE is_current = TRUE
                        ORDER BY cache_name
                    """
                    ).fetchall()

                    if results:
                        self.logger.info("Hazard cache statistics:")
                        for cache_name, built_at, row_count, data_checksum in results:
                            # Protect against NULLs in early runs
                            _prefix = (data_checksum or "")[0:8]
                            self.logger.info(
                                f"  {cache_name}: {row_count} rows, checksum {_prefix}..."
                            )
                    else:
                        self.logger.info("No current hazard cache statistics available")
                else:
                    self.logger.info(
                        "Hazard cache metadata table not found - caches not yet built"
                    )

        except Exception as e:
            self.logger.warning(f"Error logging cache statistics: {e}")
