#!/usr/bin/env python3
"""
Analyze compensation ranges from census data to inform job level configuration.

Usage:
    python scripts/analyze_compensation_ranges.py
    python scripts/analyze_compensation_ranges.py --census data/other_census.parquet
"""

import argparse
import pandas as pd
from pathlib import Path


def analyze_compensation_distribution(census_path: Path) -> pd.DataFrame:
    """Analyze overall compensation statistics."""
    df = pd.read_parquet(census_path)

    # Use employee_gross_compensation as the primary compensation field
    comp_series = df['employee_gross_compensation'].dropna()

    # Calculate comprehensive statistics
    stats = pd.DataFrame({
        'Metric': ['Count', 'Min', 'P5', 'P10', 'P25', 'Median', 'P75', 'P90', 'P95', 'Max', 'Mean', 'Std Dev'],
        'Value': [
            int(comp_series.count()),
            int(comp_series.min()),
            int(comp_series.quantile(0.05)),
            int(comp_series.quantile(0.10)),
            int(comp_series.quantile(0.25)),
            int(comp_series.median()),
            int(comp_series.quantile(0.75)),
            int(comp_series.quantile(0.90)),
            int(comp_series.quantile(0.95)),
            int(comp_series.max()),
            int(comp_series.mean()),
            int(comp_series.std())
        ]
    })

    return stats, comp_series


def suggest_compensation_bands(comp_series: pd.Series, num_bands: int = 5) -> pd.DataFrame:
    """Suggest compensation bands based on percentile distribution."""
    percentiles = [i / num_bands for i in range(num_bands + 1)]
    band_edges = [comp_series.quantile(p) for p in percentiles]

    bands = []
    for i in range(num_bands):
        band_min = int(band_edges[i])
        band_max = int(band_edges[i + 1])

        # Count employees in this band
        in_band = comp_series[(comp_series >= band_min) & (comp_series < band_max if i < num_bands - 1 else comp_series <= band_max)]
        count = len(in_band)
        median = int(in_band.median()) if len(in_band) > 0 else 0

        bands.append({
            'Band': f'Band {i + 1}',
            'Min': band_min,
            'Median': median,
            'Max': band_max,
            'Count': count,
            'Percentage': f'{count / len(comp_series) * 100:.1f}%'
        })

    return pd.DataFrame(bands)


def main():
    # Argument parsing
    parser = argparse.ArgumentParser(description='Analyze compensation ranges from census data')
    parser.add_argument('--census', type=Path,
                       default=Path(__file__).parent.parent / 'data' / 'census_preprocessed.parquet',
                       help='Path to census parquet file (default: data/census_preprocessed.parquet)')
    parser.add_argument('--bands', type=int, default=5,
                       help='Number of compensation bands to suggest (default: 5)')
    args = parser.parse_args()

    census_path = args.census

    if not census_path.exists():
        print(f"Error: Census file not found at {census_path}")
        return

    print("Analyzing compensation ranges from census data...")
    print(f"Source: {census_path}\n")

    stats, comp_series = analyze_compensation_distribution(census_path)

    print("=" * 80)
    print("COMPENSATION DISTRIBUTION ANALYSIS")
    print("=" * 80)
    print(stats.to_string(index=False))
    print("\n")

    # Suggest compensation bands
    bands = suggest_compensation_bands(comp_series, num_bands=args.bands)

    print("=" * 80)
    print(f"SUGGESTED COMPENSATION BANDS (n={args.bands})")
    print("=" * 80)
    print(bands.to_string(index=False))
    print("\n")

    print("Notes:")
    print("- Bands are based on equal percentile distribution")
    print("- P5/P95 percentiles recommended to avoid outliers when defining custom ranges")
    print("- Consider market data and organizational policy when finalizing bands")
    print("- Use --bands N to adjust the number of suggested bands")


if __name__ == '__main__':
    main()
