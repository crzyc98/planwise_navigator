# E083: Workspace Cloud Synchronization

## Overview

Enable synchronization of PlanAlign workspaces across multiple machines, providing users with:
- Complete history of all scenarios run in a workspace
- Access to outputs, configurations, and run metadata from any device
- Version-controlled scenario evolution via Git
- Team collaboration on shared workspaces

## Problem Statement

Currently, all workspace data is stored locally at `~/.planalign/workspaces/`. Users working across multiple machines (e.g., laptop and workstation) cannot:
- See their scenario history from another device
- Continue work started on a different machine
- Share workspace configurations with teammates
- Maintain a versioned backup of their simulation work

## Goals

1. **Cross-Device Access**: Access workspace history and configurations from any machine
2. **Selective Sync**: Sync metadata and configs efficiently; regenerate large outputs on-demand
3. **Version Control**: Track scenario evolution over time with meaningful commit history
4. **Team Collaboration**: Share workspaces with team members (optional future phase)
5. **Offline-First**: Work locally without network; sync when convenient

## Non-Goals (Out of Scope)

- Real-time collaborative editing (Google Docs-style)
- Syncing simulation databases (too large, easily regenerated)
- Conflict resolution for concurrent edits (first phase uses last-write-wins)
- Hosting/managing Git repositories (users bring their own)

---

## Technical Analysis

### Current Workspace Structure

```
~/.planalign/workspaces/
├── {workspace_id}/
│   ├── workspace.json           # ~1 KB - Workspace metadata
│   ├── base_config.yaml         # ~2 KB - Default configuration
│   ├── scenarios/
│   │   ├── {scenario_id}/
│   │   │   ├── scenario.json    # ~2 KB - Scenario metadata
│   │   │   ├── config.yaml      # ~3 KB - Merged configuration
│   │   │   ├── simulation.duckdb    # 50-500 MB - EXCLUDE
│   │   │   ├── results/
│   │   │   │   ├── *.xlsx       # 1-10 MB each - EXCLUDE (regenerable)
│   │   │   │   └── run_metadata.json  # ~1 KB - Include
│   │   │   └── runs/
│   │   │       └── {run_id}/
│   │   │           ├── run_metadata.json  # ~1 KB - Include
│   │   │           └── config.yaml        # ~3 KB - Include
```

### What to Sync

| Data Type | Size | Sync? | Rationale |
|-----------|------|-------|-----------|
| `workspace.json` | ~1 KB | Yes | Essential metadata |
| `base_config.yaml` | ~2 KB | Yes | Workspace defaults |
| `scenario.json` | ~2 KB | Yes | Scenario definitions |
| `config.yaml` | ~3 KB | Yes | Audit trail of configs used |
| `run_metadata.json` | ~1 KB | Yes | Run history and metrics |
| `simulation.duckdb` | 50-500 MB | No | Regenerable from config |
| `*.xlsx` exports | 1-10 MB | No | Regenerable on demand |

**Estimated sync size per workspace**: 50-200 KB (text files only)

### Storage Backend Options

#### Option A: GitHub Repository (Recommended)

**Pros:**
- Free for private repos (up to 500 MB, unlimited repos)
- Built-in version control and history
- Familiar workflow for developers
- Works with existing Git tooling
- Supports GitHub Actions for automation

**Cons:**
- Requires GitHub account
- 100 MB file size limit (not an issue for metadata)
- Learning curve for non-technical users

**Implementation:**
```
~/.planalign/workspaces/
├── .git/                        # Git repository
├── .gitignore                   # Exclude *.duckdb, *.xlsx
├── {workspace_id}/
│   └── ... (synced files only)
```

#### Option B: Cloud Storage (S3/GCS/Azure)

**Pros:**
- No file size limits
- Could sync databases if needed
- Works for non-Git users

**Cons:**
- Requires cloud account setup
- No built-in versioning (would need to implement)
- More complex authentication
- Ongoing storage costs

#### Option C: Dedicated Sync Service

**Pros:**
- Purpose-built for the use case
- Could handle conflicts intelligently
- Best user experience

**Cons:**
- Significant development effort
- Requires backend infrastructure
- Ongoing hosting costs

### Recommendation: Start with GitHub

GitHub provides the best balance of features, cost (free), and implementation simplicity. The workspace data is small and text-based, making it ideal for Git.

---

## Proposed Architecture

### Sync Components

