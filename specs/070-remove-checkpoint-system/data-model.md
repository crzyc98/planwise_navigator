# Data Model: Remove Checkpoint/Resume System

**Date**: 2026-03-15
**Branch**: `070-remove-checkpoint-system`

## Overview

This is a code removal feature — no new entities are introduced. This document tracks the entities being removed and the surviving entity modifications.

## Entities REMOVED

### CheckpointManager
- **Removed entirely** (`checkpoint_manager.py`)
- Managed compressed checkpoint files (`.checkpoint.gz`)
- Stored: year, timestamp, database state hash, validation metrics, config snapshot
- File format: gzip-compressed JSON with integrity hashing

### RecoveryOrchestrator
- **Removed entirely** (`recovery_orchestrator.py`)
- Orchestrated resume operations from checkpoints
- Validated: config compatibility (SHA256 hash), checkpoint version, database state consistency

### WorkflowCheckpoint (dataclass)
- **Removed** from `state_manager.py`
- Fields: year, stage, timestamp, state_hash
- Serialized as `year_{N}.json`

### Checkpoint CLI Commands
- **Removed** (`checkpoint.py`)
- Commands: list, status, cleanup, validate

## Entities MODIFIED

### StateManager
- **Before**: Database cleanup + checkpoint persistence (6-8 public methods)
- **After**: Database cleanup only (4 public methods)
- **Removed methods**: `write_checkpoint()`, `find_last_checkpoint()`, `state_hash()`, `calculate_config_hash()`
- **Preserved methods**: `maybe_clear_year_data()`, `maybe_full_reset()`, `clear_year_fact_rows()`, `verify_year_population()`

### PipelineOrchestrator
- **Before**: Initializes checkpoint_manager, recovery_orchestrator; saves checkpoints after each year; supports resume
- **After**: Straightforward year loop with no checkpoint branching
- **Removed**: `_save_year_checkpoint()`, `_write_legacy_checkpoint()`, `_calculate_config_hash()`, `resume_from_checkpoint` parameter
- **Preserved**: All workflow execution, monitoring, and reporting

### OrchestratorWrapper
- **Before**: Lazy-loads checkpoint_manager and recovery_orchestrator; exposes `get_checkpoint_info()`
- **After**: Core orchestrator creation and health checks only
- **Removed**: `checkpoint_manager` property, `recovery_orchestrator` property, `get_checkpoint_info()`, checkpoint section in `get_system_status()`

## File System Artifacts

### `.planalign_checkpoints/` directory
- **Status**: No longer created or managed
- **Migration**: Existing directories are inert — users can delete manually
- **No automated cleanup needed**

## State Transitions

N/A — This feature removes state management, it does not introduce new states.
