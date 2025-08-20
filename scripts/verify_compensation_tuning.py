#!/usr/bin/env python3
"""
Quick verification of compensation parameter tuning
"""


def calculate_expected_growth():
    """Calculate expected growth with tuned parameters"""

    # Level distribution (approximate)
    level_distribution = {
        1: 0.35,  # 35% Level 1
        2: 0.30,  # 30% Level 2
        3: 0.20,  # 20% Level 3
        4: 0.10,  # 10% Level 4
        5: 0.05,  # 5% Level 5
    }

    # Tuned parameters
    merit_rates = {
        1: 0.020,  # 2.0%
        2: 0.022,  # 2.2%
        3: 0.024,  # 2.4%
        4: 0.026,  # 2.6%
        5: 0.028,  # 2.8%
    }

    cola_rates = {
        1: 0.015,  # 1.5%
        2: 0.013,  # 1.3%
        3: 0.011,  # 1.1%
        4: 0.009,  # 0.9%
        5: 0.007,  # 0.7%
    }

    # Calculate weighted average growth
    total_growth = 0
    for level, weight in level_distribution.items():
        level_growth = merit_rates[level] + cola_rates[level]
        total_growth += level_growth * weight
        print(
            f"Level {level}: {merit_rates[level]:.1%} merit + {cola_rates[level]:.1%} COLA = {level_growth:.1%} (weight: {weight:.0%})"
        )

    print(f"\nWeighted Average Growth: {total_growth:.2%}")

    # New hire impact (approximately -0.5% dilution)
    new_hire_dilution = -0.005
    print(f"New Hire Dilution Effect: {new_hire_dilution:.1%}")

    # Final expected growth
    expected_growth = total_growth + new_hire_dilution
    print(f"\nExpected Total Compensation Growth: {expected_growth:.2%}")

    if 2.8 <= expected_growth * 100 <= 3.2:
        print("✅ Parameters are well-tuned for 3% target!")
    else:
        print(
            f"❌ Parameters need adjustment (off by {(expected_growth - 0.03)*100:+.1f}%)"
        )


if __name__ == "__main__":
    print("COMPENSATION PARAMETER VERIFICATION")
    print("=" * 50)
    calculate_expected_growth()
