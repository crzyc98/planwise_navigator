"""Require combined coverage to include every shipped Python module."""

import json
from pathlib import Path
import tomllib


def main(report_path: Path = Path("coverage.json")) -> None:
    config = tomllib.loads(Path("pyproject.toml").read_text())
    sources = set(config["tool"]["coverage"]["run"]["source"])
    shipped = {
        package.split(".")[0] for package in config["tool"]["setuptools"]["packages"]
    }
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
