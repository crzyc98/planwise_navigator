# Epic E024: Advanced Enrollment Features

## Epic Overview

### Summary
Extend the E023 Enrollment Engine MVP with advanced behavioral modeling, ML-based segmentation, auto-escalation features, and real-time analytics. This epic builds upon the proven SQL/dbt foundation to deliver sophisticated enrollment behavior simulation for complex plan design scenarios.

### Business Value
- Enables sophisticated behavioral modeling for complex plan designs
- Provides ML-driven enrollment predictions with 95%+ accuracy
- Supports auto-escalation modeling for long-term savings optimization
- Delivers executive-level analytics and A/B testing capabilities

### Success Criteria
- ✅ ML-based behavioral clustering achieves 95% enrollment prediction accuracy
- ✅ Auto-escalation modeling supports complex multi-year scenarios
- ✅ Real-time analytics dashboard provides sub-second query response
- ✅ A/B testing framework enables plan design experimentation
- ✅ Advanced features maintain <30 seconds processing for 100K employees

### Implementation Approach
**Advanced Features Phase (40 points)**
- ML-enhanced behavioral segmentation with K-means clustering
- Auto-escalation and complex deferral modeling
- Real-time analytics dashboard with interactive visualizations
- A/B testing framework for enrollment strategy optimization
- Psychological behavioral modeling for realistic projections

---

## User Stories

### Advanced Behavioral Modeling

#### Story S024-01: Advanced Behavioral Segmentation (12 points) 📅
**Status**: Post-MVP development
**As a** workforce analyst
**I want** ML-based behavioral clustering
**So that** I can model complex enrollment patterns with high accuracy

**Acceptance Criteria:**
- K-means clustering for 5-7 behavioral segments based on enrollment patterns
- Machine learning-enhanced probability curves using historical data
- Automated calibration against 3+ years of actual enrollment data
- Feature engineering including tenure, compensation growth, life events
- Cross-validation framework ensuring 95%+ prediction accuracy
- Integration with existing SQL/dbt pipeline for performance

**Technical Implementation:**
- Scikit-learn K-means clustering on historical enrollment patterns
- Feature matrix including demographics, compensation, tenure, seasonality
- Automated hyperparameter tuning with grid search
- Model persistence and versioning for reproducible results
- SQL UDF integration for real-time segment assignment

#### Story S024-02: Psychological Behavioral Modeling (8 points) 📅
**Status**: Post-MVP development
**As a** behavioral economist
**I want** psychological factor modeling
**So that** I can simulate realistic decision-making patterns

**Acceptance Criteria:**
- Loss aversion modeling for opt-out behavior
- Present bias effects on deferral rate selection
- Social influence factors based on peer enrollment rates
- Seasonal enrollment pattern recognition
- Integration with demographic segmentation for personalized modeling

### Auto-Escalation Features

#### Story S024-03: Auto-Escalation Engine (8 points) 📅
**Status**: Post-MVP development
**As a** retirement committee member
**I want** to model automatic increase programs
**So that** I can assess long-term savings improvements

**Acceptance Criteria:**
- Annual escalation processing with configurable increase amounts (1%, 2%, etc.)
- Behavioral opt-out rates for automatic increases by demographic segment
- Integration with salary increase events for realistic timing
- Multi-year escalation path modeling up to IRS limits
- Escalation event generation in existing event sourcing system
- Performance optimization for complex multi-year scenarios

**Technical Implementation:**
- SQL-based escalation logic integrated with yearly event processing
- Configurable escalation schedules via dbt variables
- Behavioral opt-out modeling using similar patterns to enrollment opt-outs
- Integration with promotion and merit increase events for realistic timing

#### Story S024-04: Complex Deferral Strategies (6 points) 📅
**Status**: Post-MVP development
**As a** plan administrator
**I want** sophisticated deferral election modeling
**So that** I can simulate complex contribution strategies

**Acceptance Criteria:**
- Roth vs. traditional pre-tax election modeling
- Catch-up contribution eligibility and election rates
- After-tax contribution modeling for highly compensated employees
- Deferral rate change modeling (mid-year adjustments)
- Integration with compensation limit testing

### Analytics and Optimization

#### Story S024-05: Real-Time Analytics Dashboard (8 points) 📅
**Status**: Post-MVP development
**As a** CFO
**I want** interactive enrollment analytics
**So that** I can make data-driven plan design decisions

**Acceptance Criteria:**
- Interactive participation rate dashboards with drill-down capabilities
- Scenario comparison reports with side-by-side metrics
- Executive-level enrollment metrics with trend analysis
- Real-time query performance (<50ms for standard reports)
- Export capabilities for board presentations
- Mobile-responsive design for executive access

