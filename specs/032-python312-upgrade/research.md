# Research: Python 3.12 Dependency Compatibility

**Date**: 2026-02-03
**Feature**: 032-python312-upgrade
**Purpose**: Verify all project dependencies support Python 3.12.x

## Summary

All core dependencies support Python 3.12. Three development dependencies require version upgrades for full compatibility.

## Dependency Analysis

### Core Runtime Dependencies

| Dependency | Pinned Version | Python 3.12 | Wheels | Action |
|------------|----------------|-------------|--------|--------|
| duckdb | 1.0.0 | ✅ Yes | ✅ cp312 | No change |
| dbt-core | 1.8.8 | ✅ Yes | ✅ Yes | No change |
| dbt-duckdb | 1.8.1 | ✅ Yes | ✅ cp312 | No change |
| pydantic | 2.7.4 | ✅ Yes | ✅ py3 | No change |
| FastAPI | >=0.109.0 | ✅ Yes | ✅ py3 | No change |
| uvicorn | >=0.27.0 | ✅ Yes | ✅ py3 | No change |
| rich | >=13.0.0 | ✅ Yes | ✅ py3 | No change |
| typer | >=0.9.0 | ✅ Yes | ✅ py3 | No change |
| GitPython | >=3.1.0 | ✅ Yes | ✅ py3 | No change |

### Development Dependencies

| Dependency | Pinned Version | Python 3.12 | Issue | Recommended Version |
|------------|----------------|-------------|-------|---------------------|
| pytest | 7.4.0 | ✅ Yes | Minor edge cases | 8.0.0+ (optional) |
| black | 23.9.1 | ⚠️ Partial | No mypyc wheels | 24.3.0+ |
| mypy | 1.5.1 | ⚠️ Partial | Limited PEP 695 | 1.10.0+ |
| ipython | 8.14.0 | ⚠️ Partial | Tokenizer issues | 8.18.0+ |
| jupyter | 1.0.0 | ❌ No | Severely outdated | 1.1.1+ |

## Findings

### 1. duckdb==1.0.0

**Decision**: Use as-is
**Rationale**: DuckDB 1.0.0 has full Python 3.12 support with prebuilt cp312 wheels for all platforms (Windows, macOS arm64/x86_64, Linux).
**Alternatives considered**: None needed

### 2. dbt-core==1.8.8

**Decision**: Use as-is
**Rationale**: dbt-core 1.8.x series includes Python 3.12 support. Verified compatible per dbt's Python compatibility matrix.
**Alternatives considered**: None needed

### 3. dbt-duckdb==1.8.1

**Decision**: Use as-is
**Rationale**: dbt-duckdb requires Python >=3.9, placing Python 3.12 well within supported range. Has cp312 wheels.
**Alternatives considered**: None needed

### 4. pydantic==2.7.4

**Decision**: Use as-is
**Rationale**: Explicitly lists "Python :: 3.12" in classifiers. Includes specific fixes for Python 3.12 TypeAliasType.
**Alternatives considered**: None needed

### 5. pytest==7.4.0

**Decision**: Use as-is (optional upgrade to 8.x)
**Rationale**: Works on Python 3.12. Minor edge cases fixed in 8.x but not critical for project use.
**Alternatives considered**: pytest 8.0.0+ eliminates all edge cases but requires testing compatibility with pytest plugins

### 6. black==23.9.1 → 24.3.0+

**Decision**: Upgrade to black>=24.3.0
**Rationale**: Version 23.9.1 lacks mypyc-compiled wheels for Python 3.12 due to upstream compiler bug. Pure Python fallback is significantly slower. Version 24.3.0+ includes proper Python 3.12 mypyc wheels.
**Alternatives considered**: Keep 23.9.1 (rejected: unacceptable performance regression)

### 7. mypy==1.5.1 → 1.10.0+

**Decision**: Upgrade to mypy>=1.10.0
**Rationale**: Version 1.5.1 runs on Python 3.12 but has limited support for PEP 695 type syntax. Version 1.10.0+ has complete Python 3.12 type syntax support.
**Alternatives considered**: Keep 1.5.1 (acceptable if not using new type syntax, but upgrade recommended)

### 8. ipython==8.14.0 → 8.18.0+

**Decision**: Upgrade to ipython>=8.18.0
**Rationale**: Python 3.12 changed the tokenizer for better f-string support, breaking IPython features. Version 8.18.0+ includes explicit Python 3.12 compatibility fixes.
**Alternatives considered**: Keep 8.14.0 (rejected: known bugs with Python 3.12 tokenizer)

### 9. jupyter==1.0.0 → 1.1.1+

**Decision**: Upgrade to jupyter>=1.1.1
**Rationale**: Version 1.0.0 is from August 2015 (9+ years old). Has severe dependency resolution issues with Python 3.12. Version 1.1.1+ is the modern release with proper Python 3.12 support.
**Alternatives considered**: None viable - 1.0.0 is unmaintainable

## Version Constraint Decision

**Decision**: Set `requires-python = ">=3.11,<3.14"`
**Rationale**:
- Lower bound `>=3.11`: Maintains backward compatibility for existing users
- Upper bound `<3.14`: Allows Python 3.12 and 3.13 (when released), prevents unknown future incompatibilities
**Alternatives considered**:
- `>=3.12`: Rejected - would break existing Python 3.11 users
- `>=3.11`: Rejected - no upper bound risks future breakage

## Required Changes Summary

### pyproject.toml

```toml
# Update requires-python
requires-python = ">=3.11,<3.14"

# Update dev dependencies
[project.optional-dependencies]
dev = [
    # ... existing ...
    "black>=24.3.0",      # was 23.9.1
    "mypy>=1.10.0",       # was 1.5.1
    "ipython>=8.18.0",    # was 8.14.0
    "jupyter>=1.1.1",     # was 1.0.0
]
```

### requirements-dev.txt

```text
black>=24.3.0
mypy>=1.10.0
ipython>=8.18.0
jupyter>=1.1.1
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Dev tool version bump breaks workflows | Low | Medium | Run full test suite after upgrade |
| Black formatting changes | Low | Low | Review formatting diffs before commit |
| mypy strictness increases | Low | Low | Fix any new type errors incrementally |
| jupyter ecosystem conflicts | Very Low | Low | jupyter metapackage updated regularly |

## Verification Plan

1. Create fresh Python 3.12 virtual environment
2. Install with `pip install -e ".[dev]"`
3. Run `planalign health` to verify core functionality
4. Run `pytest -m fast` to verify test suite
5. Run `black --check .` to verify formatting tool
6. Run `mypy planalign_orchestrator` to verify type checking
