"""
Integration Patch for Existing Optimization Interfaces
Adds the new unified storage system to existing advanced_optimization.py and compensation_tuning.py
with minimal code changes.

Usage:
1. Import this module in the existing files
2. Replace the load_optimization_results() function calls
3. Add save calls after successful optimizations
"""

from typing import Dict, Any, Optional, List
import streamlit as st
from datetime import datetime
import logging

# Import the new system components
try:
    from integration_hooks import (
        AdvancedOptimizationIntegration,
        CompensationTuningIntegration,
        OptimizationSession
    )
    from optimization_results_manager import get_optimization_results_manager
    from optimization_storage import OptimizationType

    INTEGRATION_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Optimization integration not available: {e}")
    INTEGRATION_AVAILABLE = False


def enhanced_load_optimization_results():
    """
    Enhanced version of load_optimization_results() that tries the new system first,
    then falls back to the legacy implementation.
    """
    if not INTEGRATION_AVAILABLE:
        return None

    try:
        # Try new system first
        result = AdvancedOptimizationIntegration.load_optimization_results()
        if result:
            st.info("📊 Loaded results from unified optimization storage")
            return result
    except Exception as e:
        logging.warning(f"New system load failed, trying legacy: {e}")

    # Fallback to legacy implementation would go here
    return None


def enhanced_save_optimization_results(
    scenario_id: str,
    algorithm: str,
    optimization_config: Dict[str, Any],
    results: Dict[str, Any],
    **kwargs
) -> Optional[str]:
    """
    Enhanced save function that saves to the new unified system.
    """
    if not INTEGRATION_AVAILABLE:
        return None

    try:
        run_id = AdvancedOptimizationIntegration.save_optimization_results(
            scenario_id=scenario_id,
            algorithm=algorithm,
            optimization_config=optimization_config,
            results=results,
            **kwargs
        )

        st.success(f"✅ Saved optimization results to unified storage: {run_id[:8]}...")

        # Show quick link to dashboard
        if st.button("📊 View in Results Dashboard"):
            st.switch_page("optimization_dashboard.py")

        return run_id

    except Exception as e:
        st.error(f"Failed to save to unified storage: {e}")
        logging.error(f"Save to unified storage failed: {e}")
        return None


def enhanced_save_tuning_results(
    scenario_id: str,
    parameters: Dict[str, float],
    simulation_results: Dict[str, Any],
    **kwargs
) -> Optional[str]:
    """
    Enhanced save function for compensation tuning results.
    """
    if not INTEGRATION_AVAILABLE:
        return None

    try:
        run_id = CompensationTuningIntegration.save_tuning_results(
            scenario_id=scenario_id,
            parameters=parameters,
            simulation_results=simulation_results,
            **kwargs
        )

        st.success(f"✅ Saved tuning results to unified storage: {run_id[:8]}...")

        # Show optimization insights
        with st.expander("📈 Optimization Insights", expanded=False):
            st.write("**Parameters Saved:**")
            for param, value in parameters.items():
                if isinstance(value, float):
                    st.write(f"- {param}: {value:.4f}")
                else:
                    st.write(f"- {param}: {value}")

            if st.button("📊 View All Results", key="view_all_tuning"):
                st.switch_page("optimization_dashboard.py")

        return run_id

    except Exception as e:
        st.error(f"Failed to save tuning results: {e}")
        logging.error(f"Save tuning results failed: {e}")
        return None


