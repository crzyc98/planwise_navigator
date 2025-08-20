#!/usr/bin/env python3
"""
Fix import order issues caused by automatic database path updates.

This script moves get_database_path imports to the proper location after
__future__ imports and other system imports.
"""

import re
import sys
from pathlib import Path


def fix_import_order(file_path: Path) -> bool:
    """Fix import order in a single Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check if the file has the problematic pattern
        if not content.startswith('from navigator_orchestrator.config import get_database_path'):
            return False  # Nothing to fix

        lines = content.split('\n')

        # Remove the misplaced import from the beginning
        if lines[0] == 'from navigator_orchestrator.config import get_database_path':
            lines = lines[1:]

        # Find the right place to insert it
        insert_index = 0
        in_imports = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip shebang, encoding, docstrings
            if stripped.startswith('#!') or stripped.startswith('# -*- coding'):
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # Skip to end of docstring
                quote = '"""' if stripped.startswith('"""') else "'''"
                if stripped.count(quote) == 1:  # Multi-line docstring
                    j = i + 1
                    while j < len(lines) and quote not in lines[j]:
                        j += 1
                    i = j  # Skip to end of docstring
                continue

            # Track when we're in the imports section
            if stripped.startswith('from __future__'):
                in_imports = True
                continue
            elif stripped.startswith('import ') or stripped.startswith('from '):
                in_imports = True
                insert_index = i + 1
            elif stripped == '':
                if in_imports:
                    insert_index = i
                continue
            else:
                # We've hit non-import code
                if not in_imports:
                    insert_index = i
                break

        # Insert the import at the proper location
        lines.insert(insert_index, 'from navigator_orchestrator.config import get_database_path')

        # Write the fixed content
        fixed_content = '\n'.join(lines)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

        print(f"✅ Fixed: {file_path}")
        return True

    except Exception as e:
        print(f"❌ Error fixing {file_path}: {e}")
        return False


def main():
    """Main script entry point."""
    # Get all files that need fixing
    import subprocess
    result = subprocess.run([
        'find', '.', '-name', '*.py', '-exec',
        'grep', '-l', '^from navigator_orchestrator.config import get_database_path', '{}', ';'
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print("No files found with import order issues")
        return 0

    files_to_fix = [Path(line.strip()) for line in result.stdout.strip().split('\n') if line.strip()]

    print(f"Found {len(files_to_fix)} files with import order issues")

    fixed_count = 0
    for file_path in files_to_fix:
        if fix_import_order(file_path):
            fixed_count += 1

    print(f"\n✅ Fixed {fixed_count} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
