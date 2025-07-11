# Epic E023: Behavioral Enrollment Engine

## Epic Overview

### Summary
Develop a high-performance behavioral enrollment simulation engine using vectorized processing that models participant enrollment behavior including auto-enrollment, opt-out rates, and voluntary enrollment patterns based on demographic characteristics and behavioral segments.

### Business Value
- Enables accurate participation rate projections for plan design decisions
- Models the financial impact of auto-enrollment features saving $1-5M annually
- Provides insights into employee savings behavior by demographic segments

### Success Criteria
- ✅ Models enrollment with 95% accuracy vs historical data using behavioral segments
- ✅ Supports auto-enrollment with configurable default rates using vectorized processing
- ✅ Simulates realistic opt-out and escalation behavior with <30 second processing for 100K employees
- ✅ Generates detailed enrollment analytics by segment with real-time performance
- ✅ Achieves reproducible results with random seed control
- ✅ Supports behavioral A/B testing for enrollment strategy optimization

---

## User Stories

### Story 1: Vectorized Auto-Enrollment Logic (18 points)
**As a** plan sponsor
**I want** to model auto-enrollment impact
**So that** I can predict participation rates and costs

**Acceptance Criteria:**
- Vectorized auto-enrollment processing for 100K+ employees in <10 seconds
- Configurable auto-enrollment default rate (3%, 6%, etc.) with segment-specific overrides
- Opt-out window modeling (30, 60, 90 days) using efficient random sampling
- Different defaults by employee class with dynamic rule application
- Creates batch ENROLLMENT events with source = "auto" and UUID correlation
- Tracks opt-out events and reasons with detailed behavioral analytics
- Supports real-time enrollment status queries with optimized indexing

### Story 2: Behavioral Segment Enrollment Modeling (12 points)
**As a** workforce analyst
**I want** realistic voluntary enrollment rates
**So that** my projections match actual behavior

**Acceptance Criteria:**
- Pre-computed enrollment probability curves by behavioral segments (age/salary/tenure/education)
- Vectorized time-to-enrollment distributions using statistical sampling
- Machine learning-enhanced deferral rate selection patterns
- Automated calibration against historical data with validation metrics
- Supports re-enrollment campaigns with effectiveness tracking
- Dynamic behavioral segment assignment with real-time updates
- A/B testing framework for enrollment strategy comparison

### Story 3: Intelligent Deferral Rate Selection (10 points)
**As a** benefits consultant
**I want** to model initial deferral elections
**So that** I can project employee and employer contributions

**Acceptance Criteria:**
- Vectorized distribution of deferral rates by behavioral segments
- Common clustering (3%, 6%, 10%, max) with intelligent anchoring logic
- Dynamic impact of match formula on elections with optimization suggestions
- Roth vs traditional split modeling based on tax optimization patterns
- Behavioral anchoring effects with psychological modeling components
- Machine learning recommendations for optimal default rates
- Integration with compensation planning for realistic contribution limits

### Story 4: Auto-Escalation Implementation (8 points)
**As a** retirement plan committee member
**I want** to model automatic increase programs
**So that** I can assess long-term savings improvements

**Acceptance Criteria:**
- Vectorized annual increase processing with configurable amounts (1%, 2%)
- Maximum escalation cap (10%, 15%) with intelligent stopping logic
- Behavioral opt-out rates for increases using segmented models
- Flexible timing of increases (anniversary, Jan 1, quarterly) with payroll integration
- Real-time impact analysis on average deferral rates with trend projections
- Escalation effectiveness analytics with ROI calculations
- Integration with salary increase events for optimal timing

### Story 5: Real-Time Enrollment Analytics & Reporting (8 points)
**As a** CFO
**I want** clear enrollment projections
**So that** I can budget for retirement contributions

**Acceptance Criteria:**
- Real-time participation rate tracking by year with drill-down capabilities
- Interactive average deferral rate trends with predictive analytics
- Comprehensive opt-out analysis by behavioral segments with intervention recommendations
- New hire vs existing employee pattern analysis with onboarding optimization insights
- Side-by-side scenario comparison reports with statistical significance testing
- Automated insights generation using machine learning pattern detection
- Executive dashboard with key enrollment metrics and alerts

---

## Technical Specifications

