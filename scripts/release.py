"""Version PlanAlign Engine releases from the commits merged since the last tag.

    python3 scripts/release.py next
        Prints the next version: major for a `type!:` commit, minor for any
        `feat`, patch for any `fix` or `perf`. Prints nothing if none landed.

    python3 scripts/release.py prepare [VERSION] [--name NAME]
        Bumps the version everywhere it is recorded, moves CHANGELOG's
        Unreleased section under a dated heading (or lists the merged
        feat/fix commits if it is empty), and updates SECURITY.md's supported
        versions on a minor or major bump. VERSION defaults to `next`.

    python3 scripts/release.py publish VERSION
        After the release PR merges: tags the commit on origin/main that set
        the version, pushes the tag, and publishes the GitHub release with the
        CHANGELOG section as its notes.

release.yml runs this automatically: every feat/fix merge refreshes one open
"chore(release)" PR, and merging that PR publishes. Stdlib only.
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
NAME_LINE = re.compile(r'^__release_name__ = "([^"]*)"$', re.M)
CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(\([^)]*\))?(?P<breaking>!)?:")
RELEASABLE = {"feat", "fix", "perf"}


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


def parse(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def commit_kind(subject: str) -> str | None:
    """Return "breaking", the conventional type if releasable, or None."""
    match = CONVENTIONAL.match(subject)
    if not match:
        return None
    if match.group("breaking"):
        return "breaking"
    kind = match.group("type")
    return kind if kind in RELEASABLE else None


def releasable_subjects() -> list[str]:
    """Subjects of feat/fix/perf (or breaking) commits on HEAD since the last tag."""
    last_tag = run("git", "describe", "--tags", "--abbrev=0", "--match", "v*")
    log = run("git", "log", f"{last_tag}..HEAD", "--first-parent", "--format=%s")
    return [subject for subject in log.splitlines() if commit_kind(subject)]


def next_version(current: str, subjects: list[str]) -> str | None:
    kinds = {commit_kind(subject) for subject in subjects}
    major, minor, patch = parse(current)
    if "breaking" in kinds:
        return f"{major + 1}.0.0"
    if "feat" in kinds:
        return f"{major}.{minor + 1}.0"
    if kinds & {"fix", "perf"}:
        return f"{major}.{minor}.{patch + 1}"
    return None


def replace_once(path: str, pattern: str, replacement: str) -> None:
    """Apply one regex substitution to a repo file, failing loudly if it misses."""
    file = ROOT / path
    text, count = re.subn(pattern, replacement, file.read_text(), count=1, flags=re.M)
    if count != 1:
        sys.exit(f"{path}: pattern not found: {pattern}")
    file.write_text(text)


def bump_files(old: str, new: str, name: str, today: str) -> None:
    replace_once("_version.py", r'^__version__ = "[^"]+"$', f'__version__ = "{new}"')
    replace_once(
        "_version.py", r'^__release_date__ = "[^"]+"$', f'__release_date__ = "{today}"'
    )
    replace_once(
        "_version.py", r'^__release_name__ = "[^"]*"$', f'__release_name__ = "{name}"'
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


def update_supported_versions(old: str, new: str) -> None:
    """On a minor or major bump, mark the new line active and the old one critical-only."""
    old_line, new_line = ".".join(old.split(".")[:2]), ".".join(new.split(".")[:2])
    if old_line == new_line:
        return
    replace_once(
        "SECURITY.md",
        rf"^\| {re.escape(old_line)}\.x(\s*)\| ✅ Active \|$",
        f"| {new_line}.x\\g<1>| ✅ Active |\n"
        f"| {old_line}.x\\g<1>| ⚠️ Critical fixes only |",
    )


def changelog_section(text: str, heading: str) -> str:
    """Return the body under `## [heading]` up to the next release heading."""
    match = re.search(
        rf"^## \[{re.escape(heading)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S
    )
    if not match:
        sys.exit(f"CHANGELOG.md has no [{heading}] section")
    return match.group(1).strip()


def release_changelog(new: str, name: str, today: str, subjects: list[str]) -> None:
    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text()
    title = f"## [{new}] - {today}" + (f' "{name}"' if name else "")
    listed = ""
    if not changelog_section(text, "Unreleased"):
        listed = "\n" + "\n".join(f"- {subject}" for subject in subjects) + "\n"
    changelog.write_text(
        text.replace("## [Unreleased]\n", f"## [Unreleased]\n\n{title}\n{listed}", 1)
    )


def release_name(old: str, new: str, name: str | None) -> str:
    """Keep the line's name on a patch; minor and major releases start unnamed."""
    if name is not None:
        return name
    if parse(new)[:2] != parse(old)[:2]:
        return ""
    match = NAME_LINE.search((ROOT / "_version.py").read_text())
    return match.group(1) if match else ""


def prepare(version: str | None, name: str | None) -> None:
    old = current_version()
    subjects = releasable_subjects()
    new = version or next_version(old, subjects)
    if new is None:
        sys.exit("no feat, fix or perf commits since the last tag")
    if parse(new) <= parse(old):
        sys.exit(f"{new} is not newer than {old}")
    today = date.today().isoformat()
    final_name = release_name(old, new, name)
    release_changelog(new, final_name, today, subjects)
    bump_files(old, new, final_name, today)
    update_supported_versions(old, new)
    print(new)


def release_commit(new: str) -> str:
    """Return the commit on origin/main that set __version__ to `new`."""
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
    return commit


def publish(new: str) -> None:
    run("git", "fetch", "--quiet", "--tags", "origin")
    if current_version(run("git", "show", "origin/main:_version.py")) != new:
        sys.exit(f"origin/main is not at {new}; merge the release PR first")
    if run("git", "tag", "--list", f"v{new}"):
        sys.exit(f"tag v{new} already exists")
    commit = release_commit(new)
    notes = changelog_section(run("git", "show", "origin/main:CHANGELOG.md"), new)
    name = NAME_LINE.search(run("git", "show", f"{commit}:_version.py"))
    title = f"{new} — {name.group(1)}" if name and name.group(1) else new
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
    sub.add_parser("next", help="print the next version, or nothing")
    prep = sub.add_parser("prepare", help="bump versions and date the changelog")
    prep.add_argument("version", nargs="?")
    prep.add_argument("--name", help="release name (kept on patch, none otherwise)")
    pub = sub.add_parser("publish", help="tag origin/main and publish the release")
    pub.add_argument("version")
    args = parser.parse_args()
    version: str | None = getattr(args, "version", None)
    if version is not None and not SEMVER.match(version):
        sys.exit(f"{version} is not MAJOR.MINOR.PATCH")
    if args.command == "next":
        print(next_version(current_version(), releasable_subjects()) or "")
    elif args.command == "prepare":
        prepare(version, args.name)
    elif version is not None:
        publish(version)


if __name__ == "__main__":
    main()