**Technical Implementation:**
- Streamlit-based dashboard with advanced visualizations
- DuckDB materialized views for sub-second query performance
- Plotly interactive charts with filtering and drill-down
- Automated report generation with PDF export
- Integration with existing orchestrator_mvp simulation results

#### Story S024-06: A/B Testing Framework (6 points) 📅
**Status**: Post-MVP development
**As a** plan design consultant
**I want** enrollment strategy experimentation
**So that** I can optimize plan features for maximum participation

**Acceptance Criteria:**
- A/B test configuration for different auto-enrollment strategies
- Statistical significance testing for enrollment rate differences
- Multi-variant testing for complex plan design scenarios
- Automated experiment monitoring and results reporting
- Integration with behavioral segmentation for targeted testing

**Technical Implementation:**
- Experiment configuration via YAML with treatment/control groups
- Statistical analysis using SciPy for significance testing
- Automated experiment execution within simulation framework
- Results tracking and visualization in analytics dashboard

---

## Technical Specifications

### ML-Enhanced Behavioral Segmentation

#### Behavioral Feature Engineering
```python
# Advanced behavioral features for clustering
behavioral_features = [
    'enrollment_delay_days',          # Time from eligibility to enrollment
    'initial_deferral_rate',          # First contribution rate selected
    'deferral_change_frequency',      # How often rates are modified
    'opt_out_probability_score',      # Calculated risk of opting out
    'peer_influence_factor',          # Enrollment rate in similar demographics
    'seasonal_enrollment_pattern',    # Month/quarter of enrollment tendency
    'compensation_growth_trajectory', # Historical salary increase pattern
    'tenure_at_enrollment',           # Service years when enrolled
    'life_event_correlation',         # Marriage, birth, etc. timing
    'financial_stress_indicators'     # Low balance, loan activity, etc.
]
```

#### K-Means Clustering Implementation
```python
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

class AdvancedBehavioralSegmentation:
    def __init__(self, n_segments=6):
        self.n_segments = n_segments
        self.scaler = StandardScaler()
        self.kmeans = KMeans(n_clusters=n_segments, random_state=42)

    def fit_behavioral_segments(self, enrollment_history: pd.DataFrame):
        """Fit behavioral segments using historical enrollment data."""
        features = self.engineer_behavioral_features(enrollment_history)
        features_scaled = self.scaler.fit_transform(features)

        # Find optimal number of clusters using elbow method
        self.optimize_cluster_count(features_scaled)

        # Fit final model
        self.kmeans.fit(features_scaled)

        return self.kmeans.labels_

    def predict_enrollment_behavior(self, employee_features: pd.DataFrame):
        """Predict enrollment behavior for new employees."""
        features_scaled = self.scaler.transform(employee_features)
        segments = self.kmeans.predict(features_scaled)

        # Map segments to enrollment probabilities
        return self.map_segments_to_probabilities(segments)
```

### Auto-Escalation SQL Implementation

#### dbt Model for Auto-Escalation Processing
```sql
-- models/advanced/int_auto_escalation_events.sql
{{ config(materialized='table') }}

WITH current_participants AS (
    SELECT *
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE enrolled = true
    AND simulation_year = {{ var('current_year') }}
),

escalation_eligible AS (
    SELECT
        *,
        -- Check if participant has been enrolled for full year
        simulation_year - enrollment_year >= 1 as eligible_for_escalation,

        -- Calculate current contribution rate
        current_pre_tax_rate + current_roth_rate as total_current_rate,

        -- Determine escalation amount based on plan design
        CASE
            WHEN total_current_rate < 0.03 THEN {{ var('escalation_rate_low') }}
            WHEN total_current_rate < 0.06 THEN {{ var('escalation_rate_medium') }}
            ELSE {{ var('escalation_rate_high') }}
        END as escalation_amount,

        -- Calculate behavioral opt-out probability
        CASE age_segment
            WHEN 'young' THEN {{ var('escalation_opt_out_young') }}
            WHEN 'mid_career' THEN {{ var('escalation_opt_out_mid') }}
            WHEN 'mature' THEN {{ var('escalation_opt_out_mature') }}
            ELSE {{ var('escalation_opt_out_senior') }}
        END as escalation_opt_out_probability

    FROM current_participants
    WHERE eligible_for_escalation = true
    AND total_current_rate < {{ var('irs_contribution_limit_rate') }}
),

escalation_decisions AS (
    SELECT
        *,
        -- Deterministic random sampling for escalation opt-out
        (ABS(HASH(employee_id || 'escalation' || simulation_year)) % 1000000) / 1000000.0 as random_draw,
        random_draw > escalation_opt_out_probability as will_accept_escalation,

        CASE WHEN will_accept_escalation
            THEN LEAST(
                total_current_rate + escalation_amount,
                {{ var('irs_contribution_limit_rate') }}
            )
            ELSE total_current_rate
        END as new_contribution_rate

    FROM escalation_eligible
)

SELECT
    employee_id,
    simulation_year,
    eligible_for_escalation,
    escalation_amount,
    escalation_opt_out_probability,
    will_accept_escalation,
    total_current_rate as previous_rate,
    new_contribution_rate,
    new_contribution_rate - total_current_rate as rate_increase,
    current_timestamp as processed_at
FROM escalation_decisions
WHERE eligible_for_escalation = true
```

