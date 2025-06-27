#!/usr/bin/env python3
"""
Setup script to install DuckDB extensions locally.
Run this once to avoid network download issues during pipeline execution.
"""

import duckdb
import sys
from pathlib import Path

def setup_extensions():
    """Install DuckDB extensions locally."""
    extensions_to_install = ['parquet', 'httpfs']

    print("Setting up DuckDB extensions...")

    # Test with in-memory database first
    conn = duckdb.connect()

    try:
        for extension in extensions_to_install:
            try:
                print(f"Installing {extension}...")
                conn.execute(f"INSTALL {extension};")
                conn.execute(f"LOAD {extension};")
                print(f"✅ {extension} installed and loaded successfully")
            except Exception as e:
                print(f"❌ Failed to install {extension}: {e}")

        # Verify all extensions
        print("\nVerifying installed extensions:")
        installed = conn.execute("""
            SELECT extension_name, installed, loaded
            FROM duckdb_extensions()
            WHERE extension_name IN ('parquet', 'httpfs')
            ORDER BY extension_name
        """).fetchall()

        for ext_name, installed, loaded in installed:
            status = "✅" if installed and loaded else "❌"
            print(f"{status} {ext_name}: installed={installed}, loaded={loaded}")

    except Exception as e:
        print(f"Error during setup: {e}")
        return False
    finally:
        conn.close()

    # Test with file database (your actual simulation database)
    db_path = Path(__file__).parent.parent / "simulation.duckdb"
    print(f"\nTesting with project database: {db_path}")

    if db_path.exists():
        conn = duckdb.connect(str(db_path))
        try:
            for extension in extensions_to_install:
                try:
                    conn.execute(f"LOAD {extension};")
                    print(f"✅ {extension} loaded in project database")
                except Exception as e:
                    print(f"⚠️  {extension} not available in project database: {e}")
        finally:
            conn.close()
    else:
        print("Project database doesn't exist yet - will be created on first run")

    print("\n🎉 DuckDB extension setup completed!")
    return True

if __name__ == "__main__":
    success = setup_extensions()
    sys.exit(0 if success else 1)
