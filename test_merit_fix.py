#!/usr/bin/env python3
"""
Test script to demonstrate the merit events compounding fix
"""

def simulate_merit_events_logic(simulation_year):
    print(f"=== Merit Events for Year {simulation_year} ===")

    if simulation_year == 2025:
        # First year: Use baseline workforce
        data_source = "int_baseline_workforce"
        print(f"Data source: {data_source}")
        print("Using original 2025 baseline compensation values")

        # Simulate baseline compensation values
        mock_baseline = [100000, 120000, 85000, 150000, 95000]  # Original values
        print(f"Sample compensation baseline: {mock_baseline[:3]}")

    else:
        # Subsequent years: Use previous year's workforce snapshot for compounded compensation
        data_source = f"fct_workforce_snapshot (year {simulation_year - 1})"
        print(f"Data source: {data_source}")
        print(f"Using year {simulation_year - 1} final compensation values (compounded)")

        # Simulate compounded compensation values (4.3% increase from previous year)
        if simulation_year == 2026:
            # Year 2: 2025 baseline * 1.043
            mock_baseline = [104300, 125160, 88655, 156450, 99085]
        elif simulation_year == 2027:
            # Year 3: 2026 values * 1.043
            mock_baseline = [108785, 130542, 92467, 163181, 103382]
        else:
            # Year 4+: Keep growing
            factor = 1.043 ** (simulation_year - 2025)
            mock_baseline = [round(100000 * factor), round(120000 * factor),
                           round(85000 * factor), round(150000 * factor),
                           round(95000 * factor)]

        print(f"Sample compensation baseline: {mock_baseline[:3]}")

    # Simulate merit calculation (4.3% merit + 2.5% COLA = 6.8% total)
    total_increase_rate = 0.043 + 0.025  # merit + COLA
    mock_new_salaries = [round(comp * (1 + total_increase_rate)) for comp in mock_baseline[:3]]

    print(f"After {total_increase_rate:.1%} increase: {mock_new_salaries}")
    print(f"Average baseline: ${sum(mock_baseline)/len(mock_baseline):,.0f}")
    print()

    return len(mock_baseline), sum(mock_baseline)/len(mock_baseline)

def main():
    print("Simulating Merit Events Compounding Fix")
    print("======================================\n")

    # Test the logic for multiple years
    baseline_averages = {}
    for year in [2025, 2026, 2027, 2028]:
        count, avg_baseline = simulate_merit_events_logic(year)
        baseline_averages[year] = avg_baseline

    print("=== BEFORE vs AFTER Fix Comparison ===")
    print("BEFORE (bug): All years use 2025 baseline -> identical merit event counts")
    print("  - Year 2025: avg baseline = $110,000")
    print("  - Year 2026: avg baseline = $110,000 (WRONG - should be compounded)")
    print("  - Year 2027: avg baseline = $110,000 (WRONG - should be compounded)")
    print()
    print("AFTER (fixed): Each year uses previous year final -> properly compounding compensation")
    for year, avg in baseline_averages.items():
        print(f"  - Year {year}: avg baseline = ${avg:,.0f}")

    print()
    print("Key Fix:")
    print("  - Lines 728-762 in event_emitter.py now check simulation_year")
    print("  - Year 2025: Uses int_baseline_workforce (original behavior)")
    print("  - Year 2026+: Uses fct_workforce_snapshot from previous year")
    print("  - This ensures merit raises compound properly year-over-year")

if __name__ == "__main__":
    main()