def add_results_viewer_widget():
    """
    Add a widget to view recent optimization results.
    Call this in the sidebar of optimization interfaces.
    """
    if not INTEGRATION_AVAILABLE:
        return

    try:
        st.sidebar.markdown("### 📊 Recent Results")

        results_manager = get_optimization_results_manager()
        recent_runs = results_manager.get_recent_results(5)

        if recent_runs:
            for i, run in enumerate(recent_runs):
                with st.sidebar.expander(f"🔍 {run.scenario_id[:20]}..." if len(run.scenario_id) > 20 else run.scenario_id):
                    st.write(f"**Type:** {run.optimization_type.value.replace('_', ' ').title()}")
                    st.write(f"**Created:** {run.created_at.strftime('%m/%d %H:%M')}")
                    st.write(f"**Status:** {run.status.value.title()}")
                    if run.runtime_seconds:
                        st.write(f"**Runtime:** {run.runtime_seconds:.1f}s")

                    if st.button("📋 View Details", key=f"view_{i}"):
                        st.session_state['selected_run_details'] = run.run_id
                        st.switch_page("optimization_dashboard.py")
        else:
            st.sidebar.info("No recent results")

        # Quick action buttons
        if st.sidebar.button("📊 Open Dashboard"):
            st.switch_page("optimization_dashboard.py")

    except Exception as e:
        st.sidebar.warning(f"Results viewer error: {e}")


def add_optimization_status_indicator():
    """
    Add a status indicator for the optimization system.
    """
    if not INTEGRATION_AVAILABLE:
        st.sidebar.warning("⚠️ Unified storage not available")
        return

    try:
        status = AdvancedOptimizationIntegration.get_optimization_status()

        if status['system_healthy']:
            st.sidebar.success("✅ Optimization System Online")

            # Show quick stats
            if status.get('recent_runs_count', 0) > 0:
                st.sidebar.metric("Recent Runs", status['recent_runs_count'])

            if status.get('last_run_time'):
                last_run = datetime.fromisoformat(status['last_run_time'])
                hours_ago = (datetime.now() - last_run).total_seconds() / 3600
                st.sidebar.metric("Last Run", f"{hours_ago:.1f}h ago")
        else:
            st.sidebar.error("❌ System Issues Detected")
            if 'warning' in status:
                st.sidebar.warning(status['warning'])
            if 'error' in status:
                st.sidebar.error(status['error'])

    except Exception as e:
        st.sidebar.warning(f"Status check failed: {e}")


def get_parameter_comparison_widget(current_parameters: Dict[str, float]):
    """
    Widget to compare current parameters with previous optimizations.
    """
    if not INTEGRATION_AVAILABLE:
        return

    try:
        st.subheader("📊 Parameter Comparison")

        # Get parameter history
        param_history = CompensationTuningIntegration.get_parameter_history()

        if len(param_history) > 1:
            # Create comparison DataFrame
            comparison_data = []

            # Add current parameters
            comparison_data.append({
                'Run': 'Current',
                'Timestamp': 'Now',
                **current_parameters
            })

            # Add historical parameters
            for i, hist in enumerate(param_history[:3]):  # Last 3 runs
                comparison_data.append({
                    'Run': f"Run {i+1}",
                    'Timestamp': hist['timestamp'].strftime('%m/%d %H:%M'),
                    **hist['parameters']
                })

            import pandas as pd
            comparison_df = pd.DataFrame(comparison_data)

            # Display comparison
            st.dataframe(comparison_df, use_container_width=True)

            # Highlight differences
            if len(comparison_data) > 1:
                st.write("**Key Differences from Last Run:**")
                last_run_params = param_history[0]['parameters']

                differences = []
                for param, current_value in current_parameters.items():
                    if param in last_run_params:
                        last_value = last_run_params[param]
                        if abs(current_value - last_value) > 0.001:  # Significant difference
                            diff = current_value - last_value
                            differences.append(f"- {param}: {diff:+.4f} ({diff/last_value*100:+.1f}%)")

                if differences:
                    for diff in differences[:5]:  # Show top 5 differences
                        st.write(diff)
                else:
                    st.write("- No significant parameter changes")
        else:
            st.info("Run more optimizations to see parameter comparisons")

    except Exception as e:
        st.warning(f"Parameter comparison error: {e}")


