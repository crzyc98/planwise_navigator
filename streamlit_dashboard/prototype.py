# filename: streamlit_dashboard/prototype.py
"""Streamlit dashboard prototype for PlanWise Navigator."""

from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Page config
st.set_page_config(
    page_title="PlanWise Navigator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 0.25rem;
        padding: 0.75rem;
        margin: 1rem 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Header
st.markdown('<h1 class="main-header">📊 PlanWise Navigator</h1>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("Configuration")

    # Simulation parameters
    st.subheader("Simulation Settings")
    start_year = st.number_input("Start Year", 2024, 2030, 2025)
    end_year = st.number_input("End Year", start_year, 2035, 2029)

    growth_rate = st.slider("Target Growth Rate", -10.0, 20.0, 3.0, 0.5, format="%g%%")
    termination_rate = st.slider(
        "Termination Rate", 0.0, 30.0, 12.0, 0.5, format="%g%%"
    )

    st.subheader("Display Options")
    show_confidence = st.checkbox("Show Confidence Intervals", True)
    show_scenarios = st.checkbox("Compare Scenarios", False)

    if st.button("Run Simulation", type="primary", use_container_width=True):
        st.session_state.simulation_run = True
        st.balloons()

# Main content tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "📈 Executive Summary",
        "👥 Workforce Analysis",
        "💰 Financial Impact",
        "🎯 Scenario Planning",
        "📊 Reports",
    ]
)


# Generate sample data
@st.cache_data
def generate_sample_data():
    """Generate sample simulation data."""
    years = list(range(2025, 2030))

    # Workforce data
    workforce_data = []
    base_headcount = 1000
    for i, year in enumerate(years):
        headcount = int(base_headcount * (1 + growth_rate / 100) ** i)
        workforce_data.append(
            {
                "Year": year,
                "Headcount": headcount,
                "Hires": int(headcount * 0.15),
                "Terminations": int(headcount * termination_rate / 100),
                "Promotions": int(headcount * 0.12),
            }
        )

    # Level distribution
    levels = ["Entry Level", "Experienced", "Senior", "Lead/Principal", "Executive"]
    level_dist = pd.DataFrame(
        {
            "Level": levels * len(years),
            "Year": np.repeat(years, len(levels)),
            "Count": np.random.multinomial(
                headcount, [0.4, 0.3, 0.2, 0.08, 0.02], len(years)
            ).flatten(),
        }
    )

    return pd.DataFrame(workforce_data), level_dist


workforce_df, level_df = generate_sample_data()