```
┌─────────────────────────────────────────────────────────────┐
│                      PlanAlign Studio                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │  Workspace  │    │    Sync     │    │   Git Client    │ │
│  │   Storage   │◄──►│   Service   │◄──►│   (libgit2)     │ │
│  └─────────────┘    └─────────────┘    └─────────────────┘ │
│         │                  │                    │           │
│         ▼                  ▼                    ▼           │
│  ~/.planalign/      Conflict         GitHub/GitLab/etc.     │
│   workspaces/       Resolution                              │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Local Changes**: User creates/modifies scenarios locally
2. **Auto-Stage**: Sync service detects changes to JSON/YAML files
3. **Push**: User initiates sync (or on schedule)
4. **Pull**: On startup/request, fetch remote changes
5. **Merge**: Apply remote changes to local workspace

### File Structure for Synced Workspaces

```
~/.planalign/workspaces/
├── .git/
├── .gitignore
├── .planalign-sync.yaml          # Sync configuration
├── {workspace_id}/
│   ├── workspace.json
│   ├── base_config.yaml
│   └── scenarios/
│       └── {scenario_id}/
│           ├── scenario.json
│           ├── config.yaml
│           └── runs/
│               └── {run_id}/
│                   ├── run_metadata.json
│                   └── config.yaml
```

### `.gitignore` Template

```gitignore
# Exclude large/regenerable files
*.duckdb
*.xlsx
*.parquet

# Exclude temporary files
*.tmp
*.lock
__pycache__/

# Keep metadata
!**/run_metadata.json
!**/scenario.json
!**/workspace.json
!**/*.yaml
```

### `.planalign-sync.yaml` Configuration

```yaml
version: 1
sync:
  enabled: true
  remote: "git@github.com:user/planalign-workspaces.git"
  branch: "main"
  auto_sync: false  # Manual sync by default

  # What to sync
  include:
    - "**/*.json"
    - "**/*.yaml"
  exclude:
    - "*.duckdb"
    - "*.xlsx"

  # Conflict resolution
  conflict_strategy: "last-write-wins"  # or "ask-user", "keep-local", "keep-remote"
```

---

## User Experience

### CLI Commands

```bash
# Initialize sync for workspaces
planalign sync init
# > Enter GitHub repository URL: git@github.com:user/planalign-workspaces.git
# > Sync initialized. Use 'planalign sync push' to upload workspaces.

# Push local changes to remote
planalign sync push
# > Pushing changes to origin/main...
# > Synced 3 workspaces (12 scenarios, 45 runs)

# Pull remote changes
planalign sync pull
# > Pulling from origin/main...
# > Updated 2 workspaces with new scenarios

# Check sync status
planalign sync status
# > Local:  3 workspaces, 12 scenarios
# > Remote: 3 workspaces, 14 scenarios
# > Behind: 2 scenarios need to be pulled

# View sync history
planalign sync log
# > 2025-12-02 10:30: Pushed "Q4 Projections" scenario
# > 2025-12-01 15:45: Pulled 3 new scenarios from remote
# > 2025-12-01 09:00: Initial sync established

# Disconnect sync
planalign sync disconnect
# > Sync disconnected. Local workspaces preserved.
```

### Studio UI Integration

```
┌─────────────────────────────────────────────────────────────┐
│  Workspaces                                    [Sync ↻]     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  📁 Q4 2025 Projections           [↑ 2 changes]        │ │
│  │      3 scenarios · Last run: 2 hours ago                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  📁 Annual Planning                [✓ Synced]          │ │
│  │      5 scenarios · Last run: yesterday                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  📁 Headcount Analysis             [↓ Pull available]  │ │
│  │      2 scenarios · Last run: 3 days ago                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Sync Status Icons

| Icon | Meaning |
|------|---------|
| `✓` | Synced - local matches remote |
| `↑` | Push needed - local changes to upload |
| `↓` | Pull needed - remote changes to download |
| `⚠` | Conflict - manual resolution needed |
| `○` | Not synced - local only |

---

## Implementation Plan

### Phase 1: Foundation (Stories 1-4)

**S083-01: Create SyncService Core**
- Create `planalign_api/services/sync_service.py`
- Implement workspace directory scanning
- Create `.gitignore` template generation
- Add `.planalign-sync.yaml` configuration model

**S083-02: Implement Git Integration**
- Add `pygit2` or `GitPython` dependency
- Implement repository initialization
- Add remote configuration
- Implement push/pull operations

**S083-03: Add CLI Sync Commands**
- Add `planalign sync init` command
- Add `planalign sync push` command
- Add `planalign sync pull` command
- Add `planalign sync status` command
- Add `planalign sync log` command

**S083-04: Handle Sync Conflicts**
- Detect conflicting changes
- Implement last-write-wins resolution
- Add conflict logging and notification
- Preserve conflicting versions as backups

### Phase 2: Studio Integration (Stories 5-7)

**S083-05: Add Sync Status API Endpoints**
- `GET /api/sync/status` - Current sync state
- `POST /api/sync/push` - Trigger push
- `POST /api/sync/pull` - Trigger pull
- `GET /api/sync/log` - Sync history

**S083-06: Add Sync UI Components**
- Add sync status indicators to workspace cards
- Add sync button to workspace list header
- Create sync settings modal
- Add sync progress indicator

**S083-07: Implement Auto-Sync (Optional)**
- Detect file changes with watchdog
- Auto-push on scenario completion
- Auto-pull on Studio startup
- Configurable sync frequency

