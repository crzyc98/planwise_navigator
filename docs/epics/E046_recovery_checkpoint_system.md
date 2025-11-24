# Epic E046: Recovery & Checkpoint System

**Epic Points**: 16
**Priority**: HIGH
**Duration**: 1-2 Sprints
**Status**: ✅ Completed
**Last Updated**: August 19, 2025

## Epic Story

**As a** production operations team
**I want** robust checkpoint and recovery mechanisms for multi-year simulations
**So that** failed runs can be resumed from the last successful state without complete re-execution

## Business Context

Fidelity PlanAlign Engine currently has a **checkpoint illusion** - checkpoint files exist but provide no actual recovery capability. Multi-year simulations (2025-2029) take significant time and computational resources, making complete re-runs after mid-simulation failures extremely costly and operationally disruptive.

This epic transforms the existing checkpoint system from simple logging into a robust recovery framework capable of resuming simulations from the last successful year, maintaining state consistency, and enabling partial recovery workflows.

## Current Checkpoint Limitations

- **No recovery logic**: Checkpoint files exist but are not integrated into orchestration
- **Minimal state data**: Only stores `{"year": 2025, "stage": "cleanup", "timestamp": "...", "state_hash": "..."}`
- **No integrity validation**: No verification of checkpoint completeness or validity
- **No resume capability**: Failed simulations require complete restart
- **No state persistence**: Critical simulation state not preserved

## Epic Acceptance Criteria

### Checkpoint Enhancement
- ✅ **Comprehensive state capture** including row counts, configuration hash, and validation data
- ✅ **Integrity verification** ensuring checkpoint completeness and consistency
- ✅ **Atomic checkpoint operations** preventing corruption during save/load
- ✅ **Checkpoint compression** for efficient storage of large state data

### Recovery Framework
- ✅ **Resume capability** allowing simulation restart from last successful checkpoint
- ✅ **State validation** verifying checkpoint integrity before resume
- ✅ **Configuration drift detection** identifying when config changes invalidate checkpoints
- ✅ **Partial recovery** enabling targeted re-execution of specific years

### Operational Resilience
- ✅ **Automatic checkpoint creation** at year boundaries and critical operations
- ✅ **Checkpoint cleanup** maintaining storage efficiency with retention policies
- ✅ **Recovery documentation** with specific procedures for common failure scenarios
- ✅ **Integration testing** validating end-to-end recovery workflows

## Story Breakdown

| Story | Title | Points | Owner | Status | Dependencies |
|-------|-------|--------|-------|--------|--------------|
| **S046-01** | Enhanced Checkpoint State Capture | 5 | Platform | ✅ Completed | None |
| **S046-02** | Resume & Recovery Logic | 6 | Platform | ✅ Completed | S046-01 |
| **S046-03** | Checkpoint Integrity & Validation | 3 | Platform | ✅ Completed | S046-01 |
| **S046-04** | Recovery Documentation & Testing | 2 | Platform | ✅ Completed | S046-01,02,03 |

**Completed**: 16 points (100%) | **Remaining**: 0 points (0%)

## Technical Implementation

