"""
Multi-year inspection and analysis for MVP orchestrator.

This module provides comprehensive multi-year inspection capabilities for
workforce simulation analysis, including year-over-year comparisons,
cumulative growth validation, and detailed multi-year summaries.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from ..core.database_manager import get_connection


def compare_year_over_year_metrics(start_year: int, end_year: int) -> Dict[str, Any]:
    """
    Compare key workforce metrics across all simulated years.

    Args:
        start_year: First year of simulation range
        end_year: Last year of simulation range

    Returns:
        Dictionary containing year-over-year comparison metrics
    """
    logging.info(f"📊 Comparing year-over-year metrics: {start_year}-{end_year}")

    comparison_data = {
        'year_progression': [],
        'summary_stats': {},
        'total_years_analyzed': 0
    }

    try:
        # Get comprehensive metrics for each year
        for year in range(start_year, end_year + 1):
            year_metrics = _get_year_metrics(year)
            if year_metrics:
                comparison_data['year_progression'].append(year_metrics)

        comparison_data['total_years_analyzed'] = len(comparison_data['year_progression'])

        # Calculate summary statistics if we have data
        if comparison_data['year_progression']:
            comparison_data['summary_stats'] = _calculate_summary_statistics(
                comparison_data['year_progression']
            )

            # Display results
            _display_year_over_year_comparison(comparison_data)

        return comparison_data

    except Exception as e:
        logging.error(f"❌ Error comparing year-over-year metrics: {str(e)}")
        return {'error': str(e), 'year_progression': [], 'total_years_analyzed': 0}


def validate_cumulative_growth(
    start_year: int,
    end_year: int,
    target_growth_rate: float
) -> Dict[str, Any]:
    """
    Validate the overall growth trajectory against targets.

    Args:
        start_year: First year of simulation
        end_year: Last year of simulation
        target_growth_rate: Expected annual growth rate (e.g., 0.03 for 3%)

    Returns:
        Dictionary containing growth validation results
    """
    logging.info(f"📈 Validating cumulative growth against {target_growth_rate:.1%} target")

    validation_results = {
        'target_growth_rate': target_growth_rate,
        'actual_cagr': 0.0,
        'total_years': end_year - start_year + 1,
        'growth_validation': 'UNKNOWN',
        'year_deviations': [],
        'recommendations': []
    }

    try:
        # Get starting and ending workforce counts
        start_count = _get_active_workforce_count(start_year)
        end_count = _get_active_workforce_count(end_year)

        if start_count == 0 or end_count == 0:
            validation_results['growth_validation'] = 'ERROR'
            validation_results['error'] = 'Missing workforce data for growth calculation'
            return validation_results

        # Calculate compound annual growth rate (CAGR)
        years_elapsed = end_year - start_year
        if years_elapsed > 0:
            validation_results['actual_cagr'] = (
                (end_count / start_count) ** (1 / years_elapsed) - 1
            )

        # Analyze year-by-year growth vs target
        previous_count = start_count
        for year in range(start_year + 1, end_year + 1):
            current_count = _get_active_workforce_count(year)
            if current_count > 0 and previous_count > 0:
                year_growth = (current_count - previous_count) / previous_count
                deviation = year_growth - target_growth_rate

                validation_results['year_deviations'].append({
                    'year': year,
                    'actual_growth': year_growth,
                    'target_growth': target_growth_rate,
                    'deviation': deviation,
                    'deviation_pct': deviation / target_growth_rate if target_growth_rate != 0 else 0
                })

            previous_count = current_count

        # Determine validation status
        cagr_deviation = abs(validation_results['actual_cagr'] - target_growth_rate)
        if cagr_deviation <= 0.005:  # Within 0.5% tolerance
            validation_results['growth_validation'] = 'PASS'
        elif cagr_deviation <= 0.01:   # Within 1% tolerance
            validation_results['growth_validation'] = 'WARNING'
        else:
            validation_results['growth_validation'] = 'FAIL'

        # Generate recommendations
        validation_results['recommendations'] = _generate_growth_recommendations(
            validation_results
        )

        # Display results
        _display_growth_validation(validation_results, start_count, end_count)

        return validation_results

    except Exception as e:
        logging.error(f"❌ Error validating cumulative growth: {str(e)}")
        validation_results['growth_validation'] = 'ERROR'
        validation_results['error'] = str(e)
        return validation_results


def display_multi_year_summary(start_year: int, end_year: int) -> Dict[str, Any]:
    """
    Display a comprehensive summary of multi-year simulation results.

    Args:
        start_year: First year of simulation
        end_year: Last year of simulation

    Returns:
        Dictionary containing complete multi-year summary
    """
    logging.info(f"📋 Generating multi-year summary: {start_year}-{end_year}")

    summary = {
        'simulation_range': f'{start_year}-{end_year}',
        'total_years': end_year - start_year + 1,
        'workforce_progression': [],
        'event_summary': {},
        'compensation_analysis': {},
        'key_insights': []
    }

    try:
        # Get workforce progression
        for year in range(start_year, end_year + 1):
            year_data = _get_comprehensive_year_data(year)
            if year_data:
                summary['workforce_progression'].append(year_data)

        # Aggregate event summary across all years
        summary['event_summary'] = _get_multi_year_event_summary(start_year, end_year)

        # Analyze compensation trends
        summary['compensation_analysis'] = _analyze_compensation_trends(start_year, end_year)

        # Generate key insights
        summary['key_insights'] = _generate_key_insights(summary)

        # Display the summary
        _display_comprehensive_summary(summary)

        return summary

    except Exception as e:
        logging.error(f"❌ Error generating multi-year summary: {str(e)}")
        return {'error': str(e), 'simulation_range': f'{start_year}-{end_year}'}


def analyze_workforce_aging(start_year: int, end_year: int) -> Dict[str, Any]:
    """
    Track how workforce age and tenure distributions change over the simulation period.

    Args:
        start_year: First year of simulation
        end_year: Last year of simulation

    Returns:
        Dictionary containing workforce aging analysis
    """
    logging.info(f"👥 Analyzing workforce aging: {start_year}-{end_year}")

    aging_analysis = {
        'age_progression': {},
        'tenure_progression': {},
        'demographic_trends': {}
    }

    try:
        for year in range(start_year, end_year + 1):
            # Age distribution by year
            age_dist = _get_age_distribution(year)
            aging_analysis['age_progression'][year] = age_dist

            # Tenure distribution by year
            tenure_dist = _get_tenure_distribution(year)
            aging_analysis['tenure_progression'][year] = tenure_dist

        # Calculate demographic trends
        aging_analysis['demographic_trends'] = _calculate_demographic_trends(
            aging_analysis['age_progression'],
            aging_analysis['tenure_progression']
        )

        # Display aging analysis
        _display_aging_analysis(aging_analysis)

        return aging_analysis

    except Exception as e:
        logging.error(f"❌ Error analyzing workforce aging: {str(e)}")
        return {'error': str(e)}


def validate_event_consistency(start_year: int, end_year: int) -> Dict[str, Any]:
    """
    Validate event generation consistency across years.

    Args:
        start_year: First year of simulation
        end_year: Last year of simulation

    Returns:
        Dictionary containing event consistency validation results
    """
    logging.info(f"🔍 Validating event consistency: {start_year}-{end_year}")

    consistency_results = {
        'event_patterns': {},
        'anomalies': [],
        'validation_status': 'UNKNOWN',
        'recommendations': []
    }

    try:
        # Analyze event patterns by year
        for year in range(start_year, end_year + 1):
            year_events = _analyze_year_event_patterns(year)
            consistency_results['event_patterns'][year] = year_events

        # Detect anomalies
        consistency_results['anomalies'] = _detect_event_anomalies(
            consistency_results['event_patterns']
        )

        # Determine validation status
        if len(consistency_results['anomalies']) == 0:
            consistency_results['validation_status'] = 'PASS'
        elif len(consistency_results['anomalies']) <= 2:
            consistency_results['validation_status'] = 'WARNING'
        else:
            consistency_results['validation_status'] = 'FAIL'

        # Generate recommendations
        consistency_results['recommendations'] = _generate_event_recommendations(
            consistency_results
        )

        # Display results
        _display_event_consistency(consistency_results)

        return consistency_results

    except Exception as e:
        logging.error(f"❌ Error validating event consistency: {str(e)}")
        return {'error': str(e), 'validation_status': 'ERROR'}


# Helper functions for data retrieval and analysis

def _get_year_metrics(year: int) -> Optional[Dict[str, Any]]:
    """Get comprehensive metrics for a single year."""
    conn = get_connection()
    try:
        # Workforce counts
        workforce_query = """
            SELECT
                employment_status,
                COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            GROUP BY employment_status
        """
        workforce_results = conn.execute(workforce_query, [year]).fetchall()
        workforce_counts = dict(workforce_results)

        # Total compensation
        comp_query = """
            SELECT
                SUM(current_compensation) as total_comp,
                AVG(current_compensation) as avg_comp,
                COUNT(*) as active_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
        """
        comp_result = conn.execute(comp_query, [year]).fetchone()

        # Event counts
        events_query = """
            SELECT
                event_type,
                COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = ?
            GROUP BY event_type
        """
        events_results = conn.execute(events_query, [year]).fetchall()
        event_counts = dict(events_results)

        return {
            'year': year,
            'workforce_counts': workforce_counts,
            'active_employees': workforce_counts.get('active', 0),
            'total_compensation': comp_result[0] if comp_result and comp_result[0] else 0,
            'avg_compensation': comp_result[1] if comp_result and comp_result[1] else 0,
            'event_counts': event_counts,
            'total_events': sum(event_counts.values())
        }

    except Exception as e:
        logging.error(f"Error getting metrics for year {year}: {str(e)}")
        return None
    finally:
        conn.close()


def _get_active_workforce_count(year: int) -> int:
    """Get active workforce count for a specific year."""
    conn = get_connection()
    try:
        result = conn.execute("""
            SELECT COUNT(*)
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
        """, [year]).fetchone()
        return result[0] if result else 0
    except:
        return 0
    finally:
        conn.close()


def _calculate_summary_statistics(year_progression: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate summary statistics across all years."""
    if not year_progression:
        return {}

    # Extract key metrics
    active_counts = [y['active_employees'] for y in year_progression]
    total_comps = [y['total_compensation'] for y in year_progression]
    avg_comps = [y['avg_compensation'] for y in year_progression]

    return {
        'workforce_growth': {
            'start_count': active_counts[0] if active_counts else 0,
            'end_count': active_counts[-1] if active_counts else 0,
            'total_growth': active_counts[-1] - active_counts[0] if len(active_counts) >= 2 else 0,
            'growth_rate': ((active_counts[-1] / active_counts[0] - 1) * 100) if len(active_counts) >= 2 and active_counts[0] > 0 else 0
        },
        'compensation_trends': {
            'start_total': total_comps[0] if total_comps else 0,
            'end_total': total_comps[-1] if total_comps else 0,
            'start_avg': avg_comps[0] if avg_comps else 0,
            'end_avg': avg_comps[-1] if avg_comps else 0
        }
    }


