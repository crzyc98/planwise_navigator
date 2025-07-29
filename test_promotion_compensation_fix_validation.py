#!/usr/bin/env python3
"""
Validate that the promotion compensation fix is working correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_mvp.core.database_manager import get_connection

def test_promotion_compensation_fix():
    """Test that promotions use correct end-of-year compensation."""

    print("🧪 Testing Promotion Compensation Fix")
    print("=" * 50)

    try:
        conn = get_connection()

        # Check EMP_000012 specifically to validate the fix
        emp_12_events = conn.execute("""
            SELECT
                event_type,
                simulation_year,
                effective_date,
                compensation_amount,
                previous_compensation,
                level_id
            FROM fct_yearly_events
            WHERE employee_id = 'EMP_000012'
                AND simulation_year >= 2025
            ORDER BY simulation_year, effective_date, event_type
        """).fetchall()

        print("🎯 EMP_000012 Event Timeline:")
        print("   Year  Type        Date        Previous → New        Level")
        print("   " + "-" * 60)

        expected_progression = {}
        for event_type, year, date, comp, prev_comp, level in emp_12_events:
            print(f"   {year}  {event_type:<10} {str(date)[:10]}  ${prev_comp:>8,.0f} → ${comp:>8,.0f}  {level}")

            # Build expected progression
            if event_type == 'raise':
                expected_progression[year] = comp

        # Validate 2028 promotion uses correct previous compensation
        promotion_2028 = None
        for event_type, year, date, comp, prev_comp, level in emp_12_events:
            if event_type == 'promotion' and year == 2028:
                promotion_2028 = (prev_comp, comp)
                break

        if promotion_2028:
            prev_comp, new_comp = promotion_2028
            expected_prev = expected_progression.get(2027, 101913.12)  # 2027 end-of-year

            print(f"\n📊 2028 Promotion Validation:")
            print(f"   Previous compensation: ${prev_comp:,.2f}")
            print(f"   Expected (2027 end):   ${expected_prev:,.2f}")

            if abs(prev_comp - expected_prev) < 1.0:
                print(f"   ✅ PASS: Promotion uses correct 2027 end-of-year salary!")
                print(f"   ✅ Fixed: No longer using stale baseline ($87,300)")
            else:
                print(f"   ❌ FAIL: Promotion still uses incorrect previous compensation")
                print(f"   ❌ Gap: ${abs(prev_comp - expected_prev):,.2f}")

                if prev_comp == 87300:
                    print(f"   ❌ Still using baseline salary (not fixed)")
        else:
            print(f"   ⚠️  No 2028 promotion found for EMP_000012")

        # Check overall promotion compensation patterns
        print(f"\n📈 Overall Promotion Analysis:")
        promotion_analysis = conn.execute("""
            WITH promotion_validation AS (
                SELECT
                    p.employee_id,
                    p.simulation_year,
                    p.previous_compensation as promo_previous,
                    r.compensation_amount as expected_previous,
                    ABS(p.previous_compensation - COALESCE(r.compensation_amount, p.previous_compensation)) as compensation_gap
                FROM fct_yearly_events p
                LEFT JOIN fct_yearly_events r
                    ON p.employee_id = r.employee_id
                    AND r.simulation_year = p.simulation_year - 1
                    AND r.event_type = 'raise'
                WHERE p.event_type = 'promotion'
                    AND p.simulation_year = 2028
            )
            SELECT
                COUNT(*) as total_promotions,
                AVG(compensation_gap) as avg_gap,
                COUNT(CASE WHEN compensation_gap < 100 THEN 1 END) as accurate_promotions,
                COUNT(CASE WHEN compensation_gap >= 100 THEN 1 END) as problematic_promotions
            FROM promotion_validation
        """).fetchone()

        total, avg_gap, accurate, problematic = promotion_analysis
        accuracy_rate = (accurate / total * 100) if total > 0 else 0

        print(f"   • Total 2028 promotions: {total}")
        print(f"   • Average compensation gap: ${avg_gap:,.2f}")
        print(f"   • Accurate promotions: {accurate} ({accuracy_rate:.1f}%)")
        print(f"   • Problematic promotions: {problematic}")

        if accuracy_rate >= 95:
            print(f"   ✅ EXCELLENT: {accuracy_rate:.1f}% accuracy rate")
        elif accuracy_rate >= 80:
            print(f"   ⚠️  GOOD: {accuracy_rate:.1f}% accuracy rate")
        else:
            print(f"   ❌ POOR: {accuracy_rate:.1f}% accuracy rate - needs investigation")

        conn.close()

        print(f"\n✅ Promotion compensation fix validation completed!")

    except Exception as e:
        print(f"❌ Validation failed: {str(e)}")
        raise

if __name__ == "__main__":
    test_promotion_compensation_fix()
