#!/usr/bin/env python3
"""
Database Path Standardization Update Script - Epic E050, Story S050-03

This script automatically updates all Python files to use the standardized
database path configuration instead of hardcoded legacy paths.

Usage:
    python scripts/update_database_paths.py [--dry-run] [--file PATTERN]
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


class DatabasePathUpdater:
    """Updates Python files to use standardized database paths."""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.updated_files = []
        self.skipped_files = []
        self.errors = []

    def get_files_to_update(self, pattern: str = "**/*.py") -> List[Path]:
        """Get list of Python files that need updating."""
        files = []
        for py_file in self.project_root.glob(pattern):
            # Skip files that should not be updated
            if self._should_skip_file(py_file):
                continue

            # Check if file contains legacy patterns
            if self._contains_legacy_patterns(py_file):
                files.append(py_file)

        return files

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped from updates."""
        skip_patterns = [
            # Skip the migration utility itself
            "migrate_database_location.py",
            # Skip this update script
            "update_database_paths.py",
            # Skip test files that check for legacy patterns
            "test_no_legacy_db_paths.py",
            # Skip virtual environment
            "/venv/",
            "/.venv/",
            # Skip git directory
            "/.git/",
            # Skip compiled Python
            "__pycache__",
            ".pyc",
        ]

        file_str = str(file_path)
        return any(pattern in file_str for pattern in skip_patterns)

    def _contains_legacy_patterns(self, file_path: Path) -> bool:
        """Check if file contains legacy database path patterns."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Look for legacy patterns
            legacy_patterns = [
                r'duckdb\.connect\(\s*[\'"]simulation\.duckdb[\'"]',
                r'Path\(\s*[\'"]simulation\.duckdb[\'"]',
                r'[\'"]simulation\.duckdb[\'"](?!\s*#)',  # Exclude comments
            ]

            return any(re.search(pattern, content) for pattern in legacy_patterns)

        except Exception:
            return False

    def update_file(self, file_path: Path, dry_run: bool = False) -> bool:
        """Update a single file to use standardized database paths."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            updated_content = self._apply_transformations(original_content, file_path)

            if updated_content == original_content:
                self.skipped_files.append((file_path, "No changes needed"))
                return True

            if dry_run:
                print(f"Would update: {file_path}")
                self._show_diff(original_content, updated_content, file_path)
                return True

            # Write updated content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)

            self.updated_files.append(file_path)
            print(f"✅ Updated: {file_path}")
            return True

        except Exception as e:
            error_msg = f"Failed to update {file_path}: {e}"
            self.errors.append(error_msg)
            print(f"❌ {error_msg}")
            return False

    def _apply_transformations(self, content: str, file_path: Path) -> str:
        """Apply database path transformations to file content."""
        updated_content = content

        # Check if file already has the import
        has_import = 'from navigator_orchestrator.config import get_database_path' in content

        # Transformation 1: Direct duckdb.connect calls
        pattern1 = r'duckdb\.connect\(\s*[\'"]simulation\.duckdb[\'\"]\s*\)'
        if re.search(pattern1, content):
            if not has_import:
                # Add import at the top after other imports
                import_line = "from navigator_orchestrator.config import get_database_path"
                updated_content = self._add_import(updated_content, import_line)
                has_import = True

            # Replace the connect call
            updated_content = re.sub(
                pattern1,
                'duckdb.connect(str(get_database_path()))',
                updated_content
            )

        # Transformation 2: Path construction
        pattern2 = r'Path\(\s*[\'"]simulation\.duckdb[\'\"]\s*\)'
        if re.search(pattern2, content):
            if not has_import:
                import_line = "from navigator_orchestrator.config import get_database_path"
                updated_content = self._add_import(updated_content, import_line)
                has_import = True

            updated_content = re.sub(pattern2, 'get_database_path()', updated_content)

        # Transformation 3: String literals (more careful)
        pattern3 = r'([\'"])simulation\.duckdb\1(?!\s*#)'
        if re.search(pattern3, content):
            if not has_import:
                import_line = "from navigator_orchestrator.config import get_database_path"
                updated_content = self._add_import(updated_content, import_line)
                has_import = True

            # This is trickier - need to replace with str(get_database_path())
            # but only in appropriate contexts
            updated_content = re.sub(
                pattern3,
                'str(get_database_path())',
                updated_content
            )

        return updated_content

    def _add_import(self, content: str, import_line: str) -> str:
        """Add import line in the appropriate location."""
        lines = content.split('\n')

        # Find the best place to insert the import
        insert_index = 0

        # Skip shebang and docstring
        for i, line in enumerate(lines):
            if line.startswith('#!') or line.startswith('"""') or line.startswith("'''"):
                continue
            if line.strip() == '':
                continue
            if line.startswith('import ') or line.startswith('from '):
                insert_index = i + 1
            else:
                break

        # Insert the import
        lines.insert(insert_index, import_line)
        return '\n'.join(lines)

    def _show_diff(self, original: str, updated: str, file_path: Path) -> None:
        """Show differences between original and updated content."""
        print(f"\nChanges for {file_path}:")
        print("-" * 40)

        original_lines = original.split('\n')
        updated_lines = updated.split('\n')

        for i, (orig, upd) in enumerate(zip(original_lines, updated_lines)):
            if orig != upd:
                print(f"Line {i+1}:")
                print(f"  - {orig}")
                print(f"  + {upd}")

    def update_all_files(self, pattern: str = "**/*.py", dry_run: bool = False) -> None:
        """Update all files matching the pattern."""
        files_to_update = self.get_files_to_update(pattern)

        if not files_to_update:
            print("No files need updating!")
            return

        print(f"Found {len(files_to_update)} files to update:")
        for file_path in files_to_update:
            print(f"  - {file_path}")

        print()

        if dry_run:
            print("DRY RUN - No files will be modified")
            print("-" * 40)

        for file_path in files_to_update:
            self.update_file(file_path, dry_run)

    def generate_report(self) -> str:
        """Generate update report."""
        report_lines = [
            "=" * 60,
            "DATABASE PATH STANDARDIZATION REPORT",
            "=" * 60,
            f"Project Root: {self.project_root}",
            f"Updated Files: {len(self.updated_files)}",
            f"Skipped Files: {len(self.skipped_files)}",
            f"Errors: {len(self.errors)}",
            "",
        ]

        if self.updated_files:
            report_lines.extend([
                "Updated Files:",
                "-" * 20,
            ])
            for file_path in self.updated_files:
                report_lines.append(f"  ✅ {file_path}")
            report_lines.append("")

        if self.skipped_files:
            report_lines.extend([
                "Skipped Files:",
                "-" * 20,
            ])
            for file_path, reason in self.skipped_files:
                report_lines.append(f"  ⏭️  {file_path} ({reason})")
            report_lines.append("")

        if self.errors:
            report_lines.extend([
                "Errors:",
                "-" * 20,
            ])
            for error in self.errors:
                report_lines.append(f"  ❌ {error}")
            report_lines.append("")

        report_lines.extend([
            "Next Steps:",
            "-" * 20,
            "1. Run tests to verify all changes work correctly",
            "2. Test applications with updated database paths",
            "3. Commit changes to version control",
            "=" * 60
        ])

        return "\n".join(report_lines)


def main():
    """Main script entry point."""
    parser = argparse.ArgumentParser(
        description="Update Python files to use standardized database paths",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check what would be updated
    python scripts/update_database_paths.py --dry-run

    # Update all Python files
    python scripts/update_database_paths.py

    # Update specific files
    python scripts/update_database_paths.py --file "tests/*.py"
        """
    )

    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--file", type=str, default="**/*.py",
        help="File pattern to update (default: **/*.py)"
    )
    parser.add_argument(
        "--project-root", type=Path,
        help="Project root directory (default: current directory)"
    )

    args = parser.parse_args()

    # Initialize updater
    updater = DatabasePathUpdater(args.project_root)

    # Update files
    updater.update_all_files(args.file, args.dry_run)

    # Generate report
    report = updater.generate_report()
    print("\n" + report)

    # Save report if not dry run
    if not args.dry_run:
        report_path = updater.project_root / "database_path_update_report.txt"
        try:
            with open(report_path, "w") as f:
                f.write(report)
            print(f"\nUpdate report saved to: {report_path}")
        except Exception as e:
            print(f"Warning: Could not save report: {e}")

    # Return appropriate exit code
    return 0 if not updater.errors else 1


if __name__ == "__main__":
    sys.exit(main())