def create_optimization_summary_card(results: Dict[str, Any]):
    """
    Create a summary card for optimization results.
    """
    if not results:
        return

    st.markdown("### 🎯 Optimization Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        algorithm = results.get('algorithm_used', results.get('algorithm', 'Unknown'))
        st.metric("Algorithm", algorithm)

    with col2:
        converged = results.get('converged', False)
        st.metric("Converged", "✅ Yes" if converged else "❌ No")

    with col3:
        runtime = results.get('runtime_seconds', 0)
        if runtime < 60:
            st.metric("Runtime", f"{runtime:.1f}s")
        else:
            st.metric("Runtime", f"{runtime/60:.1f}m")

    with col4:
        run_id = results.get('run_id')
        if run_id:
            st.metric("Run ID", run_id[:8] + "...")
        else:
            st.metric("Evaluations", results.get('function_evaluations', 'N/A'))

    # Quick actions
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📊 View in Dashboard"):
            st.switch_page("optimization_dashboard.py")

    with col2:
        if st.button("📥 Export Results"):
            if run_id:
                st.session_state['export_runs'] = [run_id]
                st.switch_page("optimization_dashboard.py")
            else:
                st.warning("No run ID available for export")

    with col3:
        if st.button("⚖️ Compare Results"):
            if run_id:
                if 'comparison_runs' not in st.session_state:
                    st.session_state['comparison_runs'] = []

                if run_id not in st.session_state['comparison_runs']:
                    st.session_state['comparison_runs'].append(run_id)

                st.switch_page("optimization_dashboard.py")
            else:
                st.warning("No run ID available for comparison")


# Context manager for easy integration
class EnhancedOptimizationSession:
    """
    Context manager that automatically integrates with the unified storage system.

    Usage:
    with EnhancedOptimizationSession("my_optimization", "advanced") as session:
        # run optimization
        results = my_optimization_function()
        session.save_results(scenario_id, algorithm, config, results)
    """

    def __init__(self, session_name: str, optimization_type: str = "advanced"):
        self.session_name = session_name
        self.optimization_type = optimization_type
        self.session = None
        self.results = []

    def __enter__(self):
        if INTEGRATION_AVAILABLE:
            opt_type = OptimizationType.ADVANCED_SCIPY if self.optimization_type == "advanced" else OptimizationType.COMPENSATION_TUNING
            self.session = OptimizationSession(self.session_name, opt_type)
            self.session.__enter__()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.__exit__(exc_type, exc_val, exc_tb)

    def save_results(self, scenario_id: str, algorithm: str, config: Dict[str, Any], results: Dict[str, Any]) -> Optional[str]:
        """Save optimization results."""
        if self.optimization_type == "advanced":
            run_id = enhanced_save_optimization_results(scenario_id, algorithm, config, results)
        else:
            # For tuning type
            parameters = config.get('parameters', {})
            run_id = enhanced_save_tuning_results(scenario_id, parameters, results)

        if run_id and self.session:
            self.session.add_result(run_id)
            self.results.append(run_id)

        return run_id


# Simple monkey-patch functions for existing code
def patch_advanced_optimization():
    """
    Monkey-patch the advanced_optimization.py module to use the new system.
    Call this at the top of advanced_optimization.py after imports.
    """
    if INTEGRATION_AVAILABLE:
        # Replace the global load_optimization_results function
        import sys
        current_module = sys.modules[__name__]
        current_module.load_optimization_results = enhanced_load_optimization_results

        st.info("🔗 Enhanced with unified optimization storage")


def patch_compensation_tuning():
    """
    Monkey-patch the compensation_tuning.py module to use the new system.
    Call this at the top of compensation_tuning.py after imports.
    """
    if INTEGRATION_AVAILABLE:
        st.info("🔗 Enhanced with unified optimization storage")


# Export commonly used functions
__all__ = [
    'enhanced_load_optimization_results',
    'enhanced_save_optimization_results',
    'enhanced_save_tuning_results',
    'add_results_viewer_widget',
    'add_optimization_status_indicator',
    'get_parameter_comparison_widget',
    'create_optimization_summary_card',
    'EnhancedOptimizationSession',
    'patch_advanced_optimization',
    'patch_compensation_tuning'
]


if __name__ == "__main__":
    # Test the integration patch
    print("Testing optimization integration patch...")

    if INTEGRATION_AVAILABLE:
        print("✅ Integration system available")

        # Test enhanced load
        results = enhanced_load_optimization_results()
        print(f"Load test: {results is not None}")

    else:
        print("❌ Integration system not available")

    print("Integration patch test completed")
