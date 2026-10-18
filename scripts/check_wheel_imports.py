"""Import every shipped package from an installed (non-editable) wheel.

Run from outside the checkout so the source tree cannot shadow the install.
"""

import importlib
import pkgutil
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    imported = 0
    for top in config["tool"]["coverage"]["run"]["source"]:
        module = importlib.import_module(top)
        if Path(module.__file__).resolve().is_relative_to(ROOT):
            sys.exit(f"{top} imported from the checkout, not the installed wheel")
        for info in pkgutil.walk_packages(module.__path__, f"{top}."):
            if info.ispkg:
                importlib.import_module(info.name)
                imported += 1
    print(f"Imported {imported} subpackages from the installed wheel")


if __name__ == "__main__":
    main()
