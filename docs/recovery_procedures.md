# Fidelity PlanAlign Engine Recovery Procedures

Comprehensive guide for checkpoint management and simulation recovery operations.

## Table of Contents

1. [Overview](#overview)
2. [Quick Recovery Guide](#quick-recovery-guide)
3. [Checkpoint Management](#checkpoint-management)
4. [Recovery Scenarios](#recovery-scenarios)
5. [Troubleshooting](#troubleshooting)
6. [Best Practices](#best-practices)
7. [Technical Reference](#technical-reference)

---

## Overview

The Fidelity PlanAlign Engine Recovery & Checkpoint System provides robust recovery capabilities for multi-year simulations. The system automatically creates comprehensive checkpoints at year boundaries and enables resuming simulations from the last successful state.

### Key Features

- **Comprehensive State Capture**: Database state, validation metrics, and configuration snapshots
- **Integrity Validation**: SHA-256 checksums ensure checkpoint consistency
- **Configuration Drift Detection**: Prevents invalid resumes when configuration changes
- **Atomic Operations**: Checkpoint creation is atomic to prevent corruption
- **Compression**: Efficient storage with gzip compression
- **Multiple Recovery Modes**: Resume, force restart, and validation options

---

## Quick Recovery Guide

### Resume After Failure

If your simulation fails mid-run:

```bash
# Resume from the latest valid checkpoint
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
```

### Force Fresh Start

If you need to ignore all checkpoints and start fresh:

```bash
# Start fresh, ignoring any existing checkpoints
python -m planalign_orchestrator.cli run --years 2025-2029 --force-restart
```

### Check Recovery Status

Before starting a simulation, check what recovery options are available:

```bash
# View recovery status and recommendations
python -m planalign_orchestrator.cli checkpoint status
```

---

## Checkpoint Management

### Viewing Checkpoints

```bash
# List all available checkpoints
python -m planalign_orchestrator.cli checkpoint list

# Show recovery status and recommendations
python -m planalign_orchestrator.cli checkpoint status

# Validate recovery environment
python -m planalign_orchestrator.cli checkpoint validate
```

Example output:
```
Found 3 checkpoint(s):
  ✅ Year 2025: 2025-08-19T10:30:45.123456 (compressed, 52480 bytes)
  ✅ Year 2026: 2025-08-19T11:45:22.789012 (compressed, 54720 bytes)
  ✅ Year 2027: 2025-08-19T13:02:15.456789 (compressed, 56960 bytes)
```

### Cleaning Up Old Checkpoints

```bash
# Keep only the latest 5 checkpoints (default)
python -m planalign_orchestrator.cli checkpoint cleanup

# Keep only the latest 3 checkpoints
python -m planalign_orchestrator.cli checkpoint cleanup --keep 3
```

### Checkpoint Storage

Checkpoints are stored in `.navigator_checkpoints/` directory:

```
.navigator_checkpoints/
├── year_2025.checkpoint.gz    # Compressed checkpoint (preferred)
├── year_2025.json            # Legacy format (compatibility)
├── year_2026.checkpoint.gz
├── year_2026.json
└── latest_checkpoint.gz      # Symlink to latest checkpoint
```

---

## Recovery Scenarios

### Scenario 1: Mid-Simulation Failure

**Situation**: Simulation fails at year 2027 of a 2025-2029 run.

**Solution**:
```bash
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
```

**What happens**:
- System finds the latest valid checkpoint (2026)
- Validates checkpoint integrity and configuration compatibility
- Resumes simulation from year 2027
- Saves time by skipping already-completed years

### Scenario 2: Configuration Changes

**Situation**: You modified configuration parameters since the last run.

**Solution**: Check compatibility first, then decide:
```bash
# Check if existing checkpoints are compatible
python -m planalign_orchestrator.cli checkpoint status

# If incompatible, start fresh
python -m planalign_orchestrator.cli run --years 2025-2029 --force-restart
```

**Configuration drift detection**: The system calculates a hash of your configuration file. If it changes between checkpoint creation and resume, the checkpoint is considered invalid.

### Scenario 3: Database Corruption

**Situation**: Database file is corrupted or missing.

**Solution**:
```bash
# 1. Restore database from backup
cp backups/simulation_backup_2025-08-19.duckdb simulation.duckdb

# 2. Validate recovery environment
python -m planalign_orchestrator.cli checkpoint validate

# 3. Resume if validation passes
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
```

### Scenario 4: Checkpoint Corruption

**Situation**: Latest checkpoint file is corrupted.

**Solution**: The system automatically falls back to the previous valid checkpoint:
```bash
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
```

**What happens**:
- System attempts to load the latest checkpoint (2027)
- Detects corruption and moves to previous checkpoint (2026)
- Resumes simulation from year 2027
- Issues warning about corrupted checkpoint

### Scenario 5: Selective Year Re-execution

**Situation**: You need to re-run specific years due to data issues.

**Solution**:
```bash
# Method 1: Delete specific checkpoints and resume
rm .navigator_checkpoints/year_2027.*
rm .navigator_checkpoints/year_2028.*
python -m planalign_orchestrator.cli run --years 2025-2029 --resume

# Method 2: Force restart from specific year
python -m planalign_orchestrator.cli run --start-year 2027 --end-year 2029 --force-restart
```

### Scenario 6: Extending Completed Simulation

**Situation**: Simulation completed 2025-2027, now need to extend to 2029.

**Solution**:
```bash
python -m planalign_orchestrator.cli run --years 2025-2029 --resume
```

**What happens**:
- System finds checkpoint for 2027
- Resumes from 2028 (next year after checkpoint)
- Runs years 2028-2029 only

---

## Troubleshooting

### Common Issues

#### Issue: "No valid checkpoint found"

**Causes**:
- No checkpoints exist
- Configuration has changed since checkpoint creation
- All checkpoints are corrupted

**Solutions**:
```bash
# Check what checkpoints exist
python -m planalign_orchestrator.cli checkpoint list

# Check recovery status for recommendations
python -m planalign_orchestrator.cli checkpoint status

# If configuration changed, start fresh
python -m planalign_orchestrator.cli run --years 2025-2029 --force-restart
```

#### Issue: "Database inconsistency detected"

**Causes**:
- Database was modified outside the simulation
- Manual data changes after checkpoint creation
- Database corruption

**Solutions**:
```bash
# Validate the recovery environment
python -m planalign_orchestrator.cli checkpoint validate

# Check specific inconsistency details in logs
# Restore from backup if necessary
# Use --force-restart if validation fails
```

#### Issue: "Checkpoint integrity validation failed"

**Causes**:
- Checkpoint file corruption
- Manual modification of checkpoint files
- File system issues

**Solutions**:
```bash
# System will automatically try previous checkpoints
python -m planalign_orchestrator.cli run --years 2025-2029 --resume

# If all checkpoints are corrupt, start fresh
python -m planalign_orchestrator.cli run --years 2025-2029 --force-restart

# Clean up corrupt checkpoints
python -m planalign_orchestrator.cli checkpoint cleanup
```

### Debug Information

Enable verbose mode for detailed recovery information:

```bash
python -m planalign_orchestrator.cli run --years 2025-2029 --resume --verbose
```

Verbose output includes:
- Configuration hash comparison
- Checkpoint validation details
- Recovery plan information
- Database consistency checks

### Log Files

Recovery operations are logged to the standard Python logging system. Key log messages include:

- `INFO`: Successful operations and recovery status
- `WARNING`: Configuration drift or minor issues
- `ERROR`: Failed operations requiring attention

---

## Best Practices

### Regular Maintenance

1. **Monitor checkpoint storage**: Run cleanup regularly to manage disk space
   ```bash
   python -m planalign_orchestrator.cli checkpoint cleanup --keep 10
   ```

2. **Validate environment before long runs**:
   ```bash
   python -m planalign_orchestrator.cli checkpoint validate
   ```

3. **Check recovery status when resuming**:
   ```bash
   python -m planalign_orchestrator.cli checkpoint status
   ```

### Configuration Management

1. **Track configuration changes**: Document when and why configuration changes
2. **Backup configurations**: Keep copies of configurations used for important runs
3. **Use version control**: Store configuration files in git for change tracking

### Backup Strategy

1. **Database backups**: Regular backups of `simulation.duckdb`
2. **Checkpoint backups**: Include `.navigator_checkpoints/` in backup rotation
3. **Configuration backups**: Backup `config/simulation_config.yaml`

### Development Workflow

1. **Use checkpoints during development**: Saves time when testing changes
2. **Clean up test checkpoints**: Use `cleanup` command after testing
3. **Force restart for major changes**: Use `--force-restart` when testing significant modifications

---

## Technical Reference

### Checkpoint Data Structure

Enhanced checkpoints contain:

```json
{
  "metadata": {
    "year": 2025,
    "run_id": "multiyear_20250819_103045",
    "timestamp": "2025-08-19T10:30:45.123456",
    "config_hash": "a1b2c3d4e5f6...",
    "checkpoint_version": "2.0"
  },
  "database_state": {
    "table_counts": {
      "fct_yearly_events": 1250,
      "fct_workforce_snapshot": 1000,
      "int_employee_contributions": 800
    },
    "data_quality_metrics": {
      "duplicate_events": 0,
      "workforce_count": 1000,
      "event_type_distribution": {
        "hire": 50,
        "termination": 30,
        "promotion": 25
      }
    }
  },
  "validation_data": {
    "event_distribution": {...},
    "total_compensation": 75000000.00,
    "total_contributions": 5000000.00,
    "baseline_employee_count": 1000,
    "total_hires_needed": 50
  },
  "performance_metrics": {
    "checkpoint_creation_time": "2025-08-19T10:30:45.123456",
    "database_size_blocks": 12500,
    "total_tables": 45
  },
  "configuration_snapshot": {
    "checkpoint_version": "2.0",
    "database_path": "simulation.duckdb",
    "simulation_config_exists": true
  },
  "integrity_hash": "sha256_hash_of_above_data"
}
```

### Configuration Hash Calculation

The system calculates configuration hashes by:

1. Reading `config/simulation_config.yaml`
2. Computing SHA-256 hash of file contents
3. Storing hash in checkpoint metadata
4. Comparing hashes during resume validation

### Recovery Validation Process

When resuming, the system:

1. **Finds latest checkpoint**: Scans for valid checkpoint files
2. **Loads checkpoint data**: Decompresses and parses checkpoint
3. **Validates integrity**: Verifies SHA-256 hash
4. **Checks configuration**: Compares configuration hashes
5. **Validates database state**: Confirms table counts match
6. **Returns resume point**: Year after latest valid checkpoint

### CLI Integration

The enhanced recovery system integrates with the existing CLI:

- `--resume`: Use enhanced recovery if available, fall back to legacy
- `--force-restart`: Explicitly ignore all checkpoints
- `--verbose`: Show detailed recovery information
- `checkpoint` subcommand: Manage checkpoints and recovery status

### Backward Compatibility

The system maintains backward compatibility:

- **Legacy checkpoints**: Old `.json` files are still supported
- **Graceful fallback**: Enhanced system falls back to legacy when needed
- **Automatic migration**: Creates both enhanced and legacy formats

---

## Support and Maintenance

### Getting Help

1. **Check status first**: `python -m planalign_orchestrator.cli checkpoint status`
2. **Validate environment**: `python -m planalign_orchestrator.cli checkpoint validate`
3. **Use verbose mode**: Add `--verbose` to see detailed information
4. **Check logs**: Review Python logging output for error details

### Reporting Issues

When reporting checkpoint/recovery issues, include:

1. Output of `checkpoint status` command
2. Output of `checkpoint validate` command
3. Relevant log messages
4. Configuration file (if safe to share)
5. Steps to reproduce the issue

### Version Information

This recovery system is part of Epic E046 and provides:

- Checkpoint format version 2.0
- Enhanced state capture and validation
- Comprehensive recovery procedures
- Backward compatibility with legacy checkpoints

---

*Last updated: August 19, 2025*
*Epic E046: Recovery & Checkpoint System*
