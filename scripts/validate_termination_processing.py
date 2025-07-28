#!/usr/bin/env python3
"""
Validation script for termination event processing.

This script validates that termination events are properly applied to the workforce snapshot
by comparing event counts with final snapshot results.
"""

import sys
import os
from typing import Dict, Any

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator_mvp.core.database_manager import get_connection


def validate_termination_processing(simulation_year: int = 2025) -> Dict[str, Any]:
    """
    Validate that termination events are properly processed into workforce snapshot.

    Args:
        simulation_year: Year to validate

    Returns:
        Dictionary with validation results
    """
    conn = get_connection()

    try:
        # Count termination events by category
        events_query = """
        SELECT
            event_category,
            COUNT(*) as event_count
        FROM fct_yearly_events
        WHERE simulation_year = ?
        AND UPPER(event_type) = 'TERMINATION'
        GROUP BY event_category
        ORDER BY event_category
        """

        events_results = conn.execute(events_query, [simulation_year]).fetchall()
        events_by_category = {row[0]: row[1] for row in events_results}

        # Count total termination events
        total_events_query = """
        SELECT COUNT(*) as total_events
        FROM fct_yearly_events
        WHERE simulation_year = ?
        AND UPPER(event_type) = 'TERMINATION'
        """

        total_events = conn.execute(total_events_query, [simulation_year]).fetchone()[0]

        # Count terminated employees in workforce snapshot by detailed status
        snapshot_query = """
        SELECT
            detailed_status_code,
            COUNT(*) as employee_count
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        AND employment_status = 'terminated'
        GROUP BY detailed_status_code
        ORDER BY detailed_status_code
        """

        snapshot_results = conn.execute(snapshot_query, [simulation_year]).fetchall()
        terminated_by_status = {row[0]: row[1] for row in snapshot_results}

        # Count total terminated employees
        total_terminated_query = """
        SELECT COUNT(*) as total_terminated
        FROM fct_workforce_snapshot
        WHERE simulation_year = ?
        AND employment_status = 'terminated'
        """

        total_terminated = conn.execute(total_terminated_query, [simulation_year]).fetchone()[0]

        # Calculate validation results
        experienced_events = events_by_category.get('experienced_termination', 0)
        new_hire_events = events_by_category.get('new_hire_termination', 0)

        experienced_terminated = terminated_by_status.get('experienced_termination', 0)
        new_hire_terminated = terminated_by_status.get('new_hire_termination', 0)

        validation_results = {
            'simulation_year': simulation_year,
            'events': {
                'experienced_termination': experienced_events,
                'new_hire_termination': new_hire_events,
                'total': total_events
            },
            'snapshot': {
                'experienced_termination': experienced_terminated,
                'new_hire_termination': new_hire_terminated,
                'total': total_terminated
            },
            'validation': {
                'experienced_match': experienced_events == experienced_terminated,
                'new_hire_match': new_hire_events == new_hire_terminated,
                'total_match': total_events == total_terminated,
                'experienced_gap': experienced_events - experienced_terminated,
                'new_hire_gap': new_hire_events - new_hire_terminated,
                'total_gap': total_events - total_terminated
            }
        }

        # Overall validation status
        validation_results['validation']['overall_valid'] = (
            validation_results['validation']['experienced_match'] and
            validation_results['validation']['new_hire_match'] and
            validation_results['validation']['total_match']
        )

        return validation_results

    finally:
        conn.close()


def print_validation_report(results: Dict[str, Any]) -> None:
    """Print a formatted validation report."""
    print(f"\n{'='*60}")
    print(f"🔍 TERMINATION PROCESSING VALIDATION REPORT")
    print(f"{'='*60}")
    print(f"Simulation Year: {results['simulation_year']}")

    print(f"\n📊 EVENT COUNTS:")
    print(f"   • Experienced terminations: {results['events']['experienced_termination']:,}")
    print(f"   • New hire terminations: {results['events']['new_hire_termination']:,}")
    print(f"   • Total termination events: {results['events']['total']:,}")

    print(f"\n👥 WORKFORCE SNAPSHOT COUNTS:")
    print(f"   • Experienced terminated: {results['snapshot']['experienced_termination']:,}")
    print(f"   • New hire terminated: {results['snapshot']['new_hire_termination']:,}")
    print(f"   • Total terminated employees: {results['snapshot']['total']:,}")

    print(f"\n✅ VALIDATION RESULTS:")
    validation = results['validation']

    exp_status = "✅ PASS" if validation['experienced_match'] else "❌ FAIL"
    print(f"   • Experienced terminations: {exp_status}")
    if not validation['experienced_match']:
        print(f"     Gap: {validation['experienced_gap']:+} (events - snapshot)")

    nh_status = "✅ PASS" if validation['new_hire_match'] else "❌ FAIL"
    print(f"   • New hire terminations: {nh_status}")
    if not validation['new_hire_match']:
        print(f"     Gap: {validation['new_hire_gap']:+} (events - snapshot)")

    total_status = "✅ PASS" if validation['total_match'] else "❌ FAIL"
    print(f"   • Total terminations: {total_status}")
    if not validation['total_match']:
        print(f"     Gap: {validation['total_gap']:+} (events - snapshot)")

    overall_status = "✅ PASSED" if validation['overall_valid'] else "❌ FAILED"
    print(f"\n🎯 OVERALL VALIDATION: {overall_status}")

    if not validation['overall_valid']:
        print(f"\n💡 TROUBLESHOOTING HINTS:")
        if validation['experienced_gap'] > 0:
            print(f"   • {validation['experienced_gap']} experienced termination events not applied")
            print(f"   • Check event_category filter in int_snapshot_termination.sql")
            print(f"   • Verify employee_id matching between events and base workforce")
        if validation['new_hire_gap'] > 0:
            print(f"   • {validation['new_hire_gap']} new hire termination events not applied")
            print(f"   • Check new hire termination processing logic")
        if validation['total_gap'] < 0:
            print(f"   • More terminated employees than events - possible data duplication")


def main():
    """Main validation function."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate termination event processing")
    parser.add_argument(
        '--year',
        type=int,
        default=2025,
        help='Simulation year to validate (default: 2025)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON instead of formatted report'
    )

    args = parser.parse_args()

    try:
        results = validate_termination_processing(args.year)

        if args.json:
            import json
            print(json.dumps(results, indent=2))
        else:
            print_validation_report(results)

        # Exit with error code if validation failed
        if not results['validation']['overall_valid']:
            sys.exit(1)

    except Exception as e:
        print(f"❌ ERROR during validation: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
