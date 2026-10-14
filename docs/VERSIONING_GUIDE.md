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
2. Update `version` in `pyproject.toml` and the editable project entry in
   `uv.lock` to match. Do not change dependency versions for a release bump.
3. Update the current version and component versions in `README.md` and the
   versioning section in `CLAUDE.md`. Distinguish unreleased code from tagged releases.
4. Add a dated entry to `CHANGELOG.md` describing the changes.
5. Verify: `python -c "from _version import get_version_dict; print(get_version_dict())"`
   and `planalign --version`.
6. Commit, tag `v<MAJOR>.<MINOR>.<PATCH>`, and push the tag.

## History

See [CHANGELOG.md](../CHANGELOG.md) for history and
[_version.py](../_version.py) for the current version and release metadata.