### Enhanced Checkpoint Manager
```python
# planalign_orchestrator/checkpoint_manager.py
import json
import hashlib
import gzip
import duckdb
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

class CheckpointManager:
    def __init__(self, checkpoint_dir: str = ".navigator_checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def save_checkpoint(self, year: int, run_id: str, config_hash: str) -> Dict[str, Any]:
        """Save comprehensive checkpoint with full state validation"""

        # Gather comprehensive state data
        checkpoint_data = {
            'metadata': {
                'year': year,
                'run_id': run_id,
                'timestamp': datetime.now().isoformat(),
                'config_hash': config_hash,
                'checkpoint_version': '2.0'
            },
            'database_state': self._capture_database_state(year),
            'validation_data': self._capture_validation_data(year),
            'performance_metrics': self._capture_performance_metrics(year),
            'configuration_snapshot': self._capture_configuration()
        }

        # Add integrity hash
        checkpoint_data['integrity_hash'] = self._calculate_integrity_hash(checkpoint_data)

        # Save with atomic operations
        return self._save_atomic_checkpoint(year, checkpoint_data)

    def _capture_database_state(self, year: int) -> Dict[str, Any]:
        """Capture comprehensive database state for the year"""
        with duckdb.connect("simulation.duckdb") as conn:
            state = {
                'table_counts': {},
                'data_quality_metrics': {},
                'key_aggregates': {}
            }

            # Critical table row counts
            tables = ['fct_yearly_events', 'fct_workforce_snapshot', 'int_employee_contributions']
            for table in tables:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE simulation_year = ?", [year]).fetchone()[0]
                    state['table_counts'][table] = count
                except Exception as e:
                    state['table_counts'][table] = f"ERROR: {str(e)}"

            # Data quality metrics
            try:
                # Check for duplicate events
                duplicate_count = conn.execute("""
                    SELECT COUNT(*) FROM (
                        SELECT employee_id, simulation_year, event_type, effective_date
                        FROM fct_yearly_events
                        WHERE simulation_year = ?
                        GROUP BY employee_id, simulation_year, event_type, effective_date
                        HAVING COUNT(*) > 1
                    )
                """, [year]).fetchone()[0]
                state['data_quality_metrics']['duplicate_events'] = duplicate_count

                # Check workforce balance
                workforce_count = conn.execute(
                    "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year]
                ).fetchone()[0]
                state['data_quality_metrics']['workforce_count'] = workforce_count

            except Exception as e:
                state['data_quality_metrics']['error'] = str(e)

            return state

    def _capture_validation_data(self, year: int) -> Dict[str, Any]:
        """Capture validation checksums and key metrics"""
        with duckdb.connect("simulation.duckdb") as conn:
            validation = {}

            try:
                # Event type distribution
                event_dist = conn.execute("""
                    SELECT event_type, COUNT(*)
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                    GROUP BY event_type
                """, [year]).fetchall()
                validation['event_distribution'] = dict(event_dist)

                # Compensation totals
                comp_total = conn.execute("""
                    SELECT SUM(total_compensation)
                    FROM fct_workforce_snapshot
                    WHERE simulation_year = ?
                """, [year]).fetchone()[0]
                validation['total_compensation'] = float(comp_total) if comp_total else 0

                # Contribution totals
                contrib_total = conn.execute("""
                    SELECT SUM(annual_contribution_amount)
                    FROM int_employee_contributions
                    WHERE simulation_year = ?
                """, [year]).fetchone()[0]
                validation['total_contributions'] = float(contrib_total) if contrib_total else 0

            except Exception as e:
                validation['error'] = str(e)

            return validation

    def _save_atomic_checkpoint(self, year: int, checkpoint_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save checkpoint with atomic operations and compression"""

        # Serialize and compress
        json_data = json.dumps(checkpoint_data, indent=2)
        compressed_data = gzip.compress(json_data.encode('utf-8'))

        # Write to temporary file first
        temp_path = self.checkpoint_dir / f"year_{year}.checkpoint.tmp"
        final_path = self.checkpoint_dir / f"year_{year}.checkpoint.gz"

        # Atomic write
        with open(temp_path, 'wb') as f:
            f.write(compressed_data)

        # Atomic rename
        temp_path.rename(final_path)

        # Update latest checkpoint link
        latest_path = self.checkpoint_dir / "latest_checkpoint.gz"
        if latest_path.exists():
            latest_path.unlink()
        latest_path.symlink_to(final_path.name)

        return checkpoint_data

    def load_checkpoint(self, year: int) -> Optional[Dict[str, Any]]:
        """Load and validate checkpoint for specific year"""
        checkpoint_path = self.checkpoint_dir / f"year_{year}.checkpoint.gz"

        if not checkpoint_path.exists():
            return None

        try:
            # Load compressed checkpoint
            with open(checkpoint_path, 'rb') as f:
                compressed_data = f.read()

            json_data = gzip.decompress(compressed_data).decode('utf-8')
            checkpoint_data = json.loads(json_data)

            # Validate integrity
            if not self._validate_checkpoint_integrity(checkpoint_data):
                raise ValueError(f"Checkpoint integrity validation failed for year {year}")

            return checkpoint_data

        except Exception as e:
            print(f"Error loading checkpoint for year {year}: {e}")
            return None

    def can_resume_from_year(self, year: int, current_config_hash: str) -> bool:
        """Check if simulation can safely resume from specified year"""
        checkpoint = self.load_checkpoint(year)

        if not checkpoint:
            return False

        # Check configuration compatibility
        checkpoint_config_hash = checkpoint['metadata'].get('config_hash')
        if checkpoint_config_hash != current_config_hash:
            print(f"Configuration changed since checkpoint. Checkpoint: {checkpoint_config_hash}, Current: {current_config_hash}")
            return False

        # Validate database state matches checkpoint
        return self._validate_database_consistency(year, checkpoint)

    def find_latest_resumable_checkpoint(self, current_config_hash: str) -> Optional[int]:
        """Find the latest year that can be safely resumed from"""
        checkpoint_files = list(self.checkpoint_dir.glob("year_*.checkpoint.gz"))

        # Extract years and sort in descending order
        years = []
        for file_path in checkpoint_files:
            try:
                year = int(file_path.stem.split('_')[1].split('.')[0])
                years.append(year)
            except (ValueError, IndexError):
                continue

        years.sort(reverse=True)

        # Find latest resumable year
        for year in years:
            if self.can_resume_from_year(year, current_config_hash):
                return year

        return None
```

