#!/usr/bin/env python3
"""Reconstruct and run the chart-palette audit documented in #497/#503.

The original audit was never checked into the repository. This module makes its
published hard gates durable: OKLCH lightness, chroma, adjacent OKLab distance,
simulated CVD distance, and WCAG surface contrast. The light-theme contrast and
close-CVD dispositions remain warnings when consumers provide secondary labels;
dark-theme surface contrast is a hard gate.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence


Mode = Literal["light", "dark"]
CheckResult = tuple[list[str], list[str], list[str]]

LIGHTNESS_BANDS: dict[Mode, tuple[float, float]] = {
    "light": (0.43, 0.77),
    "dark": (0.43, 0.65),
}
CHROMA_FLOOR = 0.10
NORMAL_DISTANCE_FLOOR = 15.0
CVD_FAILURE_FLOOR = 7.0
CVD_WARNING_FLOOR = 10.0
SURFACE_CONTRAST_FLOOR = 3.0

_CVD_MATRICES = {
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}


@dataclass(frozen=True)
class PaletteReport:
    """Deterministic validation result for one palette/surface pair."""

    mode: Mode
    surface: str
    colors: tuple[str, ...]
    hard_failures: tuple[str, ...]
    warnings: tuple[str, ...]
    details: tuple[str, ...]

    def format(self) -> str:
        lines = [
            f"Palette ({self.mode}, surface {self.surface}): {len(self.colors)} slots"
        ]
        lines.extend(f"  [FAIL] {item}" for item in self.hard_failures)
        lines.extend(f"  [WARN] {item}" for item in self.warnings)
        lines.extend(f"  [PASS] {item}" for item in self.details)
        return "\n".join(lines)


def _hex_to_srgb(color: str) -> tuple[float, float, float]:
    value = color.removeprefix("#")
    if len(value) != 6 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError(f"Expected six-digit hex color, received {color!r}")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (0, 2, 4))  # type: ignore[return-value]


def _linear_channel(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _linear_rgb(color: str) -> tuple[float, float, float]:
    return tuple(_linear_channel(channel) for channel in _hex_to_srgb(color))  # type: ignore[return-value]


def _oklab_from_linear(rgb: Sequence[float]) -> tuple[float, float, float]:
    red, green, blue = rgb
    l_value = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    m_value = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    s_value = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    l_root = math.copysign(abs(l_value) ** (1 / 3), l_value)
    m_root = math.copysign(abs(m_value) ** (1 / 3), m_value)
    s_root = math.copysign(abs(s_value) ** (1 / 3), s_value)
    return (
        0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root,
        1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root,
        0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root,
    )


def _oklab(color: str) -> tuple[float, float, float]:
    return _oklab_from_linear(_linear_rgb(color))


def _ok_distance(first: Sequence[float], second: Sequence[float]) -> float:
    return (
        math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second))) * 100
    )


def _relative_luminance(color: str) -> float:
    red, green, blue = _linear_rgb(color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    light, dark = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (light + 0.05) / (dark + 0.05)


def _simulate_cvd(
    color: str, matrix: Sequence[Sequence[float]]
) -> tuple[float, float, float]:
    rgb = _linear_rgb(color)
    simulated = tuple(
        max(0.0, min(1.0, sum(weight * channel for weight, channel in zip(row, rgb))))
        for row in matrix
    )
    return _oklab_from_linear(simulated)


def _adjacent_pairs(colors: Sequence[str]) -> Iterable[tuple[str, str]]:
    return zip(colors, colors[1:])


def _validate_structure(colors: tuple[str, ...]) -> list[str]:
    failures: list[str] = []
    if len(colors) != 6:
        failures.append(f"Slot count: expected 6, received {len(colors)}")
    if len(set(colors)) != len(colors):
        failures.append("Uniqueness: duplicate palette slots")
    return failures


def _validate_color_bounds(
    colors: tuple[str, ...],
    labs: dict[str, tuple[float, float, float]],
    mode: Mode,
) -> CheckResult:
    failures: list[str] = []
    details: list[str] = []
    minimum, maximum = LIGHTNESS_BANDS[mode]
    outside = [
        f"{color} ({labs[color][0]:.3f})"
        for color in colors
        if not minimum <= labs[color][0] <= maximum
    ]
    if outside:
        failures.append(
            f"Lightness band: outside {minimum:.2f}-{maximum:.2f}: "
            + ", ".join(outside)
        )
    else:
        details.append(f"Lightness band: all slots inside {minimum:.2f}-{maximum:.2f}")

    low_chroma = [
        f"{color} ({math.hypot(labs[color][1], labs[color][2]):.3f})"
        for color in colors
        if math.hypot(labs[color][1], labs[color][2]) < CHROMA_FLOOR
    ]
    if low_chroma:
        failures.append(
            f"Chroma floor: below {CHROMA_FLOOR:.2f}: {', '.join(low_chroma)}"
        )
    else:
        details.append(f"Chroma floor: all slots >= {CHROMA_FLOOR:.2f}")
    return failures, [], details


def _minimum_adjacent_distance(
    colors: tuple[str, ...],
    labs: dict[str, tuple[float, float, float]],
) -> tuple[str, float]:
    return min(
        (
            (f"{first}↔{second}", _ok_distance(labs[first], labs[second]))
            for first, second in _adjacent_pairs(colors)
        ),
        key=lambda item: item[1],
    )


def _validate_normal_distance(
    colors: tuple[str, ...],
    labs: dict[str, tuple[float, float, float]],
) -> CheckResult:
    if len(colors) < 2:
        return [], [], []
    pair, distance = _minimum_adjacent_distance(colors, labs)
    if distance < NORMAL_DISTANCE_FLOOR:
        return (
            [
                f"Normal separation: {pair} ΔE {distance:.1f} below "
                f"{NORMAL_DISTANCE_FLOOR:.0f}"
            ],
            [],
            [],
        )
    return [], [], [f"Normal separation: worst adjacent {pair} ΔE {distance:.1f}"]


def _validate_cvd_distance(
    colors: tuple[str, ...],
) -> CheckResult:
    if len(colors) < 2:
        return [], [], []
    results: list[tuple[str, str, float]] = []
    for vision, matrix in _CVD_MATRICES.items():
        simulated = {color: _simulate_cvd(color, matrix) for color in colors}
        pair, distance = _minimum_adjacent_distance(colors, simulated)
        results.append((vision, pair, distance))
    vision, pair, distance = min(results, key=lambda item: item[2])
    if distance < CVD_FAILURE_FLOOR:
        message = (
            f"CVD separation: {pair} ΔE {distance:.1f} ({vision}) below "
            f"{CVD_FAILURE_FLOOR:.0f}"
        )
        return [message], [], []
    if distance < CVD_WARNING_FLOOR:
        message = (
            f"CVD separation: {pair} ΔE {distance:.1f} ({vision}); "
            "requires legend plus table/direct labels"
        )
        return [], [message], []
    return (
        [],
        [],
        [f"CVD separation: worst adjacent {pair} ΔE {distance:.1f} ({vision})"],
    )


def _validate_contrast(
    colors: tuple[str, ...],
    surface: str,
    mode: Mode,
) -> CheckResult:
    low_contrast = [
        f"{color} ({_contrast(color, surface):.2f}:1)"
        for color in colors
        if _contrast(color, surface) < SURFACE_CONTRAST_FLOOR
    ]
    if not low_contrast:
        return (
            [],
            [],
            [f"Contrast vs surface: all slots >= {SURFACE_CONTRAST_FLOOR:.0f}:1"],
        )
    message = (
        f"Contrast vs surface: below {SURFACE_CONTRAST_FLOOR:.0f}:1: "
        + ", ".join(low_contrast)
    )
    if mode == "dark":
        return [message], [], []
    return [], [message + "; requires legend plus table/direct labels"], []


def validate_palette_source(
    colors: Sequence[str],
    *,
    surface: str,
    mode: Mode,
) -> PaletteReport:
    """Validate one ordered categorical ramp against the reconstructed gates."""

    normalized = tuple(color.upper() for color in colors)
    failures = _validate_structure(normalized)
    warnings: list[str] = []
    details: list[str] = []
    labs = {color: _oklab(color) for color in normalized}
    for check in (
        _validate_color_bounds(normalized, labs, mode),
        _validate_normal_distance(normalized, labs),
        _validate_cvd_distance(normalized),
        _validate_contrast(normalized, surface, mode),
    ):
        check_failures, check_warnings, check_details = check
        failures.extend(check_failures)
        warnings.extend(check_warnings)
        details.extend(check_details)

    return PaletteReport(
        mode=mode,
        surface=surface.upper(),
        colors=normalized,
        hard_failures=tuple(failures),
        warnings=tuple(warnings),
        details=tuple(details),
    )


def _default_palette_path() -> Path:
    return Path(__file__).parents[1] / "planalign_studio/theme/chart-palettes.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--palette", type=Path, default=_default_palette_path())
    args = parser.parse_args()
    source = json.loads(args.palette.read_text(encoding="utf-8"))
    reports = [
        validate_palette_source(
            source["runtime"][mode],
            surface=source["surfaces"][mode],
            mode=mode,
        )
        for mode in ("light", "dark")
    ]
    print("\n\n".join(report.format() for report in reports))
    return 1 if any(report.hard_failures for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
