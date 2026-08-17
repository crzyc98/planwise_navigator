"""Dependency-free source contract for Studio semantic and chart theming."""

from __future__ import annotations

import re

import pytest

from tests.fixtures.studio_theme import (
    EXPECTED_COMPONENT_COUNT,
    EXPECTED_RECHARTS_CHART_COUNT,
    EXPECTED_RECHARTS_CONSUMER_COUNT,
    STUDIO_ROOT,
    component_files,
    recharts_chart_count,
    recharts_consumer_files,
)


pytestmark = pytest.mark.fast

FORBIDDEN_LITERAL_UTILITY = re.compile(
    r"(?:bg|text|border|divide|ring|placeholder)-(?:gray|slate)-\d+"
    r"|(?:bg|text|border)-white\b"
)
FORBIDDEN_INLINE_COLOR = re.compile(r"['\"]#[0-9A-Fa-f]{3,8}\b")


def _read(relative_path: str) -> str:
    return (STUDIO_ROOT / relative_path).read_text(encoding="utf-8")


def test_dynamic_studio_inventory_matches_reviewed_baseline() -> None:
    assert len(component_files()) == EXPECTED_COMPONENT_COUNT
    assert len(recharts_consumer_files()) == EXPECTED_RECHARTS_CONSUMER_COUNT
    assert recharts_chart_count() == EXPECTED_RECHARTS_CHART_COUNT


def test_theme_contract_has_closed_types_one_key_and_guarded_storage() -> None:
    theme = _read("theme/theme.ts")
    hook = _read("hooks/useTheme.ts")

    assert "'system' | 'light' | 'dark'" in theme
    assert "'light' | 'dark'" in theme
    assert "planalign.theme.v1" in theme
    assert "readExplicitThemePreference" in theme
    assert "writeExplicitThemePreference" in theme
    assert "clearExplicitThemePreference" in theme
    assert theme.count("try {") >= 3
    assert "ThemeContext" in theme
    assert "useContext(ThemeContext)" in hook


def test_semantic_token_families_and_tailwind_mapping_exist() -> None:
    css = _read("index.css")
    for token in (
        "--color-surface",
        "--color-surface-raised",
        "--color-surface-subtle",
        "--color-surface-input",
        "--color-surface-disabled",
        "--color-ink",
        "--color-ink-muted",
        "--color-ink-subtle",
        "--color-ink-inverse",
        "--color-border",
        "--color-border-strong",
        "--color-focus",
        "--color-success-surface",
        "--color-warning-surface",
        "--color-danger-surface",
        "--color-info-surface",
    ):
        assert token in css
    assert "@theme inline" in css
    assert ":root[data-theme='dark']" in css


def test_components_contain_no_legacy_neutral_or_inline_colors() -> None:
    offenders: list[str] = []
    chart_consumers = set(recharts_consumer_files())
    for path in (*component_files(), STUDIO_ROOT / "App.tsx"):
        source = path.read_text(encoding="utf-8")
        if FORBIDDEN_LITERAL_UTILITY.search(source):
            offenders.append(f"legacy utility: {path.relative_to(STUDIO_ROOT)}")
        if path not in chart_consumers and FORBIDDEN_INLINE_COLOR.search(source):
            offenders.append(f"inline color: {path.relative_to(STUDIO_ROOT)}")
    assert offenders == []


def test_every_recharts_consumer_uses_complete_shared_theme() -> None:
    offenders: list[str] = []
    for path in recharts_consumer_files():
        source = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(STUDIO_ROOT))
        if "useChartTheme" not in source:
            offenders.append(f"missing hook: {relative}")
        if FORBIDDEN_INLINE_COLOR.search(source):
            offenders.append(f"inline chart color: {relative}")
        if "CartesianGrid" in source and "chartTheme.grid.line" not in source:
            offenders.append(f"un-themed grid: {relative}")
        if ("XAxis" in source or "YAxis" in source) and "chartTheme.axis" not in source:
            offenders.append(f"un-themed axis: {relative}")
        if "Tooltip" in source and "chartTheme.tooltip" not in source:
            offenders.append(f"un-themed tooltip: {relative}")
        if "Legend" in source and "chartTheme.legendText" not in source:
            offenders.append(f"un-themed legend: {relative}")
    assert offenders == []


def test_chart_theme_is_resolved_complete_and_preserves_modulo() -> None:
    chart_theme = _read("theme/chartTheme.ts")
    hook = _read("hooks/useChartTheme.ts")

    for role in (
        "grid",
        "axis",
        "tooltip",
        "legendText",
        "categorical",
        "positive",
        "negative",
        "neutral",
        "anchor",
        "frontierOutline",
        "contribution",
    ):
        assert role in chart_theme
    assert "((index % length) + length) % length" in chart_theme
    assert "resolvedTheme" in hook
    assert "CHART_THEMES[resolvedTheme]" in hook


def test_bootstrap_provider_and_accessible_settings_share_one_contract() -> None:
    html = _read("index.html")
    index = _read("index.tsx")
    provider = _read("theme/ThemeProvider.tsx")
    layout = _read("components/Layout.tsx")

    assert html.index("planalign.theme.v1") < html.index('src="/index.tsx"')
    assert 'name="color-scheme"' in html
    assert "ThemeProvider" in index
    assert index.index("<ThemeProvider>") < index.index("<App />")
    assert "matchMedia" in provider
    assert "addEventListener('change'" in provider
    assert "removeEventListener('change'" in provider
    assert "document.documentElement.dataset.theme" in provider
    assert "document.documentElement.style.colorScheme" in provider
    assert "useTheme" in layout
    assert 'role="radiogroup"' in layout
    assert 'role="radio"' in layout
    assert "aria-checked" in layout
    for label in ("System", "Light", "Dark"):
        assert label in layout
    assert "isDarkMode" not in layout
    assert "window.location.reload" not in provider
    assert "window.location.reload" not in layout