### Enrollment Configuration
```yaml
enrollment_config:
  auto_enrollment:
    enabled: true
    default_deferral_rate: 0.06
    opt_out_window_days: 90

    # Opt-out rates by demographic
    opt_out_rates:
      by_age:
        - {min: 18, max: 25, rate: 0.35}
        - {min: 26, max: 35, rate: 0.20}
        - {min: 36, max: 50, rate: 0.15}
        - {min: 51, max: 99, rate: 0.10}

      by_salary:
        - {min: 0, max: 30000, rate: 0.40}
        - {min: 30001, max: 50000, rate: 0.25}
        - {min: 50001, max: 100000, rate: 0.15}
        - {min: 100001, max: 999999, rate: 0.05}

  voluntary_enrollment:
    # Probability of enrolling within first year
    enrollment_curves:
      baseline: 0.60
      age_factor: 0.01  # +1% per year over 25
      tenure_factor: 0.05  # +5% per year of service

  deferral_distributions:
    # Common deferral rate selections
    rates:
      - {rate: 0.03, probability: 0.25}  # Match threshold
      - {rate: 0.06, probability: 0.35}  # Common default
      - {rate: 0.10, probability: 0.20}  # Round number
      - {rate: 0.15, probability: 0.10}  # High savers
      - {rate: "max", probability: 0.10} # Max contributors
```

