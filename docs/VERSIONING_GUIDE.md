# Versioning Guide

Fidelity PlanAlign Engine follows [Semantic Versioning 2.0.0](https://semver.org/):
**MAJOR.MINOR.PATCH**.

- **MAJOR** — incompatible API/config changes or major architectural changes
- **MINOR** — backwards-compatible features (e.g., a new epic)
- **PATCH** — backwards-compatible bug fixes

The single source of truth is `_version.py` (`__version__`, `__release_date__`,
`__release_name__`); `pyproject.toml`, the editable package in `uv.lock`, and
`dbt/dbt_project.yml` must be kept in sync. The dbt project ships as part of the
engine and has no independent release version. Its `config-version: 2` is dbt's
configuration format and must not be changed for an engine release. The CLI
reports the engine version via `planalign --version`.

## Release checklist

1. Update `__version__`, `__release_date__`, and (for minor/major releases)
   `__release_name__` in `_version.py`.
2. Update `version` in `pyproject.toml`, the editable project entry in
   `uv.lock`, and `dbt/dbt_project.yml` to match. Do not change dependency
   versions for a release bump.
3. Update the current version and component versions in `README.md` and the
   versioning section in `CLAUDE.md`. Distinguish unreleased code from tagged releases.
4. Reconcile the active release line in `SECURITY.md` with `_version.py` and
   explicitly review which older lines receive fixes. Compare current stack
   entries in README, SECURITY, and CLAUDE with `pyproject.toml`,
   `requirements.txt`, and resolved `uv.lock` versions. Keep dated upgrade
   validation records historical; do not relabel their tested versions.
5. Review `METHODOLOGY.md` against shipped features and configuration defaults,
   including migration semantics. Update its system version, document date,
   scope, assumptions, limitations, and linked feature guides. Distinguish
   checked-in sample settings from typed defaults and per-design overrides.
6. Check README's profile key against `profile` in `dbt/dbt_project.yml` and
   `dbt/profiles.yml`. Copy the README YAML into a fresh temporary profiles
   directory and, from `dbt/`, run `dbt debug --profiles-dir <that-directory>` with `DATABASE_PATH` set to a fresh absolute database path and
   `DBT_TARGET_PATH` / `DBT_LOG_PATH` set to isolated artifact directories.
   Verify the logged database path and successful connection. Explicitly
   distinguish this user-profile setup from `--profiles-dir .`.
7. Add a dated entry to `CHANGELOG.md` describing the release changes.
8. Verify: `python -c "from _version import get_version_dict; print(get_version_dict())"`,
   `planalign --version`, `uv lock --check --offline`, and `git diff --check`.
   Run the targeted checks required by any behavioral changes separately in
   isolated databases; a profile connection check is not simulation validation.
9. Commit, tag `v<MAJOR>.<MINOR>.<PATCH>`, and push the tag.

## History

See [CHANGELOG.md](../CHANGELOG.md) for history and
[_version.py](../_version.py) for the current version and release metadata.