### Recovery Orchestration
```python
# planalign_orchestrator/recovery_orchestrator.py
from typing import Optional, List
import logging

class RecoveryOrchestrator:
    def __init__(self, checkpoint_manager: CheckpointManager, logger):
        self.checkpoint_manager = checkpoint_manager
        self.logger = logger

    def resume_simulation(self, target_end_year: int, config_hash: str) -> bool:
        """Resume simulation from latest valid checkpoint"""

        # Find resumption point
        resume_year = self.checkpoint_manager.find_latest_resumable_checkpoint(config_hash)

        if not resume_year:
            self.logger.warning("No valid checkpoint found. Starting from beginning.")
            return False

        self.logger.info(f"Resuming simulation from year {resume_year}")

        # Validate resume point
        checkpoint = self.checkpoint_manager.load_checkpoint(resume_year)
        if not self._validate_resume_conditions(checkpoint):
            self.logger.error(f"Resume validation failed for year {resume_year}")
            return False

        # Log resume context
        self.logger.info("Resume validation successful",
                        resume_year=resume_year,
                        target_end_year=target_end_year,
                        checkpoint_timestamp=checkpoint['metadata']['timestamp'])

        return True

    def _validate_resume_conditions(self, checkpoint: Dict[str, Any]) -> bool:
        """Validate that resume conditions are met"""

        # Check database state consistency
        year = checkpoint['metadata']['year']
        expected_counts = checkpoint['database_state']['table_counts']

        with duckdb.connect("simulation.duckdb") as conn:
            for table, expected_count in expected_counts.items():
                if isinstance(expected_count, str) and "ERROR" in expected_count:
                    continue  # Skip tables that had errors during checkpoint

                try:
                    actual_count = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE simulation_year = ?",
                        [year]
                    ).fetchone()[0]

                    if actual_count != expected_count:
                        self.logger.error(f"Database inconsistency: {table} has {actual_count} rows, expected {expected_count}")
                        return False

                except Exception as e:
                    self.logger.error(f"Error validating table {table}: {e}")
                    return False

        return True
```

## Integration with Navigator CLI

```python
# planalign_orchestrator/cli.py - Enhanced run command
@click.command()
@click.option('--years', help='Year range (e.g., 2025-2029)')
@click.option('--resume', is_flag=True, help='Resume from latest checkpoint')
@click.option('--force-restart', is_flag=True, help='Ignore checkpoints and start fresh')
def run(years: str, resume: bool, force_restart: bool):
    """Run multi-year simulation with checkpoint support"""

    start_year, end_year = parse_year_range(years)
    checkpoint_manager = CheckpointManager()
    recovery_orchestrator = RecoveryOrchestrator(checkpoint_manager, logger)

    # Calculate configuration hash
    config_hash = calculate_config_hash()

    # Determine starting point
    if force_restart:
        actual_start_year = start_year
        logger.info(f"Force restart: ignoring checkpoints, starting from {start_year}")
    elif resume:
        resume_year = recovery_orchestrator.resume_simulation(end_year, config_hash)
        actual_start_year = resume_year + 1 if resume_year else start_year
        logger.info(f"Resume mode: starting from year {actual_start_year}")
    else:
        actual_start_year = start_year

    # Execute simulation with checkpointing
    for year in range(actual_start_year, end_year + 1):
        try:
            logger.info(f"Processing year {year}")

            # Execute year simulation
            run_year_simulation(year)

            # Create checkpoint
            checkpoint_data = checkpoint_manager.save_checkpoint(year, run_id, config_hash)
            logger.info(f"Checkpoint saved for year {year}",
                       checkpoint_size=len(str(checkpoint_data)))

        except Exception as e:
            logger.error(f"Year {year} failed: {e}")
            logger.info(f"Simulation can be resumed with --resume flag")
            raise
```

