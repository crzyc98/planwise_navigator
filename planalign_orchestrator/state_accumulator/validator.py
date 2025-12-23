"""
YearDependencyValidator - Runtime validation of temporal year dependencies.

Validates that prior year data exists in state accumulator tables before
executing the STATE_ACCUMULATION stage. Prevents silent data corruption
from out-of-order year execution.

Example:
    validator = YearDependencyValidator(db_manager, start_year=2025)
    validator.validate_year_dependencies(year=2026)  # Raises if 2025 missing
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict

from planalign_orchestrator.exceptions import YearDependencyError
from planalign_orchestrator.state_accumulator.registry import StateAccumulatorRegistry

if TYPE_CHECKING:
    from planalign_orchestrator.utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class YearDependencyValidator:
    """Validates temporal dependencies before state accumulation.

    Checks that prior year data exists in all registered state accumulator
    tables before allowing a simulation year to execute. This prevents
    silent data corruption from out-of-order year execution.

    Attributes:
        db_manager: DatabaseConnectionManager for database queries.
        start_year: The configured simulation start year.
                   Start year has no prior dependency requirement.

    Example:
        >>> validator = YearDependencyValidator(db_manager, start_year=2025)
        >>> validator.validate_year_dependencies(2025)  # OK - start year
        >>> validator.validate_year_dependencies(2026)  # Checks 2025 data exists
    """

    def __init__(
        self,
        db_manager: "DatabaseConnectionManager",
        start_year: int
    ) -> None:
        """Initialize the validator.

        Args:
            db_manager: Database connection manager for executing queries.
            start_year: The configured simulation start year.
        """
        self.db_manager = db_manager
        self.start_year = start_year
        logger.debug(f"YearDependencyValidator initialized with start_year={start_year}")

    def validate_year_dependencies(self, year: int) -> None:
        """Validate that prior year data exists for all registered accumulators.

        This method should be called before STATE_ACCUMULATION stage execution.
        If year equals start_year, validation is skipped (no prior dependency).

        Args:
            year: The simulation year about to execute.

        Raises:
            YearDependencyError: If prior year data is missing for any
                               registered state accumulator.

        Example:
            >>> validator.validate_year_dependencies(2026)
            # Checks that 2025 data exists in all registered accumulators
        """
        # Start year has no prior dependency
        if year == self.start_year:
            logger.debug(f"Year {year} is start year - no prior dependency validation needed")
            return

        # Check for missing prior year data
        missing = self.get_missing_years(year)

        if missing:
            logger.warning(
                f"Year dependency validation failed for year {year}: "
                f"missing data in {len(missing)} accumulators"
            )
            raise YearDependencyError(
                year=year,
                missing_tables=missing,
                start_year=self.start_year
            )

        logger.debug(f"Year dependency validation passed for year {year}")

    def get_missing_years(self, year: int) -> Dict[str, int]:
        """Check which required accumulators are missing prior year data.

        Queries each registered state accumulator table to check if data
        exists for the prior year (year - 1). Only checks accumulators where
        required_for_year_validation=True.

        Args:
            year: The simulation year to check dependencies for.

        Returns:
            Dict mapping table_name to row count (0 indicates missing data).
            Empty dict if all required dependencies are satisfied.

        Example:
            >>> missing = validator.get_missing_years(2026)
            >>> # Returns {"int_enrollment_state_accumulator": 0} if 2025 missing
        """
        missing: Dict[str, int] = {}
        prior_year = year - 1

        # Get all registered contracts
        contracts = StateAccumulatorRegistry.get_all_contracts()

        if not contracts:
            logger.debug("No state accumulators registered - nothing to validate")
            return {}

        for contract in contracts:
            count = self._check_table_year_count(
                table_name=contract.table_name,
                year_column=contract.prior_year_column,
                year=prior_year
            )

            if count == 0:
                if contract.required_for_year_validation:
                    missing[contract.table_name] = 0
                    logger.debug(
                        f"Missing data (REQUIRED): {contract.table_name} has 0 rows "
                        f"for {contract.prior_year_column}={prior_year}"
                    )
                else:
                    logger.debug(
                        f"Empty accumulator (optional): {contract.table_name} has 0 rows "
                        f"for {contract.prior_year_column}={prior_year} - allowed"
                    )
            else:
                logger.debug(
                    f"Found data: {contract.table_name} has {count} rows "
                    f"for {contract.prior_year_column}={prior_year}"
                )

        return missing

    def _check_table_year_count(
        self,
        table_name: str,
        year_column: str,
        year: int
    ) -> int:
        """Query the count of rows for a specific year in a table.

        Args:
            table_name: Name of the table to query.
            year_column: Column containing the year value.
            year: Year value to filter on.

        Returns:
            Number of rows matching the year filter.
        """
        def _query(conn):
            try:
                result = conn.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE {year_column} = ?",
                    [year]
                ).fetchone()[0]
                return int(result)
            except Exception as e:
                # If table doesn't exist, treat as 0 rows
                logger.warning(f"Error querying {table_name}: {e}")
                return 0

        return self.db_manager.execute_with_retry(_query)

    def validate_checkpoint_dependencies(self, checkpoint_year: int) -> None:
        """Validate dependency chain from start_year to checkpoint_year.

        Used when resuming from a checkpoint to ensure all prior years
        have data in state accumulator tables.

        Args:
            checkpoint_year: The year of the checkpoint being resumed.

        Raises:
            YearDependencyError: If any year in the chain is missing data.

        Example:
            >>> # Checkpoint at 2027 requires 2025 and 2026 data
            >>> validator.validate_checkpoint_dependencies(2027)
        """
        logger.info(
            f"Validating checkpoint dependency chain: "
            f"{self.start_year} -> {checkpoint_year}"
        )

        # Validate each year in the chain (excluding start year)
        for year in range(self.start_year + 1, checkpoint_year):
            missing = self.get_missing_years(year)
            if missing:
                logger.warning(
                    f"Checkpoint dependency chain broken at year {year}: "
                    f"missing data in {list(missing.keys())}"
                )
                raise YearDependencyError(
                    year=year,
                    missing_tables=missing,
                    start_year=self.start_year
                )

        logger.info(f"Checkpoint dependency chain validated successfully")
