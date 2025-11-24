# Fidelity PlanAlign Engine Versioning Guide

## Overview

Fidelity PlanAlign Engine follows **Semantic Versioning 2.0.0** (https://semver.org/) to track releases and ensure clear communication about changes to stakeholders, compliance teams, and users.

## Version Format

**MAJOR.MINOR.PATCH** (e.g., `1.2.3`)

- **MAJOR**: Breaking changes that require user action
- **MINOR**: New features that are backwards-compatible
- **PATCH**: Bug fixes and minor improvements

## Current Version

**Version:** 1.0.0
**Release Name:** Foundation
**Release Date:** 2025-01-15

View the current version:
```bash
planalign --version
planalign health
planalign status
```

## When to Increment Versions

### MAJOR Version (X.0.0) - Breaking Changes

Increment when making incompatible changes that require user action:

- **Configuration Schema Changes**: Removing or renaming required fields
- **Database Schema Changes**: Incompatible changes requiring migration
- **API Changes**: Removing or changing existing CLI commands/options
- **Behavioral Changes**: Significant changes to simulation logic
- **Deprecated Feature Removal**: Removing previously deprecated features

**Examples:**
- `1.0.0 → 2.0.0`: Removing `--legacy-mode` flag
- `2.0.0 → 3.0.0`: Changing database schema requiring manual migration

### MINOR Version (x.Y.0) - New Features

Increment when adding new functionality in a backwards-compatible manner:

- **New Epic Features**: E068 (Performance), E069 (Batch Processing), etc.
- **New CLI Commands**: Adding `planalign export` command
- **New Configuration Options**: Adding optional configuration fields
- **New dbt Models**: Adding new analytics models or reports
- **Performance Improvements**: Significant speed improvements without breaking changes
- **New Analysis Features**: New dashboard views or reports

**Examples:**
- `1.0.0 → 1.1.0`: Adding E076 Polars State Accumulation
- `1.1.0 → 1.2.0`: Adding new Excel export formats

### PATCH Version (x.y.Z) - Bug Fixes

Increment for backwards-compatible bug fixes and minor improvements:

- **Bug Fixes**: Fixing incorrect calculations or broken features
- **Documentation Updates**: README, CLAUDE.md, or other docs
- **Test Improvements**: Adding or improving tests
- **Internal Refactoring**: Code cleanup without API changes
- **Dependency Updates**: Updating dependencies (if no breaking changes)
- **Performance Tweaks**: Minor optimizations

**Examples:**
- `1.0.0 → 1.0.1`: Fixing termination event calculation bug
- `1.0.1 → 1.0.2`: Updating documentation and adding tests

## Version Update Workflow

### Step 1: Update Version Module

Edit `_version.py` in the project root:

```python
__version__ = "1.1.0"  # Update version number
__version_info__ = tuple(int(x) for x in __version__.split("."))
__release_date__ = "2025-01-24"  # Update to release date
__release_name__ = "Performance"  # Optional: Choose a release name
```

### Step 2: Update pyproject.toml

Edit line 3 in `pyproject.toml`:

```toml
[project]
name = "planwise-navigator"
version = "1.1.0"  # Must match _version.py
```

### Step 3: Update CHANGELOG.md

Add a new version section under `## [Unreleased]`:

```markdown
## [Unreleased]

### Added
### Changed
### Fixed

---

## [1.1.0] - 2025-01-24 "Performance"

### Added
- E076: Polars State Accumulation Pipeline (60-75% performance improvement)
- New `--profile` flag for performance profiling

### Changed
- State accumulation now uses Polars instead of dbt
- Improved error messages for configuration validation

### Fixed
- Fixed memory leak in multi-year simulations
- Fixed checkpoint recovery edge case
```

Categories to use:
- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Features that will be removed in future versions
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security fixes

### Step 4: Commit and Tag

```bash
# Commit version changes
git add _version.py pyproject.toml CHANGELOG.md
git commit -m "chore: Bump version to 1.1.0"

# Create annotated tag
git tag -a v1.1.0 -m "Release version 1.1.0: Performance improvements"

# Push commits and tags
git push origin feature/your-branch
git push origin v1.1.0
```

### Step 5: Create Pull Request

Create a PR with the version bump:
- **Title**: `chore: Release v1.1.0 - Performance improvements`
- **Description**: Include CHANGELOG entry for the release
- **Labels**: Add `release` label

### Step 6: Reinstall Package (Development)

After merging to main, reinstall the package locally:

```bash
uv pip install -e .
```

Verify the version:

```bash
planalign --version
# Output: Fidelity PlanAlign Engine CLI v1.1.0
```

## Version Management in CI/CD

### Pre-Release Checks

Before creating a release, run:

```bash
# Verify all tests pass
pytest

# Verify version consistency
python -c "
from _version import __version__
import toml
pyproject_version = toml.load('pyproject.toml')['project']['version']
assert __version__ == pyproject_version, f'Version mismatch: _version.py={__version__}, pyproject.toml={pyproject_version}'
print(f'✅ Version {__version__} is consistent')
"

# Verify CHANGELOG updated
grep -q "## \[${VERSION}\]" CHANGELOG.md || echo "⚠️ CHANGELOG not updated for ${VERSION}"
```

### Automated Versioning (Future Enhancement)

Consider using tools like:
- **bump2version**: Automates version updates across files
- **semantic-release**: Automated semantic versioning based on commit messages
- **commitizen**: Enforces conventional commits for automated versioning

## Release Names (Optional)

Release names are optional but provide memorable identifiers for major versions:

- **1.0.0** - "Foundation": Initial production release
- **1.1.0** - "Performance": E076 Polars state accumulation
- **1.2.0** - "Analytics": Enhanced reporting and dashboards
- **2.0.0** - "Enterprise": Major architectural overhaul

## Compliance and Auditing

### Version Information in Artifacts

Every simulation run includes version metadata:

1. **Database Metadata**: Version stored in checkpoint tables
2. **Excel Exports**: Version included in metadata sheet
3. **Log Files**: Version logged at startup
4. **Status Commands**: Version displayed in health checks

### Version Queries

Query version from Python code:

```python
# Get current version
from _version import __version__, get_version_dict

print(f"Running Fidelity PlanAlign Engine v{__version__}")

# Get full version metadata
version_info = get_version_dict()
print(f"Release: {version_info['release_name']}")
print(f"Date: {version_info['release_date']}")
```

### Git Integration (Future)

The `_version.py` module supports git SHA tracking:

```python
# These fields can be populated by CI/CD or build scripts
__git_sha__ = "a1b2c3d"  # Short git SHA
__git_branch__ = "main"  # Branch name
```

Use `get_full_version()` to include git SHA: `1.1.0+a1b2c3d`

## Version History

See [CHANGELOG.md](../CHANGELOG.md) for complete version history.

## Examples

### Example 1: Bug Fix Release

```bash
# Current version: 1.0.0
# Fix: Termination calculation bug

# 1. Update _version.py
__version__ = "1.0.1"
__release_date__ = "2025-01-18"

# 2. Update pyproject.toml
version = "1.0.1"

# 3. Update CHANGELOG.md
## [1.0.1] - 2025-01-18
### Fixed
- Fixed termination event proration calculation

# 4. Commit and tag
git commit -m "fix: Correct termination event proration"
git tag -a v1.0.1 -m "Bug fix: termination proration"
```

### Example 2: New Feature Release

```bash
# Current version: 1.0.1
# Feature: E076 Polars State Accumulation

# 1. Update _version.py
__version__ = "1.1.0"
__release_date__ = "2025-02-01"
__release_name__ = "Performance"

# 2. Update pyproject.toml
version = "1.1.0"

# 3. Update CHANGELOG.md
## [1.1.0] - 2025-02-01 "Performance"
### Added
- E076: Polars State Accumulation (60-75% faster)

# 4. Commit and tag
git commit -m "feat: Add E076 Polars state accumulation"
git tag -a v1.1.0 -m "Release v1.1.0: Performance improvements"
```

### Example 3: Breaking Change Release

```bash
# Current version: 1.2.0
# Change: Remove deprecated --legacy-mode flag

# 1. Update _version.py
__version__ = "2.0.0"
__release_date__ = "2025-03-01"
__release_name__ = "Modernization"

# 2. Update pyproject.toml
version = "2.0.0"

# 3. Update CHANGELOG.md
## [2.0.0] - 2025-03-01 "Modernization"
### Removed
- BREAKING: Removed deprecated --legacy-mode flag
### Migration Guide
- Replace `planalign simulate --legacy-mode` with `planalign simulate`

# 4. Commit and tag
git commit -m "feat!: Remove deprecated legacy mode"
git tag -a v2.0.0 -m "Release v2.0.0: Breaking changes"
```

## Questions?

For questions about versioning:
1. Check the [CHANGELOG.md](../CHANGELOG.md)
2. Review [Semantic Versioning](https://semver.org/)
3. Consult your team lead or compliance officer

---

**Last Updated:** 2025-01-24
**Document Version:** 1.0