### Vectorized Enrollment Simulation Engine
```python
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sklearn.cluster import KMeans
from dataclasses import dataclass

@dataclass
class BehavioralSegment:
    segment_id: str
    enrollment_probability: float
    opt_out_probability: float
    deferral_rate_preferences: Dict[float, float]  # rate -> probability
    escalation_acceptance_rate: float

class VectorizedEnrollmentEngine:
    def __init__(self, config: EnrollmentConfig, random_seed: Optional[int] = None):
        self.config = config
        self.random_state = np.random.RandomState(random_seed)
        self.behavioral_segments = self._initialize_behavioral_segments()

    def simulate_enrollment_batch(self, eligible_employees_df: pd.DataFrame,
                                  eligibility_date: datetime) -> pd.DataFrame:
        """Process enrollment for entire eligible population efficiently"""

        # Assign behavioral segments
        employees_df = self._assign_behavioral_segments(eligible_employees_df)

        # Initialize enrollment columns
        employees_df['enrolled'] = False
        employees_df['enrollment_date'] = pd.NaT
        employees_df['deferral_rate'] = 0.0
        employees_df['enrollment_source'] = 'none'
        employees_df['opted_out'] = False
        employees_df['opt_out_date'] = pd.NaT

        if self.config.auto_enrollment.enabled:
            employees_df = self._process_auto_enrollment_vectorized(
                employees_df, eligibility_date
            )
        else:
            employees_df = self._process_voluntary_enrollment_vectorized(
                employees_df, eligibility_date
            )

        return employees_df

    def _assign_behavioral_segments(self, employees_df: pd.DataFrame) -> pd.DataFrame:
        """Assign employees to behavioral segments using clustering"""

        # Create feature matrix for clustering
        features = employees_df[[
            'age', 'annual_salary', 'tenure_months', 'education_level_code'
        ]].copy()

        # Normalize features
        features['age_norm'] = (features['age'] - 25) / 40  # Normalize to 0-1
        features['salary_norm'] = np.log(features['annual_salary']) / np.log(200000)
        features['tenure_norm'] = features['tenure_months'] / 240  # 20 years max
        features['education_norm'] = features['education_level_code'] / 4

        # K-means clustering to create behavioral segments
        kmeans = KMeans(n_clusters=5, random_state=42)
        employees_df['behavioral_segment'] = kmeans.fit_predict(
            features[['age_norm', 'salary_norm', 'tenure_norm', 'education_norm']]
        )

        return employees_df

    def _process_auto_enrollment_vectorized(self, employees_df: pd.DataFrame,
                                           eligibility_date: datetime) -> pd.DataFrame:
        """Process auto-enrollment using vectorized operations"""

        # All eligible employees are auto-enrolled on eligibility date
        employees_df['enrolled'] = True
        employees_df['enrollment_date'] = eligibility_date
        employees_df['enrollment_source'] = 'auto'

        # Apply segment-specific default rates or global default
        employees_df['deferral_rate'] = self.config.auto_enrollment.default_deferral_rate

        # Vectorized opt-out probability calculation
        opt_out_probabilities = employees_df.apply(
            lambda row: self._calculate_opt_out_probability_vectorized(row), axis=1
        )

        # Generate random numbers for opt-out decisions
        random_draws = self.random_state.rand(len(employees_df))
        opt_out_mask = random_draws < opt_out_probabilities

        # Process opt-outs
        employees_df.loc[opt_out_mask, 'opted_out'] = True
        employees_df.loc[opt_out_mask, 'enrolled'] = False
        employees_df.loc[opt_out_mask, 'deferral_rate'] = 0.0

        # Calculate opt-out dates (random within window)
        opt_out_days = self.random_state.randint(
            1, self.config.auto_enrollment.opt_out_window_days + 1,
            size=opt_out_mask.sum()
        )
        employees_df.loc[opt_out_mask, 'opt_out_date'] = [
            eligibility_date + timedelta(days=int(days)) for days in opt_out_days
        ]

        return employees_df

    def _process_voluntary_enrollment_vectorized(self, employees_df: pd.DataFrame,
                                                eligibility_date: datetime) -> pd.DataFrame:
        """Process voluntary enrollment using behavioral segments"""

        # Calculate enrollment probabilities by segment
        enrollment_probabilities = employees_df['behavioral_segment'].map(
            lambda seg: self.behavioral_segments[seg].enrollment_probability
        )

        # Generate random numbers for enrollment decisions
        random_draws = self.random_state.rand(len(employees_df))
        enrollment_mask = random_draws < enrollment_probabilities

        # Set enrollment status
        employees_df.loc[enrollment_mask, 'enrolled'] = True
        employees_df.loc[enrollment_mask, 'enrollment_source'] = 'voluntary'

        # Calculate enrollment timing (days after eligibility)
        enrolled_count = enrollment_mask.sum()
        if enrolled_count > 0:
            # Sample from realistic enrollment timing distribution
            enrollment_delays = self.random_state.exponential(
                scale=60, size=enrolled_count  # Average 60 days to enroll
            ).astype(int)

            enrollment_dates = [
                eligibility_date + timedelta(days=int(delay))
                for delay in enrollment_delays
            ]
            employees_df.loc[enrollment_mask, 'enrollment_date'] = enrollment_dates

            # Select deferral rates based on behavioral segments
            deferral_rates = self._sample_deferral_rates_vectorized(
                employees_df.loc[enrollment_mask]
            )
            employees_df.loc[enrollment_mask, 'deferral_rate'] = deferral_rates

        return employees_df

    def _calculate_opt_out_probability_vectorized(self, employee_row: pd.Series) -> float:
        """Calculate opt-out probability based on employee characteristics"""

        # Base probability from behavioral segment
        base_prob = self.behavioral_segments[employee_row['behavioral_segment']].opt_out_probability

        # Age adjustment
        age_factor = 1.0
        if employee_row['age'] < 30:
            age_factor = 1.5  # Younger employees more likely to opt out
        elif employee_row['age'] > 50:
            age_factor = 0.7  # Older employees less likely to opt out

        # Salary adjustment
        salary_factor = 1.0
        if employee_row['annual_salary'] < 40000:
            salary_factor = 1.3  # Lower income more likely to opt out
        elif employee_row['annual_salary'] > 100000:
            salary_factor = 0.6  # Higher income less likely to opt out

        return min(base_prob * age_factor * salary_factor, 0.95)

    def _sample_deferral_rates_vectorized(self, enrolled_employees_df: pd.DataFrame) -> List[float]:
        """Sample deferral rates based on behavioral segments and preferences"""

        deferral_rates = []

        for _, employee in enrolled_employees_df.iterrows():
            segment = self.behavioral_segments[employee['behavioral_segment']]

            # Sample from segment's deferral rate distribution
            rates = list(segment.deferral_rate_preferences.keys())
            probabilities = list(segment.deferral_rate_preferences.values())

            # Handle 'max' rate by calculating actual max for this employee
            if 'max' in rates:
                max_idx = rates.index('max')
                irs_limit = 23000  # 2025 limit
                max_rate = min(irs_limit / employee['annual_salary'], 0.5)  # Cap at 50%
                rates[max_idx] = max_rate

            selected_rate = self.random_state.choice(rates, p=probabilities)
            deferral_rates.append(float(selected_rate))

        return deferral_rates

    def _initialize_behavioral_segments(self) -> Dict[int, BehavioralSegment]:
        """Initialize behavioral segments with realistic parameters"""

        return {
            0: BehavioralSegment(  # Young, low earners
                segment_id="young_low_earners",
                enrollment_probability=0.45,
                opt_out_probability=0.35,
                deferral_rate_preferences={0.03: 0.4, 0.06: 0.3, 0.10: 0.2, 0.15: 0.1},
                escalation_acceptance_rate=0.6
            ),
            1: BehavioralSegment(  # Mid-career, moderate earners
                segment_id="mid_career_moderate",
                enrollment_probability=0.75,
                opt_out_probability=0.15,
                deferral_rate_preferences={0.03: 0.2, 0.06: 0.4, 0.10: 0.25, 0.15: 0.15},
                escalation_acceptance_rate=0.8
            ),
            2: BehavioralSegment(  # High earners
                segment_id="high_earners",
                enrollment_probability=0.90,
                opt_out_probability=0.05,
                deferral_rate_preferences={0.06: 0.1, 0.10: 0.2, 0.15: 0.3, 'max': 0.4},
                escalation_acceptance_rate=0.9
            ),
            3: BehavioralSegment(  # Long tenure, engaged
                segment_id="long_tenure_engaged",
                enrollment_probability=0.85,
                opt_out_probability=0.08,
                deferral_rate_preferences={0.06: 0.15, 0.10: 0.35, 0.15: 0.35, 'max': 0.15},
                escalation_acceptance_rate=0.85
            ),
            4: BehavioralSegment(  # Cautious savers
                segment_id="cautious_savers",
                enrollment_probability=0.65,
                opt_out_probability=0.20,
                deferral_rate_preferences={0.03: 0.5, 0.06: 0.35, 0.10: 0.15},
                escalation_acceptance_rate=0.4
            )
        }

# Usage example for batch processing
def process_enrollment_batch(eligible_employees_df: pd.DataFrame,
                           config: EnrollmentConfig,
                           eligibility_date: datetime,
                           random_seed: int = 42) -> pd.DataFrame:
    """Process enrollment for all eligible employees"""

    engine = VectorizedEnrollmentEngine(config, random_seed)
    result_df = engine.simulate_enrollment_batch(eligible_employees_df, eligibility_date)

    # Generate enrollment events for enrolled employees
    enrolled_employees = result_df[result_df['enrolled'] == True]

    if len(enrolled_employees) > 0:
        enrollment_events = create_enrollment_events_batch(
            enrolled_employees, eligibility_date
        )

        # Generate opt-out events
        opted_out_employees = result_df[result_df['opted_out'] == True]
        if len(opted_out_employees) > 0:
            opt_out_events = create_opt_out_events_batch(
                opted_out_employees
            )
            enrollment_events.extend(opt_out_events)

        return result_df, enrollment_events

    return result_df, []
```

