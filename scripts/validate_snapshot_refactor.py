#!/usr/bin/env python3
"""
Enhanced Snapshot Validation Script with Enterprise-Grade Error Handling

This script validates snapshot operations for workforce simulation with:
- Retry logic for dbt commands with exponential backoff
- Graceful degradation for optional validations
- Comprehensive resource cleanup with context managers
- Enterprise-grade error reporting and logging

Following PlanWise Navigator's enterprise-grade standards for production deployment.
"""

from __future__ import annotations

import time
import duckdb
import pandas as pd
import sys
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import functools
import traceback
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Configure enterprise-grade logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(project_root / "validation_log.txt", mode='a')
    ]
)
logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation criticality levels for graceful degradation."""
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class ValidationResult(Enum):
    """Validation result status."""
    SUCCESS = "success"
    WARNING = "warning"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class ValidationOutcome:
    """Enterprise-grade validation result structure."""
    name: str
    level: ValidationLevel
    result: ValidationResult
    message: str
    details: Dict[str, Any]
    execution_time: float
    retry_count: int = 0
    error: Optional[Exception] = None


class RetryConfig:
    """Configuration for retry logic with exponential backoff."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt with exponential backoff."""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        
        return delay


def retry_with_exponential_backoff(
    retry_config: RetryConfig,
    exceptions: Tuple[Exception, ...] = (Exception,),
    validation_level: ValidationLevel = ValidationLevel.CRITICAL
):
    """Decorator for retry logic with exponential backoff and graceful degradation."""
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> ValidationOutcome:
            start_time = time.time()
            last_exception = None
            
            for attempt in range(retry_config.max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    
                    if isinstance(result, ValidationOutcome):
                        result.execution_time = execution_time
                        result.retry_count = attempt
                        return result
                    else:
                        # Wrap non-ValidationOutcome results
                        return ValidationOutcome(
                            name=func.__name__,
                            level=validation_level,
                            result=ValidationResult.SUCCESS,
                            message="Validation completed successfully",
                            details={"result": result},
                            execution_time=execution_time,
                            retry_count=attempt
                        )
                        
                except exceptions as e:
                    last_exception = e
                    execution_time = time.time() - start_time
                    
                    if attempt < retry_config.max_retries:
                        delay = retry_config.get_delay(attempt)
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                    else:
                        # Final attempt failed - apply graceful degradation
                        logger.error(
                            f"All {retry_config.max_retries + 1} attempts failed for {func.__name__}: {e}"
                        )
                        
                        # Graceful degradation based on validation level
                        if validation_level == ValidationLevel.OPTIONAL:
                            return ValidationOutcome(
                                name=func.__name__,
                                level=validation_level,
                                result=ValidationResult.SKIPPED,
                                message=f"Optional validation skipped after {retry_config.max_retries + 1} failures",
                                details={"error": str(e), "traceback": traceback.format_exc()},
                                execution_time=execution_time,
                                retry_count=attempt,
                                error=e
                            )
                        elif validation_level == ValidationLevel.IMPORTANT:
                            return ValidationOutcome(
                                name=func.__name__,
                                level=validation_level,
                                result=ValidationResult.WARNING,
                                message=f"Important validation failed but continuing: {e}",
                                details={"error": str(e), "traceback": traceback.format_exc()},
                                execution_time=execution_time,
                                retry_count=attempt,
                                error=e
                            )
                        else:  # CRITICAL
                            return ValidationOutcome(
                                name=func.__name__,
                                level=validation_level,
                                result=ValidationResult.FAILURE,
                                message=f"Critical validation failed: {e}",
                                details={"error": str(e), "traceback": traceback.format_exc()},
                                execution_time=execution_time,
                                retry_count=attempt,
                                error=e
                            )
            
            # Should never reach here, but defensive programming
            return ValidationOutcome(
                name=func.__name__,
                level=validation_level,
                result=ValidationResult.FAILURE,
                message="Unexpected error in retry logic",
                details={"last_exception": str(last_exception)},
                execution_time=time.time() - start_time,
                retry_count=retry_config.max_retries
            )
        
        return wrapper
    return decorator


@contextmanager
def managed_duckdb_connection(db_path: Path):
    """Context manager for DuckDB connections with comprehensive cleanup."""
    conn = None
    try:
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found at {db_path}")
        
        logger.info(f"Connecting to database: {db_path}")
        conn = duckdb.connect(str(db_path))
        yield conn
        
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
                logger.debug("Database connection closed successfully")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")


@contextmanager
def managed_subprocess(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 300):
    """Context manager for subprocess execution with comprehensive cleanup."""
    process = None
    try:
        logger.info(f"Executing command: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        yield process
        
    except Exception as e:
        logger.error(f"Subprocess execution error: {e}")
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except:
                    pass
        raise
    finally:
        if process is not None:
            try:
                if process.poll() is None:  # Process still running
                    process.terminate()
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"Error during subprocess cleanup: {e}")


class SnapshotValidator:
    """Enterprise-grade snapshot validation with enhanced error handling."""
    
    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        graceful_degradation: bool = True
    ):
        self.retry_config = retry_config or RetryConfig()
        self.graceful_degradation = graceful_degradation
        self.db_path = project_root / "simulation.duckdb"
        self.dbt_dir = project_root / "dbt"
        self.validation_results: List[ValidationOutcome] = []
    
    @retry_with_exponential_backoff(
        retry_config=RetryConfig(max_retries=3),
        exceptions=(subprocess.CalledProcessError, subprocess.TimeoutExpired),
        validation_level=ValidationLevel.CRITICAL
    )
    def execute_dbt_command_with_retry(
        self,
        command: List[str],
        timeout: int = 300
    ) -> ValidationOutcome:
        """Execute dbt command with retry logic and comprehensive error handling."""
        
        with managed_subprocess(command, cwd=self.dbt_dir, timeout=timeout) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                
                if process.returncode == 0:
                    return ValidationOutcome(
                        name=f"dbt_command_{'_'.join(command)}",
                        level=ValidationLevel.CRITICAL,
                        result=ValidationResult.SUCCESS,
                        message=f"dbt command executed successfully: {' '.join(command)}",
                        details={
                            "command": command,
                            "stdout": stdout[:1000],  # Limit output size
                            "stderr": stderr[:1000] if stderr else None
                        },
                        execution_time=0.0  # Will be set by decorator
                    )
                else:
                    raise subprocess.CalledProcessError(
                        process.returncode,
                        command,
                        output=stdout,
                        stderr=stderr
                    )
                    
            except subprocess.TimeoutExpired:
                process.kill()
                raise subprocess.TimeoutExpired(command, timeout)
    
    @retry_with_exponential_backoff(
        retry_config=RetryConfig(max_retries=2),
        exceptions=(duckdb.Error, duckdb.OperationalError),
        validation_level=ValidationLevel.IMPORTANT
    )
    def validate_snapshot_integrity(self) -> ValidationOutcome:
        """Validate snapshot data integrity with retry logic."""
        
        with managed_duckdb_connection(self.db_path) as conn:
            # Check snapshot table exists and has data
            snapshot_check = """
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT employee_id) as unique_employees,
                COUNT(DISTINCT simulation_year) as unique_years,
                MAX(simulation_year) as latest_year,
                MIN(simulation_year) as earliest_year
            FROM fct_workforce_snapshot
            """
            
            result = conn.execute(snapshot_check).df().iloc[0]
            
            # Data integrity checks
            issues = []
            
            if result['total_records'] == 0:
                issues.append("No records found in workforce snapshot")
            
            if result['unique_employees'] == 0:
                issues.append("No unique employees found")
            
            # Check for reasonable data ranges
            if result['latest_year'] > datetime.now().year + 50:
                issues.append(f"Unrealistic future year: {result['latest_year']}")
            
            if result['earliest_year'] < 1900:
                issues.append(f"Unrealistic historical year: {result['earliest_year']}")
            
            return ValidationOutcome(
                name="snapshot_integrity",
                level=ValidationLevel.IMPORTANT,
                result=ValidationResult.SUCCESS if not issues else ValidationResult.WARNING,
                message="Snapshot integrity validation completed" if not issues else f"Issues found: {'; '.join(issues)}",
                details={
                    "total_records": int(result['total_records']),
                    "unique_employees": int(result['unique_employees']),
                    "unique_years": int(result['unique_years']),
                    "latest_year": int(result['latest_year']),
                    "earliest_year": int(result['earliest_year']),
                    "issues": issues
                },
                execution_time=0.0
            )
    
    @retry_with_exponential_backoff(
        retry_config=RetryConfig(max_retries=1),
        exceptions=(Exception,),
        validation_level=ValidationLevel.OPTIONAL
    )
    def validate_compensation_ranges(self) -> ValidationOutcome:
        """Optional validation for compensation ranges with graceful degradation."""
        
        with managed_duckdb_connection(self.db_path) as conn:
            compensation_check = """
            SELECT 
                COUNT(*) as total_employees,
                AVG(current_compensation) as avg_compensation,
                MIN(current_compensation) as min_compensation,
                MAX(current_compensation) as max_compensation,
                COUNT(CASE WHEN current_compensation < 0 THEN 1 END) as negative_compensation,
                COUNT(CASE WHEN current_compensation > 10000000 THEN 1 END) as extreme_compensation
            FROM fct_workforce_snapshot
            WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
            """
            
            result = conn.execute(compensation_check).df().iloc[0]
            
            warnings = []
            
            if result['negative_compensation'] > 0:
                warnings.append(f"{result['negative_compensation']} employees with negative compensation")
            
            if result['extreme_compensation'] > 0:
                warnings.append(f"{result['extreme_compensation']} employees with >$10M compensation")
            
            if result['avg_compensation'] > 500000:
                warnings.append(f"High average compensation: ${result['avg_compensation']:,.2f}")
            
            return ValidationOutcome(
                name="compensation_ranges",
                level=ValidationLevel.OPTIONAL,
                result=ValidationResult.SUCCESS if not warnings else ValidationResult.WARNING,
                message="Compensation range validation completed" if not warnings else f"Warnings: {'; '.join(warnings)}",
                details={
                    "avg_compensation": float(result['avg_compensation']),
                    "min_compensation": float(result['min_compensation']),
                    "max_compensation": float(result['max_compensation']),
                    "negative_count": int(result['negative_compensation']),
                    "extreme_count": int(result['extreme_compensation']),
                    "warnings": warnings
                },
                execution_time=0.0
            )
    
    @retry_with_exponential_backoff(
        retry_config=RetryConfig(max_retries=2),
        exceptions=(duckdb.Error,),
        validation_level=ValidationLevel.CRITICAL
    )
    def validate_snapshot_consistency(self) -> ValidationOutcome:
        """Validate consistency between snapshot and events with retry logic."""
        
        with managed_duckdb_connection(self.db_path) as conn:
            consistency_check = """
            WITH latest_year AS (
                SELECT MAX(simulation_year) as year FROM fct_workforce_snapshot
            ),
            snapshot_counts AS (
                SELECT 
                    ly.year,
                    COUNT(*) as snapshot_employees,
                    COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_in_snapshot,
                    COUNT(CASE WHEN employment_status = 'terminated' THEN 1 END) as terminated_in_snapshot
                FROM fct_workforce_snapshot ws
                CROSS JOIN latest_year ly
                WHERE ws.simulation_year = ly.year
                GROUP BY ly.year
            ),
            event_counts AS (
                SELECT 
                    ly.year,
                    COUNT(CASE WHEN UPPER(event_type) = 'HIRE' THEN 1 END) as hire_events,
                    COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) as termination_events
                FROM fct_yearly_events ye
                CROSS JOIN latest_year ly
                WHERE ye.simulation_year = ly.year
                GROUP BY ly.year
            )
            SELECT 
                sc.*,
                ec.hire_events,
                ec.termination_events,
                ABS(sc.terminated_in_snapshot - ec.termination_events) as termination_variance
            FROM snapshot_counts sc
            JOIN event_counts ec ON sc.year = ec.year
            """
            
            result = conn.execute(consistency_check).df()
            
            if result.empty:
                return ValidationOutcome(
                    name="snapshot_consistency",
                    level=ValidationLevel.CRITICAL,
                    result=ValidationResult.WARNING,
                    message="No data found for consistency validation",
                    details={},
                    execution_time=0.0
                )
            
            row = result.iloc[0]
            
            # Check for reasonable variance (within 5%)
            termination_variance_pct = (
                (row['termination_variance'] / max(row['termination_events'], 1)) * 100
                if row['termination_events'] > 0 else 0
            )
            
            issues = []
            
            if termination_variance_pct > 5.0:
                issues.append(f"High termination variance: {termination_variance_pct:.1f}%")
            
            if row['snapshot_employees'] == 0:
                issues.append("No employees in snapshot")
            
            return ValidationOutcome(
                name="snapshot_consistency",
                level=ValidationLevel.CRITICAL,
                result=ValidationResult.SUCCESS if not issues else ValidationResult.WARNING,
                message="Snapshot consistency validation completed" if not issues else f"Issues: {'; '.join(issues)}",
                details={
                    "year": int(row['year']),
                    "snapshot_employees": int(row['snapshot_employees']),
                    "active_employees": int(row['active_in_snapshot']),
                    "terminated_employees": int(row['terminated_in_snapshot']),
                    "hire_events": int(row['hire_events']),
                    "termination_events": int(row['termination_events']),
                    "termination_variance": int(row['termination_variance']),
                    "termination_variance_pct": termination_variance_pct,
                    "issues": issues
                },
                execution_time=0.0
            )
    
    def run_all_validations(self) -> List[ValidationOutcome]:
        """Run all validations with comprehensive error handling and reporting."""
        logger.info("🔍 Starting comprehensive snapshot validation with enhanced error handling")
        logger.info("=" * 80)
        
        validations = [
            ("dbt_snapshot_refresh", lambda: self.execute_dbt_command_with_retry(
                ["dbt", "run", "--select", "fct_workforce_snapshot"]
            )),
            ("snapshot_integrity", self.validate_snapshot_integrity),
            ("snapshot_consistency", self.validate_snapshot_consistency),
            ("compensation_ranges", self.validate_compensation_ranges),
        ]
        
        for validation_name, validation_func in validations:
            logger.info(f"Running validation: {validation_name}")
            
            try:
                outcome = validation_func()
                self.validation_results.append(outcome)
                
                # Log outcome
                if outcome.result == ValidationResult.SUCCESS:
                    logger.info(f"✅ {validation_name}: {outcome.message}")
                elif outcome.result == ValidationResult.WARNING:
                    logger.warning(f"⚠️  {validation_name}: {outcome.message}")
                elif outcome.result == ValidationResult.SKIPPED:
                    logger.info(f"⏭️  {validation_name}: {outcome.message}")
                else:
                    logger.error(f"❌ {validation_name}: {outcome.message}")
                
                if outcome.retry_count > 0:
                    logger.info(f"   Completed after {outcome.retry_count + 1} attempt(s)")
                
                logger.info(f"   Execution time: {outcome.execution_time:.2f}s")
                
            except Exception as e:
                # Fallback error handling
                logger.error(f"❌ Unexpected error in {validation_name}: {e}")
                outcome = ValidationOutcome(
                    name=validation_name,
                    level=ValidationLevel.CRITICAL,
                    result=ValidationResult.FAILURE,
                    message=f"Unexpected validation error: {e}",
                    details={"error": str(e), "traceback": traceback.format_exc()},
                    execution_time=0.0,
                    error=e
                )
                self.validation_results.append(outcome)
        
        return self.validation_results
    
    def generate_comprehensive_report(self) -> bool:
        """Generate comprehensive validation report with enterprise-grade details."""
        logger.info("\n📋 COMPREHENSIVE VALIDATION REPORT")
        logger.info("=" * 80)
        
        total_validations = len(self.validation_results)
        successful = sum(1 for r in self.validation_results if r.result == ValidationResult.SUCCESS)
        warnings = sum(1 for r in self.validation_results if r.result == ValidationResult.WARNING)
        failures = sum(1 for r in self.validation_results if r.result == ValidationResult.FAILURE)
        skipped = sum(1 for r in self.validation_results if r.result == ValidationResult.SKIPPED)
        
        total_execution_time = sum(r.execution_time for r in self.validation_results)
        total_retries = sum(r.retry_count for r in self.validation_results)
        
        # Summary statistics
        logger.info(f"Total validations: {total_validations}")
        logger.info(f"✅ Successful: {successful}")
        logger.info(f"⚠️  Warnings: {warnings}")
        logger.info(f"❌ Failures: {failures}")
        logger.info(f"⏭️  Skipped: {skipped}")
        logger.info(f"⏱️  Total execution time: {total_execution_time:.2f}s")
        logger.info(f"🔄 Total retries: {total_retries}")
        
        # Detailed results
        logger.info("\nDetailed Results:")
        logger.info("-" * 50)
        
        for result in self.validation_results:
            status_icon = {
                ValidationResult.SUCCESS: "✅",
                ValidationResult.WARNING: "⚠️ ",
                ValidationResult.FAILURE: "❌",
                ValidationResult.SKIPPED: "⏭️ "
            }[result.result]
            
            logger.info(f"{status_icon} {result.name} ({result.level.value})")
            logger.info(f"   Message: {result.message}")
            logger.info(f"   Time: {result.execution_time:.2f}s, Retries: {result.retry_count}")
            
            if result.details:
                for key, value in result.details.items():
                    if key not in ['traceback', 'error']:  # Skip verbose details in summary
                        logger.info(f"   {key}: {value}")
            
            if result.error and result.level == ValidationLevel.CRITICAL:
                logger.error(f"   Error: {result.error}")
        
        # Overall status
        critical_failures = sum(
            1 for r in self.validation_results 
            if r.result == ValidationResult.FAILURE and r.level == ValidationLevel.CRITICAL
        )
        
        if critical_failures == 0:
            logger.info("\n🎉 VALIDATION COMPLETED SUCCESSFULLY!")
            logger.info("All critical validations passed. System is healthy.")
            if warnings > 0:
                logger.info(f"Note: {warnings} warning(s) detected but not blocking.")
            return True
        else:
            logger.error(f"\n⚠️  VALIDATION FAILED!")
            logger.error(f"{critical_failures} critical validation(s) failed.")
            logger.error("System may not be in a stable state.")
            return False


def main():
    """Main validation orchestration with comprehensive error handling."""
    logger.info("🚀 ENHANCED SNAPSHOT VALIDATION")
    logger.info("Enterprise-grade validation with retry logic and graceful degradation")
    logger.info("=" * 80)
    
    try:
        # Initialize validator with custom retry configuration
        retry_config = RetryConfig(
            max_retries=3,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True
        )
        
        validator = SnapshotValidator(
            retry_config=retry_config,
            graceful_degradation=True
        )
        
        # Run all validations
        results = validator.run_all_validations()
        
        # Generate comprehensive report
        success = validator.generate_comprehensive_report()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Fatal error during validation: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()