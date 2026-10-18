"""Require combined coverage to include every shipped Python module."""

from fnmatch import fnmatch
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def shipped_packages(config: dict) -> set[str]:
    """Top-level packages selected by ``[tool.setuptools.packages.find]``."""
    find = config["tool"]["setuptools"]["packages"]["find"]
    return {
        path.parent.name
        for path in ROOT.glob("*/__init__.py")
        if any(fnmatch(path.parent.name, pattern) for pattern in find["include"])
        and not any(fnmatch(path.parent.name, pattern) for pattern in find["exclude"])
    }


def main(report_path: Path = Path("coverage.json")) -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text())
    sources = set(config["tool"]["coverage"]["run"]["source"])
    shipped = shipped_packages(config)
    if sources != shipped:
        raise ValueError(f"Coverage/packaging inventory mismatch: {sources ^ shipped}")
    report = json.loads(report_path.read_text())
    files = report["files"]
    for package in sorted(sources):
        expected = {path.as_posix() for path in Path(package).rglob("*.py")}
        missing = expected - files.keys()
        if not expected or missing:
            raise ValueError(f"Coverage omitted {package} modules: {sorted(missing)}")
        summaries = [files[path]["summary"] for path in expected]
        covered = sum(summary["covered_lines"] for summary in summaries)
        statements = sum(summary["num_statements"] for summary in summaries)
        print(f"{package}: {covered}/{statements} statements; {len(expected)} modules")
    print(f"Combined coverage: {report['totals']['percent_covered']:.2f}%")


if __name__ == "__main__":
    main()
