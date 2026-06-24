#!/usr/bin/env python3
"""
Test script for database initialization functionality.

Quick validation that the init_database module works correctly.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from planalign_orchestrator.init_database import DatabaseInitializer  # noqa: E402


def test_database_initialization():
    """Test database initialization in a temporary location."""
    print("🧪 Testing database initialization...")

    # Use temporary file for testing
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Initialize database in temp location
        initializer = DatabaseInitializer(tmp_path)
        success = initializer.initialize_database(fresh=True)

        if success:
            print("✅ Database initialization test passed!")

            # Quick verification
            with initializer.get_connection() as conn:
                tables = conn.execute("SHOW TABLES").fetchall()
                print(f"📊 Created {len(tables)} tables:")
                for table in sorted(tables):
                    count = conn.execute(f"SELECT COUNT(*) FROM {table[0]}").fetchone()[
                        0
                    ]
                    print(f"   - {table[0]}: {count} rows")

            return True
        else:
            print("❌ Database initialization test failed!")
            return False

    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

    finally:
        # Clean up temp file
        if tmp_path.exists():
            tmp_path.unlink()


def test_config_integration():
    """Test config integration with get_database_path."""
    print("\n🔧 Testing config integration...")

    try:
        from planalign_orchestrator.config import get_database_path

        # Test default path
        default_path = get_database_path()
        print(f"📍 Default database path: {default_path}")

        # Test with environment variable
        import os

        os.environ["DATABASE_PATH"] = "test/custom.duckdb"
        custom_path = get_database_path()
        print(f"📍 Custom database path: {custom_path}")

        # Clean up env var
        del os.environ["DATABASE_PATH"]

        print("✅ Config integration test passed!")
        return True

    except Exception as e:
        print(f"❌ Config test error: {e}")
        return False


def main():
    """Run all tests."""
    print("PlanWise Navigator Database Initialization Tests")
    print("=================================================")

    tests = [
        test_config_integration,
        test_database_initialization,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")

    print(f"\n📊 Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("💥 Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