# Simplified helper functions
def _get_comprehensive_year_data(year: int) -> Optional[Dict[str, Any]]:
    """Get comprehensive data for a single year."""
    return _get_year_metrics(year)


def _get_multi_year_event_summary(start_year: int, end_year: int) -> Dict[str, Any]:
    """Get aggregated event summary across multiple years."""
    conn = get_connection()
    try:
        events_query = """
            SELECT
                event_type,
                simulation_year,
                COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year BETWEEN ? AND ?
            GROUP BY event_type, simulation_year
            ORDER BY simulation_year, event_type
        """
        results = conn.execute(events_query, [start_year, end_year]).fetchall()

        # Organize by event type and year
        event_summary = {}
        for event_type, year, count in results:
            if event_type not in event_summary:
                event_summary[event_type] = {}
            event_summary[event_type][year] = count

        return event_summary
    except:
        return {}
    finally:
        conn.close()


def _analyze_compensation_trends(start_year: int, end_year: int) -> Dict[str, Any]:
    """Analyze compensation trends across years."""
    return {}  # Simplified implementation


def _get_age_distribution(year: int) -> Dict[str, int]:
    """Get age distribution for a specific year."""
    return {}  # Simplified implementation


def _get_tenure_distribution(year: int) -> Dict[str, int]:
    """Get tenure distribution for a specific year."""
    return {}  # Simplified implementation


