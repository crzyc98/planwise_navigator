# Versioning Guide

Fidelity PlanAlign Engine follows [Semantic Versioning 2.0.0](https://semver.org/):
**MAJOR.MINOR.PATCH**.

- **MAJOR** — incompatible API/config changes or major architectural changes
- **MINOR** — backwards-compatible features (e.g., a new epic)
- **PATCH** — backwards-compatible bug fixes

The single source of truth is `_version.py` (`__version__`, `__release_date__`,
`__release_name__`); `pyproject.toml` must be kept in sync. The CLI reports it via
`planalign --version`.

## Release checklist

1. Update `__version__`, `__release_date__`, and (for minor/major releases)
   `__release_name__` in `_version.py`.
2. Update `version` in `pyproject.toml` to match.
3. Add a dated entry to `CHANGELOG.md` describing the changes.
4. Verify: `python -c "from _version import get_version_dict; print(get_version_dict())"`
   and `planalign --version`.
5. Commit, tag `v<MAJOR>.<MINOR>.<PATCH>`, and push the tag.

## History

See `CHANGELOG.md`. Current version at the time of writing: **2.1.0
"Studio & Compliance"** (2026-03-03).
