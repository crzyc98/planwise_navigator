#!/bin/bash

# Storage Format Optimization Script for PlanWise Navigator
# Convert CSV seed files to Parquet format with ZSTD compression
# Author: Claude Code - Data Quality Auditor
# Epic: E068E - Engine & I/O Tuning

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SEEDS_DIR="$PROJECT_ROOT/dbt/seeds"
PARQUET_DIR="$PROJECT_ROOT/data/parquet"

# Color output for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}PlanWise Navigator - Storage Format Optimization${NC}"
echo "================================================="
echo ""

# Create Parquet directory structure
echo -e "${YELLOW}Creating Parquet directory structure...${NC}"
mkdir -p "$PARQUET_DIR"
echo "  ✓ Created: $PARQUET_DIR"

# Check for required Python packages
echo ""
echo -e "${YELLOW}Checking Python dependencies...${NC}"
python3 -c "
import pandas as pd
import pyarrow.parquet as pq
print('  ✓ pandas and pyarrow are available')
" || {
    echo -e "${RED}  ✗ Missing required packages. Please install: pip install pandas pyarrow${NC}"
    exit 1
}

# Convert CSV seeds to Parquet format
echo ""
echo -e "${YELLOW}Converting CSV seed files to Parquet format...${NC}"

SEEDS_DIR="$SEEDS_DIR" PARQUET_DIR="$PARQUET_DIR" python3 << 'EOF'
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
import os
import sys

# Configuration
seeds_dir = Path(os.environ['SEEDS_DIR'])
parquet_dir = Path(os.environ['PARQUET_DIR'])

# List of major seed files to prioritize (as mentioned in epic)
priority_files = [
    'census_data.csv',
    'comp_levers.csv',
    'plan_designs.csv',
    'baseline_workforce.csv'
]

# Get all CSV files in seeds directory
all_csv_files = list(seeds_dir.glob('*.csv'))

# Separate priority files from others
found_priority = []
other_files = []

for csv_file in all_csv_files:
    if csv_file.name in priority_files:
        found_priority.append(csv_file)
    else:
        other_files.append(csv_file)

# Sort by file size (largest first) for better progress visibility
found_priority.sort(key=lambda f: f.stat().st_size, reverse=True)
other_files.sort(key=lambda f: f.stat().st_size, reverse=True)

# Combine lists: priority first, then others
files_to_convert = found_priority + other_files

# Conversion statistics
total_csv_size = 0
total_parquet_size = 0
converted_count = 0
error_count = 0

print(f"Found {len(files_to_convert)} CSV files to convert")
print()

for csv_path in files_to_convert:
    try:
        # Read CSV file
        print(f"Converting {csv_path.name}...", end=" ", flush=True)
        df = pd.read_csv(csv_path)

        # Generate Parquet path
        parquet_filename = csv_path.stem + '.parquet'
        parquet_path = parquet_dir / parquet_filename

        # Convert to Parquet with ZSTD compression
        df.to_parquet(
            parquet_path,
            compression='zstd',      # High compression ratio as specified
            index=False,             # Don't include pandas index
            engine='pyarrow'         # Use pyarrow engine for best performance
        )

        # Calculate size comparison
        csv_size = csv_path.stat().st_size
        parquet_size = parquet_path.stat().st_size

        total_csv_size += csv_size
        total_parquet_size += parquet_size
        converted_count += 1

        # Calculate compression ratio
        if parquet_size > 0:
            compression_ratio = csv_size / parquet_size
        else:
            compression_ratio = float('inf')

        # Format sizes for display
        if csv_size < 1024:
            csv_display = f"{csv_size} B"
        elif csv_size < 1024 * 1024:
            csv_display = f"{csv_size / 1024:.1f} KB"
        else:
            csv_display = f"{csv_size / (1024 * 1024):.1f} MB"

        if parquet_size < 1024:
            parquet_display = f"{parquet_size} B"
        elif parquet_size < 1024 * 1024:
            parquet_display = f"{parquet_size / 1024:.1f} KB"
        else:
            parquet_display = f"{parquet_size / (1024 * 1024):.1f} MB"

        print(f"✓")
        print(f"    Size: {csv_display} (CSV) → {parquet_display} (Parquet)")
        print(f"    Compression: {compression_ratio:.1f}× smaller")
        print(f"    Rows: {len(df):,}, Columns: {len(df.columns)}")

        # Show column types for major files
        if csv_path.name in priority_files and len(df.columns) <= 10:
            print(f"    Schema: {', '.join([f'{col}({str(df[col].dtype)})' for col in df.columns[:5]])}{'...' if len(df.columns) > 5 else ''}")

        print()

    except Exception as e:
        print(f"✗ ERROR")
        print(f"    Error converting {csv_path.name}: {str(e)}")
        print()
        error_count += 1

# Summary statistics
print("=" * 50)
print("STORAGE OPTIMIZATION SUMMARY")
print("=" * 50)

if converted_count > 0:
    overall_compression = total_csv_size / total_parquet_size if total_parquet_size > 0 else float('inf')

    # Format total sizes
    if total_csv_size < 1024 * 1024:
        csv_total_display = f"{total_csv_size / 1024:.1f} KB"
    else:
        csv_total_display = f"{total_csv_size / (1024 * 1024):.1f} MB"

    if total_parquet_size < 1024 * 1024:
        parquet_total_display = f"{total_parquet_size / 1024:.1f} KB"
    else:
        parquet_total_display = f"{total_parquet_size / (1024 * 1024):.1f} MB"

    print(f"Converted files: {converted_count}")
    print(f"Total size reduction: {csv_total_display} → {parquet_total_display}")
    print(f"Overall compression: {overall_compression:.1f}× smaller")
    print(f"Space saved: {(total_csv_size - total_parquet_size) / 1024:.1f} KB")

if error_count > 0:
    print(f"Errors encountered: {error_count}")

# Performance expectations note
print()
print("PERFORMANCE NOTES:")
print("- Parquet files should provide 2-3× faster read performance than CSV")
print("- ZSTD compression provides optimal balance of compression ratio and decompression speed")
print("- Files are stored in data/parquet/ directory")
print("- Original CSV files in dbt/seeds/ are preserved")

# dbt integration reminder
print()
print("NEXT STEPS:")
print("1. Update dbt source configurations to use Parquet files")
print("2. Test model performance with new file format")
print("3. Monitor memory usage during dbt runs")
print("4. Consider updating CI/CD pipeline to run this optimization")

EOF

echo ""
echo -e "${GREEN}Storage format optimization completed successfully!${NC}"
echo ""
echo -e "${BLUE}Generated Files:${NC}"
echo "  Directory: $PARQUET_DIR"

# List generated Parquet files with sizes
if [ -d "$PARQUET_DIR" ] && [ "$(ls -A $PARQUET_DIR 2>/dev/null)" ]; then
    echo ""
    echo -e "${BLUE}Parquet Files Created:${NC}"
    ls -lh "$PARQUET_DIR"/*.parquet 2>/dev/null | while read -r line; do
        echo "  $line"
    done
else
    echo -e "${YELLOW}  No Parquet files were created${NC}"
fi

echo ""
echo -e "${BLUE}Integration Instructions:${NC}"
echo "  1. Update dbt sources in models/staging/sources.yml"
echo "  2. Modify staging models to use Parquet sources"
echo "  3. Test performance improvements with dbt run"
echo "  4. Monitor database size and query performance"

exit 0
EOF
