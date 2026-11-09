"""Cut a PlanAlign Engine release in two steps.

    python3 scripts/release.py prepare 3.1.0 --name "Calibration & Pay"
        Bumps the version everywhere it is recorded and moves CHANGELOG's
        Unreleased section under a dated heading. Commit the result in a PR.

    python3 scripts/release.py publish 3.1.0
        After that PR merges: tags the commit on origin/main that set the
        version, pushes the tag, and publishes the GitHub release with the
        CHANGELOG section as its notes.

Release whenever simulation results change, so a run's planalign_version
identifies the engine that produced it. Studio run provenance already records
the exact commit. Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_LINE = re.compile(r'^__version__ = "([^"]+)"$', re.M)


def run(*args: str) -> str:
    return subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def current_version(text: str | None = None) -> str:
    source = text if text is not None else (ROOT / "_version.py").read_text()
    match = VERSION_LINE.search(source)
    if not match:
        sys.exit("_version.py has no __version__ line")
    return match.group(1)


def replace_once(path: str, pattern: str, replacement: str, flags: int = re.M) -> None:
    """Apply one regex substitution to a repo file, failing loudly if it misses."""
    file = ROOT / path
    text, count = re.subn(pattern, replacement, file.read_text(), count=1, flags=flags)
    if count != 1:
        sys.exit(f"{path}: pattern not found: {pattern}")
    file.write_text(text)


def bump_files(old: str, new: str, name: str | None, today: str) -> None:
    replace_once("_version.py", r'^__version__ = "[^"]+"$', f'__version__ = "{new}"')
    replace_once(
        "_version.py", r'^__release_date__ = "[^"]+"$', f'__release_date__ = "{today}"'
    )
    if name:
        replace_once(
            "_version.py",
            r'^__release_name__ = "[^"]+"$',
            f'__release_name__ = "{name}"',
        )
    replace_once(
        "pyproject.toml", rf'^version = "{re.escape(old)}"$', f'version = "{new}"'
    )
    replace_once(
        "uv.lock",
        rf'(name = "planalign-engine"\nversion = )"{re.escape(old)}"',
        rf'\g<1>"{new}"',
    )
    replace_once(
        "dbt/dbt_project.yml", rf"^version: '{re.escape(old)}'$", f"version: '{new}'"
    )
    readme = ROOT / "README.md"
    readme.write_text(readme.read_text().replace(f"| {old} |", f"| {new} |"))


def release_changelog(new: str, name: str | None, today: str) -> None:
    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text()
    body = changelog_section(text, "Unreleased")
    if not body.strip():
        sys.exit("CHANGELOG.md has nothing under [Unreleased] to release")
    title = f"## [{new}] - {today}" + (f' "{name}"' if name else "")
    changelog.write_text(
        text.replace("## [Unreleased]\n", f"## [Unreleased]\n\n{title}\n", 1)
    )


def changelog_section(text: str, heading: str) -> str:
    """Return the body under `## [heading]` up to the next release heading."""
    match = re.search(
        rf"^## \[{re.escape(heading)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S
    )
    if not match:
        sys.exit(f"CHANGELOG.md has no [{heading}] section")
    return match.group(1).strip()


def prepare(new: str, name: str | None) -> None:
    old = current_version()
    if tuple(map(int, new.split("."))) <= tuple(map(int, old.split("."))):
        sys.exit(f"{new} is not newer than {old}")
    today = date.today().isoformat()
    release_changelog(new, name, today)
    bump_files(old, new, name, today)
    print(f"Bumped {old} -> {new}. Before committing:")
    print("  - Update the Supported Versions table in SECURITY.md.")
    print("  - Check docs against what shipped (docs/VERSIONING_GUIDE.md, step 5).")
    print(f"Then open a PR titled 'chore(release): {new}' and, after it merges, run:")
    print(f"  python3 scripts/release.py publish {new}")


def publish(new: str) -> None:
    run("git", "fetch", "--quiet", "--tags", "origin")
    if current_version(run("git", "show", "origin/main:_version.py")) != new:
        sys.exit(f"origin/main is not at {new}; merge the release PR first")
    if run("git", "tag", "--list", f"v{new}"):
        sys.exit(f"tag v{new} already exists")
    commit = run(
        "git",
        "log",
        "origin/main",
        "--first-parent",
        "-1",
        "--format=%H",
        f'-S__version__ = "{new}"',
        "--",
        "_version.py",
    )
    if not commit:
        sys.exit(
            f"no commit on origin/main sets __version__ to {new}; is the clone shallow?"
        )
    notes = changelog_section(run("git", "show", "origin/main:CHANGELOG.md"), new)
    name = re.search(
        r'__release_name__ = "([^"]+)"', run("git", "show", f"{commit}:_version.py")
    )
    title = f"{new} — {name.group(1)}" if name else new
    run("git", "tag", "-a", f"v{new}", commit, "-m", title)
    run("git", "push", "origin", f"v{new}")
    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.md"
        notes_file.write_text(notes + "\n")
        run(
            "gh",
            "release",
            "create",
            f"v{new}",
            "--title",
            title,
            "--notes-file",
            str(notes_file),
            "--latest",
        )
    print(f"Published v{new} at {commit[:8]}: {title}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="bump versions and date the changelog")
    prep.add_argument("version")
    prep.add_argument("--name", help="release name (minor and major releases)")
    pub = sub.add_parser(
        "publish", help="tag origin/main and publish the GitHub release"
    )
    pub.add_argument("version")
    args = parser.parse_args()
    if not SEMVER.match(args.version):
        sys.exit(f"{args.version} is not MAJOR.MINOR.PATCH")
    if args.command == "prepare":
        prepare(args.version, args.name)
    else:
        publish(args.version)


if __name__ == "__main__":
    main()