with tab1:
    st.header("Executive Summary")

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        end_headcount = workforce_df.iloc[-1]["Headcount"]
        start_headcount = workforce_df.iloc[0]["Headcount"]
        growth_pct = ((end_headcount - start_headcount) / start_headcount) * 100
        st.metric("Final Headcount", f"{end_headcount:,}", f"{growth_pct:+.1f}%")

    with col2:
        total_hires = workforce_df["Hires"].sum()
        st.metric("Total Hires", f"{total_hires:,}")

    with col3:
        avg_turnover = (
            workforce_df["Terminations"].sum() / workforce_df["Headcount"].sum() * 100
        )
        st.metric("Avg Turnover", f"{avg_turnover:.1f}%")

    with col4:
        total_comp = end_headcount * 95000  # Assumed avg salary
        st.metric("Total Comp (Final)", f"${total_comp/1e6:.1f}M")

    # Headcount projection chart
    st.subheader("Headcount Projection")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=workforce_df["Year"],
            y=workforce_df["Headcount"],
            mode="lines+markers",
            name="Projected",
            line=dict(color="#1f77b4", width=3),
        )
    )

    if show_confidence:
        # Add confidence bands
        upper = workforce_df["Headcount"] * 1.05
        lower = workforce_df["Headcount"] * 0.95

        fig.add_trace(
            go.Scatter(
                x=workforce_df["Year"].tolist() + workforce_df["Year"].tolist()[::-1],
                y=upper.tolist() + lower.tolist()[::-1],
                fill="toself",
                fillcolor="rgba(31,119,180,0.2)",
                line=dict(color="rgba(255,255,255,0)"),
                name="95% Confidence",
                showlegend=True,
            )
        )

    fig.update_layout(
        height=400, xaxis_title="Year", yaxis_title="Headcount", hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Warning box
    if growth_rate > 10:
        st.markdown(
            """
        <div class="warning-box">
        ⚠️ <strong>High Growth Warning:</strong> Growth rates above 10% may require
        significant recruiting infrastructure investment.
        </div>
        """,
            unsafe_allow_html=True,
        )

with tab2:
    st.header("Workforce Analysis")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Level Distribution Over Time")
        fig = px.area(
            level_df, x="Year", y="Count", color="Level", title="Workforce by Level"
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Annual Workforce Events")
        events_df = workforce_df[["Year", "Hires", "Terminations", "Promotions"]].melt(
            id_vars=["Year"], var_name="Event Type", value_name="Count"
        )

        fig = px.bar(
            events_df,
            x="Year",
            y="Count",
            color="Event Type",
            title="Workforce Movement",
            barmode="group",
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    # Detailed metrics table
    st.subheader("Year-over-Year Metrics")

    metrics_df = workforce_df.copy()
    metrics_df["Growth %"] = metrics_df["Headcount"].pct_change() * 100
    metrics_df["Turnover %"] = (
        metrics_df["Terminations"] / metrics_df["Headcount"]
    ) * 100

    # Format for display
    display_df = metrics_df[
        [
            "Year",
            "Headcount",
            "Growth %",
            "Hires",
            "Terminations",
            "Turnover %",
            "Promotions",
        ]
    ]
    display_df = display_df.style.format(
        {
            "Headcount": "{:,.0f}",
            "Growth %": "{:+.1f}%",
            "Hires": "{:,.0f}",
            "Terminations": "{:,.0f}",
            "Turnover %": "{:.1f}%",
            "Promotions": "{:,.0f}",
        }
    )

    st.dataframe(display_df, use_container_width=True)

with tab3:
    st.header("Financial Impact")

    # Compensation projections
    st.subheader("Total Compensation Projection")

    # Generate comp data
    comp_data = []
    for _, row in workforce_df.iterrows():
        base_comp = row["Headcount"] * 95000
        benefits = base_comp * 0.25
        total = base_comp + benefits

        comp_data.append(
            {
                "Year": row["Year"],
                "Base Salary": base_comp,
                "Benefits": benefits,
                "Total": total,
            }
        )

    comp_df = pd.DataFrame(comp_data)

    # Stacked bar chart
    fig = go.Figure()
    fig.add_trace(
        go.Bar(name="Base Salary", x=comp_df["Year"], y=comp_df["Base Salary"])
    )
    fig.add_trace(go.Bar(name="Benefits", x=comp_df["Year"], y=comp_df["Benefits"]))

    fig.update_layout(
        barmode="stack",
        height=400,
        yaxis_title="Compensation ($)",
        yaxis_tickformat="$,.0f",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Cost per hire analysis
    col1, col2 = st.columns(2)

    with col1:
        st.metric("5-Year Total Comp", f"${comp_df['Total'].sum()/1e9:.2f}B")
        st.metric(
            "Avg Comp Growth",
            f"{(comp_df['Total'].iloc[-1]/comp_df['Total'].iloc[0])**(1/4)-1:.1%}",
        )

    with col2:
        total_hires = workforce_df["Hires"].sum()
        cost_per_hire = 5000  # Assumed
        total_hiring_cost = total_hires * cost_per_hire
        st.metric("Total Hiring Costs", f"${total_hiring_cost/1e6:.1f}M")
        st.metric("Avg Cost per Hire", f"${cost_per_hire:,}")

with tab4:
    st.header("Scenario Planning")

    if show_scenarios:
        # Scenario comparison
        st.subheader("Scenario Comparison")

        scenarios = {
            "Conservative": {"growth": 1.0, "termination": 15.0},
            "Base Case": {"growth": growth_rate, "termination": termination_rate},
            "Aggressive": {"growth": 8.0, "termination": 10.0},
        }

        fig = go.Figure()

        for scenario_name, params in scenarios.items():
            # Calculate projections
            headcounts = []
            base = 1000
            for i in range(5):
                base = base * (1 + params["growth"] / 100)
                headcounts.append(base)

            fig.add_trace(
                go.Scatter(
                    x=list(range(2025, 2030)),
                    y=headcounts,
                    mode="lines+markers",
                    name=scenario_name,
                )
            )

        fig.update_layout(
            title="Headcount Under Different Scenarios",
            xaxis_title="Year",
            yaxis_title="Headcount",
            height=500,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Scenario metrics table
        st.subheader("Scenario Outcomes")

        scenario_metrics = []
        for name, params in scenarios.items():
            final_headcount = 1000 * (1 + params["growth"] / 100) ** 5
            total_cost = final_headcount * 95000 * 1.25 * 5  # Simple approximation

            scenario_metrics.append(
                {
                    "Scenario": name,
                    "Growth Rate": f"{params['growth']}%",
                    "Termination Rate": f"{params['termination']}%",
                    "Final Headcount": f"{final_headcount:,.0f}",
                    "Total 5Y Cost": f"${total_cost/1e9:.2f}B",
                }
            )

        st.dataframe(pd.DataFrame(scenario_metrics), use_container_width=True)
    else:
        st.info("Enable 'Compare Scenarios' in the sidebar to see scenario analysis.")

with tab5:
    st.header("Reports & Export")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Available Reports")

        reports = [
            {"name": "Executive Summary", "format": "PDF", "icon": "📄"},
            {"name": "Detailed Projections", "format": "Excel", "icon": "📊"},
            {"name": "Scenario Analysis", "format": "PDF", "icon": "📈"},
            {"name": "Financial Impact", "format": "Excel", "icon": "💰"},
            {"name": "Board Presentation", "format": "PowerPoint", "icon": "🎯"},
        ]

        for report in reports:
            col_a, col_b, col_c = st.columns([1, 3, 1])
            with col_a:
                st.write(report["icon"])
            with col_b:
                st.write(f"**{report['name']}** ({report['format']})")
            with col_c:
                if st.button("Generate", key=f"gen_{report['name']}"):
                    st.info(f"Generating {report['name']}...")
                    # TODO: Implement report generation

    with col2:
        st.subheader("Quick Export")

        export_format = st.selectbox("Format", ["CSV", "Excel", "JSON"])

        include_options = st.multiselect(
            "Include",
            ["Projections", "Events", "Financial", "Scenarios"],
            default=["Projections", "Events"],
        )

        if st.button("Export Data", type="primary", use_container_width=True):
            # Create download
            csv = workforce_df.to_csv(index=False)
            st.download_button(
                "📥 Download",
                csv,
                "planwise_export.csv",
                "text/csv",
                use_container_width=True,
            )

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
    PlanWise Navigator v3.0 | Last simulation: {timestamp} |
    <a href='#'>Documentation</a> | <a href='#'>Support</a>
    </div>
    """.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M")
    ),
    unsafe_allow_html=True,
)
