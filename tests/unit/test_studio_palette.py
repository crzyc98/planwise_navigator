"""Executable contract for the reconstructed Studio chart-palette audit."""

from __future__ import annotations

import pytest

from scripts.validate_studio_palette import validate_palette_source
from tests.fixtures.studio_theme import (
    ACCEPTED_LIGHT_PALETTE,
    DARK_SURFACE,
    LIGHT_SURFACE,
    RETIRED_PALETTE,
    load_palette_source,
)


pytestmark = pytest.mark.fast


def test_retired_palette_reproduces_published_hard_failures() -> None:
    report = validate_palette_source(
        RETIRED_PALETTE,
        surface=LIGHT_SURFACE,
        mode="light",
    )

    assert any("lightness" in failure.lower() for failure in report.hard_failures)
    assert any(
        "normal separation" in failure.lower() for failure in report.hard_failures
    )


def test_accepted_light_palette_reproduces_published_disposition() -> None:
    report = validate_palette_source(
        ACCEPTED_LIGHT_PALETTE,
        surface=LIGHT_SURFACE,
        mode="light",
    )

    assert report.hard_failures == ()
    assert any("contrast" in warning.lower() for warning in report.warnings)
    assert any("cvd" in warning.lower() for warning in report.warnings)


def test_accepted_light_palette_fails_published_dark_lightness_band() -> None:
    report = validate_palette_source(
        ACCEPTED_LIGHT_PALETTE,
        surface=DARK_SURFACE,
        mode="dark",
    )

    assert any("lightness" in failure.lower() for failure in report.hard_failures)


def test_runtime_palettes_are_unique_stable_and_accepted() -> None:
    source = load_palette_source()
    light = tuple(source["runtime"]["light"])
    dark = tuple(source["runtime"]["dark"])

    assert light == ACCEPTED_LIGHT_PALETTE
    assert len(light) == len(dark) == len(source["hue_order"]) == 6
    assert len(set(light)) == len(set(dark)) == 6
    assert light != dark

    for mode, colors in (("light", light), ("dark", dark)):
        report = validate_palette_source(
            colors,
            surface=source["surfaces"][mode],
            mode=mode,
        )
        assert report.hard_failures == (), report.format()


def test_palette_source_records_warning_mitigation() -> None:
    source = load_palette_source()

    assert "legend" in source["warning_mitigation"].lower()
    assert "table" in source["warning_mitigation"].lower()