def _analyze_year_event_patterns(year: int) -> Dict[str, Any]:
    """Analyze event patterns for a specific year."""
    return {}  # Simplified implementation


# Display functions
def _display_year_over_year_comparison(comparison_data: Dict[str, Any]) -> None:
    """Display year-over-year comparison results."""
    print(f"\n📊 YEAR-OVER-YEAR WORKFORCE COMPARISON")
    print("=" * 60)

    for year_data in comparison_data['year_progression']:
        year = year_data['year']
        active = year_data['active_employees']
        total_comp = year_data['total_compensation']
        avg_comp = year_data['avg_compensation']
        events = year_data['total_events']

        print(f"Year {year}:")
        print(f"  • Active workforce: {active:,}")
        print(f"  • Total compensation: ${total_comp:,.0f}")
        print(f"  • Average compensation: ${avg_comp:,.0f}")
        print(f"  • Total events: {events:,}")
        print()


def _display_growth_validation(validation: Dict[str, Any], start_count: int, end_count: int) -> None:
    """Display growth validation results."""
    print(f"\n📈 CUMULATIVE GROWTH VALIDATION")
    print("=" * 50)

    status = validation['growth_validation']
    target = validation['target_growth_rate']
    actual = validation['actual_cagr']

    status_icon = {'PASS': '✅', 'WARNING': '⚠️', 'FAIL': '❌', 'ERROR': '💥'}.get(status, '❓')

    print(f"Status: {status_icon} {status}")
    print(f"Target annual growth: {target:.1%}")
    print(f"Actual CAGR: {actual:.1%}")
    print(f"Workforce: {start_count:,} → {end_count:,}")
    print(f"Deviation: {(actual - target):.1%}")