---

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Batch Enrollment Processing | <30 seconds for 100K employees | Vectorized behavioral segmentation with clustering |
| Behavioral Segment Assignment | <5 seconds for population clustering | Pre-computed feature matrices with K-means |
| Random Sampling | Reproducible with seed control | NumPy RandomState for deterministic results |
| Memory Usage | <6GB for 100K employee simulation | Efficient DataFrame operations with optimized dtypes |
| Real-time Queries | <50ms for enrollment analytics | Materialized behavioral segment summaries |

## Dependencies
- E021: DC Plan Data Model (event schema)
- E022: Eligibility Engine (eligible population)
- Historical enrollment data for calibration and ML training
- Pandas/Polars for vectorized DataFrame operations
- NumPy for efficient random number generation
- Scikit-learn for behavioral segmentation clustering
- Statistical libraries for distribution sampling

## Risks
- **Risk**: Behavioral modeling accuracy
- **Mitigation**: Calibrate against 3+ years of actual data
- **Risk**: Auto-enrollment legal compliance
- **Mitigation**: Include all required notices and timing

## Estimated Effort
**Total Story Points**: 56 points
**Estimated Duration**: 3-4 sprints

---

## Definition of Done
- [ ] Auto-enrollment logic fully implemented
- [ ] Voluntary enrollment modeling calibrated
- [ ] Deferral rate distributions validated
- [ ] Auto-escalation features complete
- [ ] Analytics reports designed and tested
- [ ] Performance targets met
- [ ] User documentation complete