### Phase 3: Advanced Features (Stories 8-10)

**S083-08: Add Selective Sync**
- Allow excluding specific workspaces from sync
- Add per-workspace sync settings
- Support multiple remotes (personal + team)

**S083-09: Add Run Regeneration**
- Detect missing simulation databases
- Offer to regenerate from synced config
- Queue regeneration jobs
- Track regeneration progress

**S083-10: Add Team Collaboration Features**
- Support multiple branches per workspace
- Add workspace sharing via URL
- Implement workspace import from remote
- Add contributor tracking

---

## Technical Details

### Dependencies to Add

```toml
# pyproject.toml
[project.dependencies]
GitPython = "^3.1.0"  # or pygit2 for lower-level control
watchdog = "^4.0.0"   # For file change detection (optional)
```

### New Models

```python
# planalign_api/models/sync.py
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime

class SyncConfig(BaseModel):
    """Sync configuration for a workspace directory."""
    enabled: bool = False
    remote: Optional[str] = None
    branch: str = "main"
    auto_sync: bool = False
    conflict_strategy: Literal["last-write-wins", "ask-user", "keep-local", "keep-remote"] = "last-write-wins"

class SyncStatus(BaseModel):
    """Current sync status."""
    is_initialized: bool
    remote_url: Optional[str]
    local_changes: int  # Number of uncommitted changes
    ahead: int          # Commits ahead of remote
    behind: int         # Commits behind remote
    last_sync: Optional[datetime]
    conflicts: list[str] = []

class SyncLogEntry(BaseModel):
    """A sync operation log entry."""
    timestamp: datetime
    operation: Literal["push", "pull", "init", "conflict"]
    workspaces_affected: int
    scenarios_affected: int
    message: str
```

### Error Handling

```python
# planalign_orchestrator/exceptions.py (additions)

class SyncError(NavigatorError):
    """Base exception for sync operations."""
    pass

class SyncAuthError(SyncError):
    """Authentication failed with remote."""
    pass

class SyncConflictError(SyncError):
    """Conflict detected during sync."""
    conflicting_files: list[str]

class SyncNetworkError(SyncError):
    """Network error during sync."""
    pass
```

---

## Migration Path

### For Existing Users

1. **No Breaking Changes**: Existing local workspaces continue to work
2. **Opt-In Sync**: Users explicitly initialize sync when ready
3. **Preserve History**: Existing run history is synced on first push

### For New Users

1. **Guided Setup**: Studio prompts to configure sync on first workspace
2. **Quick Start**: One-command sync initialization
3. **Sensible Defaults**: Auto-configured `.gitignore` and sync settings

---

## Success Metrics

1. **Sync Reliability**: 99.9% successful sync operations
2. **Sync Speed**: < 5 seconds for typical workspace push/pull
3. **Storage Efficiency**: < 500 KB synced per workspace
4. **User Adoption**: 50% of active users enable sync within 3 months

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Git complexity for non-developers | Medium | Provide simple CLI/UI; hide Git details |
| Large repositories over time | Low | Auto-prune old run configs; archive old workspaces |
| Merge conflicts | Medium | Default to last-write-wins; preserve backups |
| Network dependency | Low | Offline-first design; async sync |
| GitHub rate limits | Low | Batch operations; cache status |

---

## Open Questions

1. **Should we support non-Git backends?** (e.g., iCloud, Dropbox)
   - Pro: Easier for non-technical users
   - Con: No versioning, more complex implementation

2. **Should auto-sync be default?**
   - Pro: Seamless experience
   - Con: Unexpected network usage, potential conflicts

3. **How to handle very large run histories?**
   - Option A: Sync all runs (complete history)
   - Option B: Sync only last N runs per scenario
   - Option C: Archive runs older than X days

4. **Should we support syncing simulation databases?**
   - Pro: Immediate access to results on any device
   - Con: Large files, bandwidth usage
   - Middle ground: Optional "sync databases" setting for users with fast connections

---

## Related Epics

- **E069**: Batch Scenario Processing (provides Excel exports to consider for sync)
- **E072**: Pipeline Modularization (clean architecture enables sync integration)
- **E074**: Enhanced Error Handling (error patterns for sync failures)

---

## Appendix: Alternative Approaches Considered

### A. Database-First Sync

Store workspace metadata in a central database (PostgreSQL/SQLite) and sync that.

**Rejected because:**
- Adds infrastructure dependency
- Loses Git's versioning benefits
- More complex deployment

### B. Full Cloud Service

Build a hosted PlanAlign Cloud service.

**Rejected because:**
- Significant infrastructure investment
- Ongoing hosting costs
- Users may have data locality requirements

### C. File Sync Services (Dropbox/iCloud/OneDrive)

Let users point workspace directory to a synced folder.

**Rejected because:**
- No version control
- Conflict handling is poor
- Can't exclude large files intelligently
- May sync during simulation (data corruption risk)
