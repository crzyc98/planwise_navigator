"""Compare workbook values/types and export formatting, streaming large sheets.

ZIP/XML ordering, shared versus inline strings and solid-fill alpha bytes are
benign: they do not change Excel values or the displayed RGB background.
"""

from __future__ import annotations

import argparse
from itertools import zip_longest
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import load_workbook

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def layout(path: Path, index: int) -> tuple[dict[int, float], Any]:
    """Read only the worksheet prefix, before potentially millions of cells."""
    widths: dict[int, float] = {}
    pane = None
    with ZipFile(path) as archive:
        with archive.open(f"xl/worksheets/sheet{index}.xml") as stream:
            for _, node in ET.iterparse(stream, events=("start",)):
                if node.tag == NS + "sheetData":
                    break
                if node.tag == NS + "pane":
                    pane = node.get("topLeftCell")
                if node.tag == NS + "col":
                    for col in range(
                        int(node.attrib["min"]), int(node.attrib["max"]) + 1
                    ):
                        widths[col] = float(node.attrib["width"])
    return widths, pane


def header(cell: Any) -> tuple[Any, ...]:
    color = cell.fill.fgColor
    rgb = color.rgb[-6:] if color.type == "rgb" else (color.type, color.index)
    return cell.font.bold, cell.fill.patternType, rgb, str(cell.alignment)


def cell_differences(a: Any, b: Any, location: str, header_row: bool) -> list[str]:
    """Compare typed values and formatting, including blank cells before dates."""
    errors: list[str] = []
    if type(a.value) is not type(b.value) or a.value != b.value:
        errors.append(
            f"{location}: {a.value!r} ({type(a.value).__name__}) != "
            f"{b.value!r} ({type(b.value).__name__})"
        )
    # An absent cell has Excel's implicit General format. Comparing every data
    # format also covers NULLs that precede the first date in a date column.
    if not header_row and (a.number_format or "General") != (
        b.number_format or "General"
    ):
        errors.append(f"{location}: data number format differs")
    if header_row and header(a) != header(b):
        errors.append(f"{location}: header style differs")
    return errors


def compare_sheet(left: Any, right: Any) -> tuple[int, list[str]]:
    errors: list[str] = []
    count = 0
    for row_index, rows in enumerate(zip_longest(left.rows, right.rows), 1):
        if any(row is None for row in rows):
            return count, errors + [f"{left.title}: row count differs"]
        for col, (a, b) in enumerate(zip_longest(*rows), 1):
            count += 1
            if a is None or b is None:
                errors.append(f"{left.title} row {row_index}: column count differs")
                break
            differences = cell_differences(
                a, b, f"{left.title}!R{row_index}C{col}", row_index == 1
            )
            if len(errors) < 20:
                errors.extend(differences)
    return count, errors


def compare_workbooks(first: Path, second: Path) -> list[str]:
    errors: list[str] = []
    left = load_workbook(first, read_only=True)
    right = load_workbook(second, read_only=True)
    try:
        if left.sheetnames != right.sheetnames:
            return ["Sheet names/order differ"]
        for index, name in enumerate(left.sheetnames, 1):
            count, differences = compare_sheet(left[name], right[name])
            errors.extend(differences)
            if layout(first, index) != layout(second, index):
                errors.append(
                    f"{name}: column widths or freeze panes differ: {layout(first, index)} != {layout(second, index)}"
                )
            print(f"{name}: {count:,} cells compared", flush=True)
    finally:
        left.close()
        right.close()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    errors = compare_workbooks(args.first, args.second)
    for error in errors:
        print(error)
    print(f"{'FAIL' if errors else 'PASS'}: {len(errors)} differences")
    print(
        "Ignored: ZIP/XML ordering, inline/shared string encoding, solid-fill alpha (same displayed RGB)."
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
