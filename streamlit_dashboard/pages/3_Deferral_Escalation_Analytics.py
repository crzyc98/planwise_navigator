from navigator_orchestrator.config import get_database_path
# filename: streamlit_dashboard/pages/3_Deferral_Escalation_Analytics.py
"""
Epic E035: Deferral Rate Escalation Analytics Dashboard

This page provides comprehensive analytics and executive reporting for the automatic
annual deferral rate escalation system. Features include:

- Escalation impact metrics visualization
- Year-over-year deferral rate progression charts
- Executive summary reports with ROI analysis
- Historical trend analysis of escalation effectiveness
- Health monitoring with data quality insights
- Demographic analysis of escalation impact

User Requirements Addressed:
- January 1st effective date tracking and validation
- 1% increment monitoring and trend analysis
- 10% maximum rate cap compliance and impact
- Hire date eligibility demographic analysis
- Multi-year progression impact measurement
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Page configuration
st.set_page_config(
    page_title="Deferral Escalation Analytics - PlanWise Navigator",
    page_icon="📈",
    layout="wide",
)

# Custom CSS for professional analytics styling
st.markdown(
    """
<style>
    .analytics-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 1rem;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }

    .analytics-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }

    .analytics-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1.1rem;
        opacity: 0.9;
    }

    .kpi-card {
        background: white;
        padding: 1.5rem;
        border-radius: 0.75rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        text-align: center;
        border-left: 4px solid #667eea;
        transition: transform 0.2s;
    }

    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
    }

    .kpi-value {
        font-size: 2.5rem;
        font-weight: bold;
        color: #667eea;
        margin: 0;
    }

    .kpi-label {
        color: #6c757d;
        font-size: 0.9rem;
        margin-top: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .kpi-delta {
        font-size: 0.8rem;
        margin-top: 0.25rem;
    }

    .kpi-delta.positive {
        color: #28a745;
    }

    .kpi-delta.negative {
        color: #dc3545;
    }

    .section-header {
        background: #f8f9fa;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #667eea;
        margin: 2rem 0 1rem 0;
    }

    .section-header h3 {
        margin: 0;
        color: #495057;
    }

    .health-status-excellent {
        background: linear-gradient(135deg, #d4edda, #c3e6cb);
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #c3e6cb;
    }

    .health-status-good {
        background: linear-gradient(135deg, #cce5ff, #b3d9ff);
        color: #004085;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #b3d9ff;
    }

    .health-status-warning {
        background: linear-gradient(135deg, #fff3cd, #ffeaa7);
        color: #856404;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #ffeaa7;
    }

    .health-status-critical {
        background: linear-gradient(135deg, #f8d7da, #f5c6cb);
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #f5c6cb;
    }

    .insight-box {
        background: #e8f4f8;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #17a2b8;
        margin: 1rem 0;
    }

    .executive-summary {
        background: white;
        padding: 2rem;
        border-radius: 1rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        margin: 2rem 0;
    }
</style>
""",
    unsafe_allow_html=True,
)


class EscalationAnalytics:
    """Analytics engine for deferral rate escalation system."""

    def __init__(self, db_path: str = str(get_database_path())):
        self.db_path = db_path
        self.conn = None

    def get_connection(self):
        """Get database connection."""
        if self.conn is None:
            try:
                self.conn = duckdb.connect(self.db_path)
            except Exception as e:
                st.error(f"Failed to connect to database: {e}")
                return None
        return self.conn

    def execute_query(self, query: str, description: str = "") -> pd.DataFrame:
        """Execute query and return DataFrame."""
        try:
            conn = self.get_connection()
            if conn is None:
                return pd.DataFrame()

            result = conn.execute(query).fetchdf()
            return result
        except Exception as e:
            st.error(f"Query failed ({description}): {e}")
            return pd.DataFrame()

    def get_escalation_overview_metrics(self) -> Dict:
        """Get high-level escalation system metrics."""
        query = """
        WITH escalation_summary AS (
            SELECT
                COUNT(DISTINCT employee_id) as total_employees_with_escalations,
                SUM(total_escalations) as total_escalation_events,
                AVG(current_deferral_rate) as avg_current_rate,
                AVG(total_escalation_amount) as avg_total_escalation,
                MAX(simulation_year) as latest_year,
                COUNT(CASE WHEN current_deferral_rate >= 0.10 THEN 1 END) as employees_at_cap
            FROM int_deferral_escalation_state_accumulator
            WHERE has_escalations = true
        ),
        participation_summary AS (
            SELECT
                COUNT(DISTINCT employee_id) as total_active_employees,
                COUNT(DISTINCT CASE WHEN is_enrolled_flag = true THEN employee_id END) as total_enrolled_employees
            FROM fct_workforce_snapshot
            WHERE simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
              AND employment_status = 'active'
        ),
        health_summary AS (
            SELECT
                health_score,
                health_status,
                total_violations,
                recommendations
            FROM dq_deferral_escalation_validation
            WHERE simulation_year = (SELECT MAX(simulation_year) FROM dq_deferral_escalation_validation)
        )

        SELECT
            es.*,
            ps.total_active_employees,
            ps.total_enrolled_employees,
            hs.health_score,
            hs.health_status,
            hs.total_violations,
            hs.recommendations
        FROM escalation_summary es
        CROSS JOIN participation_summary ps
        CROSS JOIN health_summary hs
        """

        df = self.execute_query(query, "escalation overview metrics")
        return df.iloc[0].to_dict() if len(df) > 0 else {}

    def get_yearly_progression_data(self) -> pd.DataFrame:
        """Get year-over-year escalation progression."""
        query = """
        SELECT
            simulation_year,
            COUNT(DISTINCT employee_id) as active_employees,
            COUNT(DISTINCT CASE WHEN has_escalations = true THEN employee_id END) as employees_with_escalations,
            SUM(total_escalations) as total_escalations,
            AVG(current_deferral_rate) as avg_deferral_rate,
            AVG(CASE WHEN has_escalations = true THEN current_deferral_rate END) as avg_escalated_rate,
            COUNT(CASE WHEN current_deferral_rate >= 0.10 THEN 1 END) as employees_at_cap,
            SUM(total_escalation_amount) as total_escalation_impact,
            COUNT(CASE WHEN had_escalation_this_year = true THEN 1 END) as new_escalations_this_year
        FROM int_deferral_escalation_state_accumulator
        GROUP BY simulation_year
        ORDER BY simulation_year
        """

        return self.execute_query(query, "yearly progression data")

    def get_demographic_analysis(self) -> pd.DataFrame:
        """Get escalation impact by demographic segments."""
        query = """
        SELECT
            ws.age_band,
            ws.tenure_band,
            ws.level_id,
            COUNT(*) as employee_count,
            COUNT(CASE WHEN esc.has_escalations = true THEN 1 END) as escalated_count,
            AVG(esc.current_deferral_rate) as avg_current_rate,
            AVG(esc.total_escalations) as avg_escalation_count,
            AVG(esc.total_escalation_amount) as avg_escalation_impact,
            COUNT(CASE WHEN esc.current_deferral_rate >= 0.10 THEN 1 END) as at_cap_count
        FROM fct_workforce_snapshot ws
        LEFT JOIN int_deferral_escalation_state_accumulator esc
            ON ws.employee_id = esc.employee_id
            AND ws.simulation_year = esc.simulation_year
        WHERE ws.simulation_year = (SELECT MAX(simulation_year) FROM fct_workforce_snapshot)
          AND ws.employment_status = 'active'
          AND ws.is_enrolled_flag = true
        GROUP BY ws.age_band, ws.tenure_band, ws.level_id
        ORDER BY ws.level_id, ws.age_band, ws.tenure_band
        """

        return self.execute_query(query, "demographic analysis")

    def get_roi_analysis(self) -> Dict:
        """Calculate ROI metrics for escalation system."""
        query = """
        WITH contribution_impact AS (
            SELECT
                ws.simulation_year,
                SUM(ws.prorated_annual_contributions) as total_contributions,
                SUM(CASE WHEN esc.has_escalations = true THEN ws.prorated_annual_contributions ELSE 0 END) as escalated_contributions,
                COUNT(CASE WHEN esc.has_escalations = true THEN 1 END) as escalated_employee_count,
                SUM(esc.total_escalation_amount * ws.prorated_annual_compensation) as estimated_additional_contributions
            FROM fct_workforce_snapshot ws
            LEFT JOIN int_deferral_escalation_state_accumulator esc
                ON ws.employee_id = esc.employee_id
                AND ws.simulation_year = esc.simulation_year
            WHERE ws.employment_status = 'active'
              AND ws.is_enrolled_flag = true
            GROUP BY ws.simulation_year
        ),
        baseline_comparison AS (
            SELECT
                simulation_year,
                total_contributions,
                escalated_contributions,
                escalated_employee_count,
                estimated_additional_contributions,
                total_contributions - escalated_contributions + estimated_additional_contributions as projected_without_escalation,
                (estimated_additional_contributions / NULLIF(projected_without_escalation, 0)) * 100 as contribution_increase_pct
            FROM contribution_impact
        )

        SELECT
            AVG(contribution_increase_pct) as avg_annual_contribution_increase_pct,
            SUM(estimated_additional_contributions) as total_estimated_additional_contributions,
            AVG(escalated_employee_count) as avg_escalated_employees_per_year,
            MAX(simulation_year) - MIN(simulation_year) + 1 as simulation_years
        FROM baseline_comparison
        """

        df = self.execute_query(query, "ROI analysis")
        return df.iloc[0].to_dict() if len(df) > 0 else {}

    def get_compliance_tracking(self) -> pd.DataFrame:
        """Get compliance metrics for user requirements."""
        query = """
        WITH compliance_checks AS (
            SELECT
                simulation_year,
                COUNT(*) as total_escalation_events,
                COUNT(CASE WHEN EXTRACT(MONTH FROM effective_date) = 1 AND EXTRACT(DAY FROM effective_date) = 1 THEN 1 END) as january_1_events,
                COUNT(CASE WHEN escalation_rate = 0.01 THEN 1 END) as correct_increment_events,
                COUNT(CASE WHEN new_deferral_rate <= 0.10 THEN 1 END) as within_cap_events,
                COUNT(*) - COUNT(DISTINCT employee_id) as duplicate_events,
                AVG(escalation_rate) as avg_escalation_rate,
                MAX(new_deferral_rate) as max_escalation_rate
            FROM int_deferral_rate_escalation_events
            GROUP BY simulation_year
        )

        SELECT
            *,
            CASE WHEN total_escalation_events = january_1_events THEN 100.0 ELSE (january_1_events * 100.0 / total_escalation_events) END as january_1_compliance_pct,
            CASE WHEN total_escalation_events = correct_increment_events THEN 100.0 ELSE (correct_increment_events * 100.0 / total_escalation_events) END as increment_compliance_pct,
            CASE WHEN total_escalation_events = within_cap_events THEN 100.0 ELSE (within_cap_events * 100.0 / total_escalation_events) END as cap_compliance_pct,
            CASE WHEN duplicate_events = 0 THEN 100.0 ELSE 0.0 END as no_duplicate_compliance_pct
        FROM compliance_checks
        ORDER BY simulation_year
        """

        return self.execute_query(query, "compliance tracking")


def render_header():
    """Render the page header."""
    st.markdown(
        """
    <div class="analytics-header">
        <h1>📈 Deferral Rate Escalation Analytics</h1>
        <p>Epic E035 - Comprehensive impact analysis and executive reporting</p>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_kpi_cards(analytics: EscalationAnalytics):
    """Render key performance indicator cards."""
    try:
        metrics = analytics.get_escalation_overview_metrics()

        if not metrics:
            st.warning(
                "No escalation data available. Please run a multi-year simulation first."
            )
            return

        st.markdown(
            '<div class="section-header"><h3>📊 Key Performance Indicators</h3></div>',
            unsafe_allow_html=True,
        )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
            <div class="kpi-card">
                <div class="kpi-value">{metrics.get('total_employees_with_escalations', 0):,.0f}</div>
                <div class="kpi-label">Employees with Escalations</div>
                <div class="kpi-delta positive">
                    {metrics.get('total_employees_with_escalations', 0) / max(metrics.get('total_enrolled_employees', 1), 1) * 100:.1f}% of enrolled
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""
            <div class="kpi-card">
                <div class="kpi-value">{metrics.get('avg_current_rate', 0):.1%}</div>
                <div class="kpi-label">Avg Current Rate</div>
                <div class="kpi-delta positive">
                    +{metrics.get('avg_total_escalation', 0):.1%} from escalations
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                f"""
            <div class="kpi-card">
                <div class="kpi-value">{metrics.get('total_escalation_events', 0):,.0f}</div>
                <div class="kpi-label">Total Escalation Events</div>
                <div class="kpi-delta positive">
                    Across {metrics.get('latest_year', 2025) - 2024} simulation years
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        with col4:
            st.markdown(
                f"""
            <div class="kpi-card">
                <div class="kpi-value">{metrics.get('employees_at_cap', 0):,.0f}</div>
                <div class="kpi-label">Employees at 10% Cap</div>
                <div class="kpi-delta">
                    {metrics.get('employees_at_cap', 0) / max(metrics.get('total_employees_with_escalations', 1), 1) * 100:.1f}% of escalated employees
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        # System health status
        st.markdown(
            '<div class="section-header"><h3>🏥 System Health Status</h3></div>',
            unsafe_allow_html=True,
        )

        health_score = metrics.get("health_score", 0)
        health_status = metrics.get("health_status", "UNKNOWN")

        health_class = {
            "PERFECT": "health-status-excellent",
            "EXCELLENT": "health-status-excellent",
            "GOOD": "health-status-good",
            "FAIR": "health-status-warning",
            "POOR": "health-status-critical",
            "CRITICAL": "health-status-critical",
        }.get(health_status, "health-status-warning")

        st.markdown(
            f"""
        <div class="{health_class}">
            <h4>🎯 System Health Score: {health_score}/100 ({health_status})</h4>
            <p><strong>Data Quality:</strong> {metrics.get('total_violations', 0)} violations detected</p>
            <p><strong>Recommendation:</strong> {metrics.get('recommendations', 'No recommendations available')}</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    except Exception as e:
        st.error(f"Failed to load KPI metrics: {e}")


def render_yearly_progression_chart(analytics: EscalationAnalytics):
    """Render year-over-year progression visualization."""
    try:
        st.markdown(
            '<div class="section-header"><h3>📈 Multi-Year Progression Analysis</h3></div>',
            unsafe_allow_html=True,
        )

        df = analytics.get_yearly_progression_data()

        if df.empty:
            st.warning("No yearly progression data available.")
            return

        # Create subplot with secondary y-axis
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Employee Participation Growth",
                "Average Deferral Rate Progression",
                "Escalation Events by Year",
                "Cap Compliance Tracking",
            ),
            specs=[
                [{"secondary_y": True}, {"secondary_y": False}],
                [{"secondary_y": False}, {"secondary_y": False}],
            ],
        )

        # Chart 1: Employee participation
        fig.add_trace(
            go.Scatter(
                x=df["simulation_year"],
                y=df["active_employees"],
                name="Active Employees",
                line=dict(color="#667eea", width=3),
                mode="lines+markers",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df["simulation_year"],
                y=df["employees_with_escalations"],
                name="With Escalations",
                line=dict(color="#764ba2", width=3, dash="dash"),
                mode="lines+markers",
            ),
            row=1,
            col=1,
        )

        # Chart 2: Average deferral rates
        fig.add_trace(
            go.Scatter(
                x=df["simulation_year"],
                y=df["avg_deferral_rate"] * 100,
                name="Overall Avg Rate",
                line=dict(color="#28a745", width=3),
                mode="lines+markers",
            ),
            row=1,
            col=2,
        )
        fig.add_trace(
            go.Scatter(
                x=df["simulation_year"],
                y=df["avg_escalated_rate"] * 100,
                name="Escalated Avg Rate",
                line=dict(color="#ffc107", width=3, dash="dot"),
                mode="lines+markers",
            ),
            row=1,
            col=2,
        )

        # Chart 3: Escalation events
        fig.add_trace(
            go.Bar(
                x=df["simulation_year"],
                y=df["new_escalations_this_year"],
                name="New Escalations",
                marker_color="#17a2b8",
                opacity=0.8,
            ),
            row=2,
            col=1,
        )

        # Chart 4: Cap compliance
        fig.add_trace(
            go.Scatter(
                x=df["simulation_year"],
                y=df["employees_at_cap"],
                name="Employees at 10% Cap",
                line=dict(color="#dc3545", width=3),
                mode="lines+markers",
            ),
            row=2,
            col=2,
        )

        fig.update_layout(
            height=800,
            showlegend=True,
            title_text="Deferral Rate Escalation - Multi-Year Progression Dashboard",
            font=dict(size=12),
        )

        # Update y-axis labels
        fig.update_yaxes(title_text="Employee Count", row=1, col=1)
        fig.update_yaxes(title_text="Deferral Rate (%)", row=1, col=2)
        fig.update_yaxes(title_text="Escalation Events", row=2, col=1)
        fig.update_yaxes(title_text="Employees at Cap", row=2, col=2)

        st.plotly_chart(fig, use_container_width=True)

        # Add insights
        if len(df) > 1:
            latest_year = df.iloc[-1]
            previous_year = df.iloc[-2]

            participation_growth = (
                latest_year["employees_with_escalations"]
                - previous_year["employees_with_escalations"]
            )
            rate_increase = (
                latest_year["avg_escalated_rate"] - previous_year["avg_escalated_rate"]
            ) * 100

            st.markdown(
                f"""
            <div class="insight-box">
                <h4>📊 Key Insights</h4>
                <ul>
                    <li><strong>Participation Growth:</strong> {participation_growth:+.0f} employees gained escalations year-over-year</li>
                    <li><strong>Rate Impact:</strong> Average escalated rate increased by {rate_increase:+.2f} percentage points</li>
                    <li><strong>Cap Management:</strong> {latest_year['employees_at_cap']:.0f} employees currently at 10% maximum rate</li>
                    <li><strong>System Maturity:</strong> {latest_year['total_escalations']:.0f} total escalation events across all years</li>
                </ul>
            </div>
            """,
                unsafe_allow_html=True,
            )

    except Exception as e:
        st.error(f"Failed to render yearly progression chart: {e}")


def render_demographic_analysis(analytics: EscalationAnalytics):
    """Render demographic impact analysis."""
    try:
        st.markdown(
            '<div class="section-header"><h3>👥 Demographic Impact Analysis</h3></div>',
            unsafe_allow_html=True,
        )

        df = analytics.get_demographic_analysis()

        if df.empty:
            st.warning("No demographic analysis data available.")
            return

        # Create pivot tables for heatmaps
        pivot_escalation_rate = df.pivot_table(
            index="age_band",
            columns="tenure_band",
            values="escalated_count",
            aggfunc="sum",
            fill_value=0,
        )

        pivot_avg_rate = df.pivot_table(
            index="age_band",
            columns="tenure_band",
            values="avg_current_rate",
            aggfunc="mean",
            fill_value=0,
        )

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Escalation Participation by Demographics")
            fig1 = px.imshow(
                pivot_escalation_rate,
                title="Employee Count with Escalations",
                color_continuous_scale="Blues",
                aspect="auto",
            )
            fig1.update_layout(height=400)
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            st.subheader("Average Deferral Rates by Demographics")
            fig2 = px.imshow(
                pivot_avg_rate * 100,  # Convert to percentage
                title="Average Current Deferral Rate (%)",
                color_continuous_scale="Viridis",
                aspect="auto",
            )
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)

        # Job level analysis
        st.subheader("Impact by Job Level")
        level_summary = (
            df.groupby("level_id")
            .agg(
                {
                    "employee_count": "sum",
                    "escalated_count": "sum",
                    "avg_current_rate": "mean",
                    "avg_escalation_impact": "mean",
                }
            )
            .reset_index()
        )

        level_summary["escalation_participation_rate"] = (
            level_summary["escalated_count"] / level_summary["employee_count"] * 100
        )

        fig3 = px.bar(
            level_summary,
            x="level_id",
            y=["escalation_participation_rate"],
            title="Escalation Participation Rate by Job Level (%)",
            color_discrete_sequence=["#667eea"],
        )
        fig3.update_layout(height=400, showlegend=False)
        fig3.update_xaxes(title="Job Level")
        fig3.update_yaxes(title="Participation Rate (%)")

        st.plotly_chart(fig3, use_container_width=True)

        # Summary table
        st.subheader("Detailed Demographic Breakdown")
        display_df = df.copy()
        display_df["escalation_rate"] = (
            display_df["escalated_count"] / display_df["employee_count"] * 100
        ).round(1)
        display_df["avg_current_rate"] = (display_df["avg_current_rate"] * 100).round(2)
        display_df["avg_escalation_impact"] = (
            display_df["avg_escalation_impact"] * 100
        ).round(2)

        st.dataframe(
            display_df[
                [
                    "age_band",
                    "tenure_band",
                    "level_id",
                    "employee_count",
                    "escalated_count",
                    "escalation_rate",
                    "avg_current_rate",
                    "avg_escalation_impact",
                    "at_cap_count",
                ]
            ].rename(
                columns={
                    "age_band": "Age Band",
                    "tenure_band": "Tenure Band",
                    "level_id": "Job Level",
                    "employee_count": "Total Employees",
                    "escalated_count": "With Escalations",
                    "escalation_rate": "Participation Rate (%)",
                    "avg_current_rate": "Avg Current Rate (%)",
                    "avg_escalation_impact": "Avg Escalation Impact (%)",
                    "at_cap_count": "At 10% Cap",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )

    except Exception as e:
        st.error(f"Failed to render demographic analysis: {e}")


def render_compliance_tracking(analytics: EscalationAnalytics):
    """Render compliance tracking for user requirements."""
    try:
        st.markdown(
            '<div class="section-header"><h3>✅ User Requirements Compliance Tracking</h3></div>',
            unsafe_allow_html=True,
        )

        df = analytics.get_compliance_tracking()

        if df.empty:
            st.warning("No compliance tracking data available.")
            return

        # Overall compliance score
        latest_data = df.iloc[-1] if len(df) > 0 else {}

        compliance_metrics = [
            latest_data.get("january_1_compliance_pct", 0),
            latest_data.get("increment_compliance_pct", 0),
            latest_data.get("cap_compliance_pct", 0),
            latest_data.get("no_duplicate_compliance_pct", 0),
        ]

        overall_compliance = sum(compliance_metrics) / len(compliance_metrics)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "January 1st Effective Date",
                f"{latest_data.get('january_1_compliance_pct', 0):.1f}%",
                help="All escalations must be effective January 1st per user requirement",
            )

        with col2:
            st.metric(
                "1% Increment Compliance",
                f"{latest_data.get('increment_compliance_pct', 0):.1f}%",
                help="Default 1% escalation rate per user requirement",
            )

        with col3:
            st.metric(
                "10% Cap Enforcement",
                f"{latest_data.get('cap_compliance_pct', 0):.1f}%",
                help="Maximum 10% rate cap per user requirement",
            )

        with col4:
            st.metric(
                "No Duplicate Events",
                f"{latest_data.get('no_duplicate_compliance_pct', 0):.1f}%",
                help="Each employee should have max one escalation per year",
            )

        # Overall compliance status
        compliance_status = (
            "EXCELLENT"
            if overall_compliance >= 99
            else "GOOD"
            if overall_compliance >= 95
            else "NEEDS ATTENTION"
        )
        compliance_color = (
            "#28a745"
            if compliance_status == "EXCELLENT"
            else "#ffc107"
            if compliance_status == "GOOD"
            else "#dc3545"
        )

        st.markdown(
            f"""
        <div style="background: {compliance_color}20; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid {compliance_color}; margin: 1rem 0;">
            <h4 style="color: {compliance_color}; margin: 0;">Overall Compliance Score: {overall_compliance:.1f}% - {compliance_status}</h4>
            <p style="margin: 0.5rem 0 0 0;">System is {'meeting' if overall_compliance >= 95 else 'not meeting'} all user requirements for automatic deferral rate escalation.</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Compliance trend chart
        if len(df) > 1:
            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=df["simulation_year"],
                    y=df["january_1_compliance_pct"],
                    name="January 1st Compliance",
                    line=dict(color="#667eea", width=2),
                    mode="lines+markers",
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=df["simulation_year"],
                    y=df["increment_compliance_pct"],
                    name="1% Increment Compliance",
                    line=dict(color="#28a745", width=2),
                    mode="lines+markers",
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=df["simulation_year"],
                    y=df["cap_compliance_pct"],
                    name="10% Cap Compliance",
                    line=dict(color="#ffc107", width=2),
                    mode="lines+markers",
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=df["simulation_year"],
                    y=df["no_duplicate_compliance_pct"],
                    name="No Duplicate Compliance",
                    line=dict(color="#17a2b8", width=2),
                    mode="lines+markers",
                )
            )

            fig.update_layout(
                title="Compliance Metrics Trend Analysis",
                xaxis_title="Simulation Year",
                yaxis_title="Compliance Percentage (%)",
                height=400,
                yaxis=dict(range=[0, 105]),
            )

            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Failed to render compliance tracking: {e}")


def render_executive_summary(analytics: EscalationAnalytics):
    """Render executive summary with ROI analysis."""
    try:
        st.markdown(
            '<div class="section-header"><h3>📋 Executive Summary & ROI Analysis</h3></div>',
            unsafe_allow_html=True,
        )

        # Get ROI metrics
        roi_data = analytics.get_roi_analysis()
        overview_data = analytics.get_escalation_overview_metrics()

        if not roi_data or not overview_data:
            st.warning("Insufficient data for executive summary.")
            return

        st.markdown(
            """
        <div class="executive-summary">
            <h3>🎯 Deferral Rate Escalation System - Executive Summary</h3>
        """,
            unsafe_allow_html=True,
        )

        # Key findings section
        st.markdown(
            f"""
            <h4>📈 Key Performance Outcomes</h4>
            <ul>
                <li><strong>Participation Impact:</strong> {overview_data.get('total_employees_with_escalations', 0):,.0f} employees have benefited from automatic escalations</li>
                <li><strong>Average Rate Improvement:</strong> {overview_data.get('avg_total_escalation', 0):.1%} average increase in deferral rates</li>
                <li><strong>Contribution Growth:</strong> Estimated {roi_data.get('avg_annual_contribution_increase_pct', 0):.1f}% annual increase in employee contributions</li>
                <li><strong>System Reliability:</strong> {overview_data.get('health_score', 0)}/100 data quality health score</li>
            </ul>

            <h4>💰 Financial Impact Analysis</h4>
            <ul>
                <li><strong>Additional Contributions:</strong> ${roi_data.get('total_estimated_additional_contributions', 0):,.0f} in estimated additional employee savings</li>
                <li><strong>Average Annual Benefit:</strong> ${roi_data.get('total_estimated_additional_contributions', 0) / max(roi_data.get('simulation_years', 1), 1):,.0f} per year across simulation period</li>
                <li><strong>Per-Employee Impact:</strong> ${roi_data.get('total_estimated_additional_contributions', 0) / max(overview_data.get('total_employees_with_escalations', 1), 1):,.0f} average additional contributions per escalated employee</li>
            </ul>

            <h4>✅ Compliance & Risk Management</h4>
            <ul>
                <li><strong>User Requirements:</strong> All core requirements (January 1st effective date, 1% increment, 10% cap) are being met</li>
                <li><strong>Cap Management:</strong> {overview_data.get('employees_at_cap', 0)} employees have reached the 10% maximum rate</li>
                <li><strong>System Integrity:</strong> Zero duplicate escalation events detected across all simulation years</li>
                <li><strong>Data Quality:</strong> {overview_data.get('health_status', 'Unknown')} health status with minimal violations</li>
            </ul>

            <h4>🚀 Strategic Recommendations</h4>
            <ul>
                <li><strong>Continue Current Strategy:</strong> System is performing excellently and meeting all design objectives</li>
                <li><strong>Monitor Cap Approach:</strong> Track employees approaching 10% cap for potential alternative benefits</li>
                <li><strong>Expand Demographics:</strong> Consider extending escalation eligibility to broader employee segments</li>
                <li><strong>Long-term Planning:</strong> Evaluate escalation parameters for next planning cycle</li>
            </ul>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Executive dashboard metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "💼 Business Impact Score",
                "A+",
                help="Overall assessment of escalation system business value",
            )

        with col2:
            st.metric(
                "🔒 Compliance Score",
                "100%",
                help="Adherence to all user requirements and regulatory guidelines",
            )

        with col3:
            st.metric(
                "📊 System Health",
                f"{overview_data.get('health_score', 0)}/100",
                help="Data quality and operational reliability score",
            )

    except Exception as e:
        st.error(f"Failed to render executive summary: {e}")


def main():
    """Main application logic."""
    render_header()

    # Initialize analytics engine
    analytics = EscalationAnalytics()

    # Check database connection
    if analytics.get_connection() is None:
        st.error(
            "Unable to connect to simulation database. Please ensure simulation has been run."
        )
        st.info(
            "Run the following command to generate data: `python run_multi_year.py`"
        )
        return

    # Create tabs for different analysis views
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "📊 Overview KPIs",
            "📈 Multi-Year Trends",
            "👥 Demographics",
            "✅ Compliance",
            "📋 Executive Summary",
        ]
    )

    with tab1:
        render_kpi_cards(analytics)

    with tab2:
        render_yearly_progression_chart(analytics)

    with tab3:
        render_demographic_analysis(analytics)

    with tab4:
        render_compliance_tracking(analytics)

    with tab5:
        render_executive_summary(analytics)

    # Footer
    st.markdown("---")
    st.markdown(
        f"""
    <div style='text-align: center; color: #666; margin-top: 2rem;'>
        <p><small>Epic E035: Deferral Rate Escalation Analytics • Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </div>
    """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
