"""Shared discovery and palette fixtures for Studio theme contract tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).parents[2]
STUDIO_ROOT = REPO_ROOT / "planalign_studio"
COMPONENT_ROOT = STUDIO_ROOT / "components"
PALETTE_PATH = STUDIO_ROOT / "theme" / "chart-palettes.json"

EXPECTED_COMPONENT_COUNT = 55
EXPECTED_RECHARTS_CONSUMER_COUNT = 13
EXPECTED_RECHARTS_CHART_COUNT = 31

RETIRED_PALETTE = (
    "#0088FE",
    "#00C49F",
    "#FFBB28",
    "#FF8042",
    "#8884D8",
    "#E91E63",
)

ACCEPTED_LIGHT_PALETTE = (
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#CC79A7",
    "#56B4E9",
    "#D55E00",
)

LIGHT_SURFACE = "#FFFFFF"
DARK_SURFACE = "#1A1A19"

_RECHARTS_IMPORT = re.compile(r"from\s+['\"]recharts['\"]")
_CHART_DECLARATION = re.compile(
    r"<(?:LineChart|BarChart|AreaChart|PieChart|ScatterChart|ComposedChart)\b"
)


def component_files() -> tuple[Path, ...]:
    """Return every current Studio component TSX file in stable order."""

    return tuple(sorted(COMPONENT_ROOT.rglob("*.tsx")))


def recharts_consumer_files() -> tuple[Path, ...]:
    """Discover direct Recharts consumers instead of maintaining a stale list."""

    return tuple(
        path
        for path in component_files()
        if _RECHARTS_IMPORT.search(path.read_text(encoding="utf-8"))
    )


def recharts_chart_count() -> int:
    """Count actual chart declarations only inside direct Recharts consumers."""

    return sum(
        len(_CHART_DECLARATION.findall(path.read_text(encoding="utf-8")))
        for path in recharts_consumer_files()
    )


def load_palette_source() -> dict[str, Any]:
    """Load the machine-readable runtime palette source."""

    return json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
