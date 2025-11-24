# filename: streamlit_dashboard/main.py
"""
Fidelity PlanAlign Engine - Main Dashboard Entry Point
Multi-page Streamlit application for workforce simulation and compensation optimization.
"""

import sys
from pathlib import Path

import streamlit as st

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

# Page configuration
st.set_page_config(
    page_title="Fidelity PlanAlign Engine",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/fidelity/planalign_engine",
        "Report a bug": "https://github.com/fidelity/planalign_engine/issues",
        "About": "Fidelity PlanAlign Engine - Enterprise Workforce Simulation Platform",
    },
)

# Custom CSS for professional styling
st.markdown(
    """
<style>
    .main-header {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 3rem 2rem;
        border-radius: 1rem;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .main-header h1 {
        margin: 0;
        font-size: 3rem;
        font-weight: 700;
    }

    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.2rem;
        opacity: 0.9;
    }

    .feature-card {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #007bff;
        margin-bottom: 1rem;
        transition: transform 0.2s;
    }

    .feature-card:hover {
        transform: translateX(5px);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }

    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        text-align: center;
    }

    .metric-value {
        font-size: 2rem;
        font-weight: bold;
        color: #007bff;
    }

    .metric-label {
        color: #6c757d;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }

    .navigation-hint {
        background: #e3f2fd;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
        border-left: 4px solid #2196f3;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Header
st.markdown(
    """
<div class="main-header">
    <h1>🚀 Fidelity PlanAlign Engine</h1>
    <p>Enterprise Workforce Simulation & Compensation Optimization Platform</p>
</div>
""",
    unsafe_allow_html=True,
)

# Welcome message
st.markdown(
    """
## Welcome to Fidelity PlanAlign Engine

Your comprehensive platform for workforce planning, simulation, and compensation optimization.
"""
)

# Navigation hint
st.markdown(
    """
<div class="navigation-hint">
    <strong>👈 Use the sidebar to navigate between different modules:</strong>
    <ul>
        <li><strong>Compensation Tuning</strong> - Adjust parameters and run simulations</li>
        <li><strong>Optimization Progress</strong> - Monitor real-time optimization runs</li>
        <li><strong>Deferral Escalation Analytics</strong> - Epic E035 analytics and executive reporting</li>
        <li><strong>Risk Assessment</strong> - Analyze parameter risks (coming soon)</li>
        <li><strong>Analytics Dashboard</strong> - View simulation results (coming soon)</li>
    </ul>
</div>
""",
    unsafe_allow_html=True,
)

# Feature overview
st.markdown("## 🎯 Key Features")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
    <div class="feature-card">
        <h3>💰 Dynamic Compensation Tuning</h3>
        <p>Adjust compensation parameters in real-time and see immediate impact on workforce costs and growth.</p>
        <ul>
            <li>Merit rate adjustments by job level</li>
            <li>COLA rate modifications</li>
            <li>Promotion probability tuning</li>
            <li>New hire compensation planning</li>
        </ul>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <div class="feature-card">
        <h3>📊 Event-Sourced Architecture</h3>
        <p>Complete audit trail of all workforce events with immutable history.</p>
        <ul>
            <li>Hire, termination, and promotion events</li>
            <li>Compensation change tracking</li>
            <li>Full workforce reconstruction capability</li>
            <li>Enterprise-grade transparency</li>
        </ul>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
    <div class="feature-card">
        <h3>🔄 Advanced Optimization Engine</h3>
        <p>Automated parameter optimization to meet specific budget and growth targets.</p>
        <ul>
            <li>SciPy-based optimization algorithms</li>
            <li>Multi-constraint handling</li>
            <li>Real-time progress monitoring</li>
            <li>Convergence tracking</li>
        </ul>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <div class="feature-card">
        <h3>🎲 Multi-Year Simulations</h3>
        <p>Run comprehensive workforce simulations across multiple years with dependencies.</p>
        <ul>
            <li>Year-over-year growth modeling</li>
            <li>Cumulative impact analysis</li>
            <li>Scenario comparison</li>
            <li>Risk assessment integration</li>
        </ul>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <div class="feature-card">
        <h3>📈 Deferral Rate Escalation Analytics</h3>
        <p>Epic E035: Comprehensive analytics for automatic annual deferral rate increases.</p>
        <ul>
            <li>January 1st effective date tracking</li>
            <li>1% increment compliance monitoring</li>
            <li>10% maximum rate cap enforcement</li>
            <li>Multi-year progression analysis</li>
        </ul>
    </div>
    """,
        unsafe_allow_html=True,
    )

# Quick stats (placeholder - would connect to real data)
st.markdown("## 📈 System Status")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        """
    <div class="metric-card">
        <div class="metric-value">2025-2029</div>
        <div class="metric-label">Simulation Years</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
    <div class="metric-card">
        <div class="metric-value">5</div>
        <div class="metric-label">Job Levels</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        """
    <div class="metric-card">
        <div class="metric-value">126</div>
        <div class="metric-label">Tunable Parameters</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col4:
    st.markdown(
        """
    <div class="metric-card">
        <div class="metric-value">Ready</div>
        <div class="metric-label">System Status</div>
    </div>
    """,
        unsafe_allow_html=True,
    )

# Quick start guide
st.markdown("## 🚀 Quick Start")

with st.expander("Getting Started with Fidelity PlanAlign Engine", expanded=True):
    st.markdown(
        """
    ### 1. Compensation Tuning
    Navigate to the **Compensation Tuning** page to:
    - Adjust merit rates, COLA rates, and promotion parameters
    - Run simulations with different random seeds
    - View year-by-year workforce composition
    - Export results for further analysis

    ### 2. Optimization Engine (S047)
    Use the advanced optimization features to:
    - Set target budget and growth constraints
    - Let the system find optimal parameter combinations
    - Monitor convergence in real-time
    - Review constraint satisfaction

    ### 3. Deferral Escalation Analytics (Epic E035)
    Navigate to the **Deferral Escalation Analytics** page to:
    - Monitor automatic deferral rate escalation impact
    - View multi-year progression charts
    - Analyze demographic participation patterns
    - Review compliance with user requirements
    - Generate executive summary reports

    ### 4. View Results
    After running simulations:
    - Analyze workforce growth patterns
    - Review compensation distributions
    - Assess budget impact
    - Export data for reporting

    ### 5. Risk Assessment
    Evaluate parameter changes for:
    - Budget overrun risks
    - Retention impact
    - Compliance concerns
    - Market competitiveness
    """
    )

# Technical information
with st.expander("Technical Architecture"):
    st.markdown(
        """
    ### Technology Stack
    - **Storage**: DuckDB 1.0.0 - Column-store OLAP engine
    - **Transformation**: dbt-core 1.8.8 - SQL-based transformations
    - **Orchestration**: Dagster 1.8.12 - Asset-based pipelines
    - **Optimization**: SciPy 1.11.0 - Scientific computing
    - **UI**: Streamlit 1.39.0 - Interactive dashboards

    ### Data Flow
    1. **Parameters** → comp_levers.csv
    2. **Events** → Event models generate workforce changes
    3. **Snapshots** → Point-in-time workforce states
    4. **Analysis** → Dashboards and reports
    """
    )

# Footer
st.markdown("---")
st.markdown(
    """
<div style='text-align: center; color: #666; padding: 2rem;'>
    <h4>Fidelity PlanAlign Engine v3.0</h4>
    <p>Enterprise Workforce Simulation Platform</p>
    <p><small>© 2024 Fidelity Investments. All rights reserved.</small></p>
</div>
""",
    unsafe_allow_html=True,
)