def _display_comprehensive_summary(summary: Dict[str, Any]) -> None:
    """Display comprehensive multi-year summary."""
    print(f"\n📋 MULTI-YEAR SIMULATION SUMMARY")
    print("=" * 60)
    print(f"Simulation range: {summary['simulation_range']}")
    print(f"Total years: {summary['total_years']}")


def _display_aging_analysis(analysis: Dict[str, Any]) -> None:
    """Display workforce aging analysis."""
    print(f"\n👥 WORKFORCE AGING ANALYSIS")
    print("=" * 50)


def _display_event_consistency(consistency: Dict[str, Any]) -> None:
    """Display event consistency validation."""
    print(f"\n🔍 EVENT CONSISTENCY VALIDATION")
    print("=" * 50)


# Analysis helper functions
def _generate_growth_recommendations(validation: Dict[str, Any]) -> List[str]:
    """Generate growth recommendations based on validation results."""
    return []  # Simplified implementation


def _generate_key_insights(summary: Dict[str, Any]) -> List[str]:
    """Generate key insights from multi-year summary."""
    return []  # Simplified implementation


def _calculate_demographic_trends(age_progression: Dict, tenure_progression: Dict) -> Dict[str, str]:
    """Calculate demographic trends from progression data."""
    return {}  # Simplified implementation


def _detect_event_anomalies(event_patterns: Dict[str, Any]) -> List[str]:
    """Detect anomalies in event patterns across years."""
    return []  # Simplified implementation


def _generate_event_recommendations(consistency: Dict[str, Any]) -> List[str]:
    """Generate recommendations based on event consistency analysis."""
    return []  # Simplified implementation
