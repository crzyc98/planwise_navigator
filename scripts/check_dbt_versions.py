"""Print and verify effective dbt versions against project declarations."""

from importlib.metadata import version
from pathlib import Path
import tomllib

from packaging.requirements import Requirement


def main() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())
    requirements = {
        requirement.name: requirement
        for dependency in project["project"]["dependencies"]
        if (requirement := Requirement(dependency)).name in {"dbt-core", "dbt-duckdb"}
    }
    if requirements.keys() != {"dbt-core", "dbt-duckdb"}:
        raise ValueError("Both dbt distributions must be declared in pyproject.toml")
    for name, requirement in sorted(requirements.items()):
        installed = version(name)
        print(f"{name}=={installed}; declared: {requirement}", flush=True)
        if installed not in requirement.specifier:
            raise ValueError(f"Effective {name}=={installed} violates {requirement}")


if __name__ == "__main__":
    main()