## Success Metrics

### Recovery Capability
- **Resume success rate**: 100% successful resumes from valid checkpoints
- **Resume time**: <2 minutes to validate and resume from checkpoint
- **State consistency**: 100% database state matches checkpoint validation
- **Configuration drift detection**: 100% detection of incompatible configurations

### Checkpoint Efficiency
- **Checkpoint size**: <10MB per year checkpoint (compressed)
- **Checkpoint creation time**: <30 seconds per checkpoint
- **Storage management**: Automated cleanup maintaining <100MB total storage
- **Integrity validation**: 100% checkpoint integrity verification

### Operational Resilience
- **Mid-run failure recovery**: <5 minutes to resume after failure
- **Documentation coverage**: Complete procedures for all failure scenarios
- **Test coverage**: 100% automated testing of recovery workflows

## Definition of Done

- ✅ **Enhanced checkpoint system** capturing comprehensive state data
- ✅ **Resume capability** enabling restart from last successful checkpoint
- ✅ **Integrity validation** ensuring checkpoint consistency and completeness
- ✅ **Configuration drift detection** preventing invalid resumes
- ✅ **CLI integration** with --resume and --force-restart options
- ✅ **Comprehensive testing** validating all recovery scenarios
- ✅ **Documentation** with specific recovery procedures

## Implementation Summary

Epic E046 has been successfully completed with the following deliverables:

### Core Components Implemented

1. **CheckpointManager** (`planalign_orchestrator/checkpoint_manager.py`)
   - Comprehensive state capture including database state, validation data, and performance metrics
   - SHA-256 integrity validation with atomic save operations
   - Gzip compression for efficient storage
   - Backward compatibility with legacy checkpoint format

2. **RecoveryOrchestrator** (`planalign_orchestrator/recovery_orchestrator.py`)
   - Intelligent resume logic with configuration drift detection
   - Recovery validation and environment checking
   - Comprehensive recovery status reporting and planning

3. **Enhanced CLI Integration** (`planalign_orchestrator/cli.py`)
   - `--resume` and `--force-restart` options for simulation runs
   - `checkpoint` subcommand with list, status, cleanup, and validate actions
   - Verbose recovery information and recommendations

4. **Pipeline Integration** (`planalign_orchestrator/pipeline.py`)
   - Enhanced checkpoint creation at year boundaries
   - Automatic fallback to legacy system when needed
   - Configuration hash calculation and tracking

### Testing and Documentation

1. **Comprehensive Test Suite** (`tests/test_checkpoint_recovery.py`)
   - 25+ test cases covering all recovery scenarios
   - Integration tests for complete workflow validation
   - Error handling and edge case coverage

2. **Recovery Procedures** (`docs/recovery_procedures.md`)
   - Complete operational guide with common scenarios
   - Troubleshooting procedures and best practices
   - Technical reference and CLI examples

### Key Features Delivered

- **100% Success Rate**: All acceptance criteria met
- **Backward Compatible**: Seamless integration with existing checkpoints
- **Production Ready**: Comprehensive error handling and validation
- **Operationally Resilient**: Automatic cleanup and environment validation
- **Well Documented**: Complete procedures for all failure scenarios

The enhanced checkpoint and recovery system transforms Fidelity PlanAlign Engine from a checkpoint illusion into a robust recovery framework, meeting all Epic E046 objectives.

## Recovery Procedures Documentation

### Common Recovery Scenarios

#### Scenario 1: Mid-Simulation Failure
```bash
# Simulation failed at year 2027
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
# Automatically resumes from year 2026 (last successful checkpoint)
```

#### Scenario 2: Configuration Change
```bash
# Configuration changed, checkpoints incompatible
python -m planalign_orchestrator.cli run --years 2025-2029 --force-restart
# Ignores existing checkpoints and starts fresh
```

#### Scenario 3: Database Corruption
```bash
# Restore from backup and resume
cp backups/latest.duckdb simulation.duckdb
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
```

## Related Epics

- **E043**: Production Data Safety & Backup System (provides backup foundation)
- **E044**: Production Observability & Logging Framework (logs checkpoint operations)
- **E045**: Data Integrity Issues Resolution (ensures clean checkpoints)
- **E047**: Production Testing & Validation Framework (tests recovery workflows)

---

**Implementation Note**: This epic builds on the backup system (E043) and logging framework (E044) to provide comprehensive recovery capabilities for production operations.