### Real-Time Analytics Implementation

#### Streamlit Dashboard for Advanced Analytics
```python
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

class AdvancedEnrollmentAnalytics:
    def __init__(self, duckdb_connection):
        self.conn = duckdb_connection

    def render_behavioral_segment_analysis(self):
        """Render advanced behavioral segment analytics."""
        st.header("🧠 Behavioral Segment Analysis")

        # Query behavioral segment data
        segment_data = self.conn.execute("""
            SELECT
                behavioral_segment,
                COUNT(*) as employee_count,
                AVG(enrollment_probability) as avg_enrollment_rate,
                AVG(deferral_rate) as avg_deferral_rate,
                AVG(opt_out_probability) as avg_opt_out_rate
            FROM {{ ref('int_behavioral_segments') }}
            GROUP BY behavioral_segment
            ORDER BY employee_count DESC
        """).df()

        # Create multi-metric visualization
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Employee Distribution', 'Enrollment Rates',
                          'Average Deferral Rates', 'Opt-Out Risk'),
            specs=[[{"type": "pie"}, {"type": "bar"}],
                   [{"type": "bar"}, {"type": "bar"}]]
        )

        # Employee distribution pie chart
        fig.add_trace(
            go.Pie(values=segment_data['employee_count'],
                   labels=segment_data['behavioral_segment']),
            row=1, col=1
        )

        # Enrollment rates bar chart
        fig.add_trace(
            go.Bar(x=segment_data['behavioral_segment'],
                   y=segment_data['avg_enrollment_rate'],
                   name='Enrollment Rate'),
            row=1, col=2
        )

        st.plotly_chart(fig, use_container_width=True)

    def render_auto_escalation_projections(self):
        """Render auto-escalation impact projections."""
        st.header("📈 Auto-Escalation Impact Projections")

        # Multi-year escalation projections
        escalation_data = self.conn.execute("""
            SELECT
                simulation_year,
                COUNT(*) as eligible_employees,
                SUM(CASE WHEN will_accept_escalation THEN 1 ELSE 0 END) as accepted_escalation,
                AVG(rate_increase) as avg_rate_increase,
                SUM(rate_increase * annual_compensation) as additional_contributions
            FROM {{ ref('int_auto_escalation_events') }}
            GROUP BY simulation_year
            ORDER BY simulation_year
        """).df()

        # Create escalation impact visualization
        fig = px.line(escalation_data,
                     x='simulation_year',
                     y='additional_contributions',
                     title='Projected Additional Contributions from Auto-Escalation')

        st.plotly_chart(fig, use_container_width=True)
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| ML Model Training | <5 minutes for behavioral clustering | Optimized scikit-learn with parallel processing |
| Behavioral Prediction | <100ms for population scoring | Pre-computed segment assignments with caching |
| Auto-Escalation Processing | <30 seconds for 100K employees | SQL-based vectorized processing with DuckDB |
| Real-Time Analytics | <50ms for dashboard queries | Materialized views with incremental updates |
| A/B Testing Analysis | <2 seconds for statistical significance | Pre-aggregated test metrics with lazy evaluation |

## Dependencies
- E023: Enrollment Engine MVP (foundation)
- E022: Eligibility Engine (employee lifecycle)
- Historical enrollment data (3+ years for ML training)
- Scikit-learn 1.3+ for behavioral clustering
- Plotly 5.0+ for advanced visualizations
- SciPy 1.10+ for statistical analysis

## Risks
- **Risk**: ML model complexity impacts performance
- **Mitigation**: Pre-compute segment assignments and cache predictions
- **Risk**: Historical data quality affects model accuracy
- **Mitigation**: Implement data quality checks and model validation framework
- **Risk**: Advanced features increase system complexity
- **Mitigation**: Maintain modular architecture with clear separation of concerns

## Estimated Effort
**Total Story Points**: 40 points
**Estimated Duration**: 3-4 sprints (6-8 weeks)

---

## Definition of Done
- [ ] ML-based behavioral segmentation implemented and validated
- [ ] Auto-escalation engine fully functional with multi-year support
- [ ] Advanced deferral strategies modeling complete
- [ ] Real-time analytics dashboard deployed and tested
- [ ] A/B testing framework operational
- [ ] Performance targets met for all advanced features
- [ ] Comprehensive user documentation and training materials
- [ ] Integration testing with E023 MVP completed
