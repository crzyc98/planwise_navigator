#!/usr/bin/env python3
"""
Analyze compensation ranges from census data to inform job level configuration.

Usage:
    python scripts/analyze_compensation_ranges.py
"""

import pandas as pd
from pathlib import Path


def analyze_compensation_by_level(census_path: Path) -> pd.DataFrame:
    """Analyze compensation statistics by job level."""
    df = pd.read_parquet(census_path)

    # Use CompensationAtYearStart as the primary compensation field
    # Group by employee_level and calculate statistics
    stats = df.groupby('employee_level')['CompensationAtYearStart'].agg([
        ('count', 'count'),
        ('min', 'min'),
        ('p5', lambda x: x.quantile(0.05)),
        ('p10', lambda x: x.quantile(0.10)),
        ('p25', lambda x: x.quantile(0.25)),
        ('median', 'median'),
        ('p75', lambda x: x.quantile(0.75)),
        ('p90', lambda x: x.quantile(0.90)),
        ('p95', lambda x: x.quantile(0.95)),
        ('max', 'max'),
        ('mean', 'mean'),
        ('std', 'std')
    ]).round(0)

    # Map level numbers to level names for readability
    level_names = {
        0: 'Level 0 (Unknown)',
        1: 'Level 1 (Staff)',
        2: 'Level 2 (Manager)',
        3: 'Level 3 (SrMgr)',
        4: 'Level 4 (Director)',
        5: 'Level 5 (VP)'
    }
    stats.index = stats.index.map(lambda x: level_names.get(x, f'Level {x}'))

    return stats


def main():
    # Path to census data
    census_path = Path(__file__).parent.parent / 'data' / 'original.parquet'

    if not census_path.exists():
        print(f"Error: Census file not found at {census_path}")
        return

    print("Analyzing compensation ranges by job level...")
    print(f"Source: {census_path}\n")

    stats = analyze_compensation_by_level(census_path)

    print("=" * 100)
    print("COMPENSATION ANALYSIS BY JOB LEVEL")
    print("=" * 100)
    print(stats.to_string())
    print("\n")

    print("=" * 100)
    print("RECOMMENDED RANGES (using P5 and P95 percentiles)")
    print("=" * 100)
    for level_name in stats.index:
        min_comp = int(stats.loc[level_name, 'p5'])
        max_comp = int(stats.loc[level_name, 'p95'])
        median_comp = int(stats.loc[level_name, 'median'])
        count = int(stats.loc[level_name, 'count'])

        print(f"{level_name:25} (n={count:5}): min={min_comp:>9,}  median={median_comp:>9,}  max={max_comp:>9,}")

    print("\n")
    print("Notes:")
    print("- P5/P95 percentiles recommended to avoid outliers")
    print("- Ensure no gaps between level max and next level min")
    print("- Consider market data and organizational policy")


if __name__ == '__main__':
    main()
