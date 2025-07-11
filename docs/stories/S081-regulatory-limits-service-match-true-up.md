# Story S081: Regulatory Limits Service & Employer Match True-Up

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 13
**Priority**: High

## Story

**As a** plan administrator
**I want** version-controlled regulatory limits and automated true-up calculations
**So that** all compliance calculations are accurate and match benchmarks

## Business Context

This story implements a comprehensive regulatory limits service and automated employer match true-up calculation system. The service maintains version-controlled IRS limits with historical preservation while ensuring match calculations are accurate and benchmarked against golden datasets.

## Acceptance Criteria

### Version-Controlled Regulatory Limits Service
- [ ] **Ingest annual 402(g), 415(c), catch-up, and related IRS limits** from YAML/CSV
- [ ] **Support mid-year effective dates** for rare regulatory changes
- [ ] **Expose lookup API** for validation logic with plan-year context
- [ ] **Maintain historical limits** for audit trail and retroactive calculations
- [ ] **Automated alerts** when new IRS limits are published

### Employer Match True-Up Calculation During Seed Load
- [ ] **Calculate expected match** using plan's match formula and actual deferrals
- [ ] **Compare expected match** to already posted employer match amounts
- [ ] **Record `er_match_true_up = max(expected - posted, 0)`** when delta ≥ $5
- [ ] **Store 0 for true-up** when delta < $5 threshold
- [ ] **Allow `er_match_true_up` to be null** on raw ingest
- [ ] **Populate before final schema validation**

### True-Up Integration Requirements
- [ ] **All compliance calculations** (ADP/ACP, 402(g), 415(c)) must aggregate both `er_match` and `er_match_true_up`
- [ ] **Outputs must match** current benchmark for golden seed plan with zero row-level variance
- [ ] **Support replacement** of inferred values when sponsors provide actuals

### Enhanced Ingestion Pipeline
- [ ] **Accept expanded money-type enum** including `er_match_true_up`
- [ ] **Handle inferred true-up field** with proper null handling
- [ ] **Write daily event partitions** under `year=/plan=` directory structure
- [ ] **Maintain audit trail** of inference vs. provided values

### Automated Regression Tests
- [ ] **Validate inference logic** on under-matched participants (true-up > 0)
- [ ] **Validate over-matched participants** (true-up = 0)
- [ ] **Verify Section 415(c) totals** include inferred true-up amounts
- [ ] **Fail CI if inference** or limits lookup produces divergent results
- [ ] **Compare against golden dataset** row-by-row

## Technical Specifications

### Regulatory Limits Models
```python
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import yaml
import csv

class LimitType(str, Enum):
    EMPLOYEE_DEFERRAL = "employee_deferral_limit"
    CATCH_UP = "catch_up_contribution_limit"
    ANNUAL_ADDITIONS = "annual_additions_limit"
    COMPENSATION = "compensation_limit"
    HCE_THRESHOLD = "highly_compensated_threshold"
    KEY_EMPLOYEE = "key_employee_threshold"
    SS_WAGE_BASE = "social_security_wage_base"

class IRSLimits(BaseModel):
    plan_year: int = Field(..., ge=2020, le=2050)
    effective_date: date

    # Core contribution limits
    employee_deferral_limit: Decimal = Field(..., gt=0)
    catch_up_contribution_limit: Decimal = Field(..., ge=0)
    annual_additions_limit: Decimal = Field(..., gt=0)
    compensation_limit: Decimal = Field(..., gt=0)

    # Testing and discrimination limits
    highly_compensated_threshold: Decimal = Field(..., gt=0)
    key_employee_threshold: Decimal = Field(..., gt=0)

    # Other limits
    social_security_wage_base: Decimal = Field(..., gt=0)

    # Metadata
    source_document: str  # e.g., "IRS Notice 2024-80"
    publication_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    # Version control
    version: str = "1.0"
    supersedes_version: Optional[str] = None
    is_active: bool = True

    @validator('effective_date')
    def validate_effective_date(cls, v, values):
        if 'plan_year' in values:
            expected_year = values['plan_year']
            if v.year != expected_year:
                raise ValueError(f"Effective date year {v.year} must match plan year {expected_year}")
        return v

    @validator('annual_additions_limit')
    def validate_annual_additions_vs_deferral(cls, v, values):
        if 'employee_deferral_limit' in values:
            if v <= values['employee_deferral_limit']:
                raise ValueError("Annual additions limit must exceed employee deferral limit")
        return v

class LimitChangeEvent(BaseModel):
    event_id: str
    limit_type: LimitType
    plan_year: int
    previous_limit: Optional[Decimal]
    new_limit: Decimal
    effective_date: date
    change_reason: str
    source_document: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TrueUpCalculation(BaseModel):
    employee_id: str
    plan_id: str
    plan_year: int

    # Match calculation inputs
    employee_deferrals: Decimal  # Combined pre-tax + Roth + after-tax
    match_formula: Dict[str, Any]

    # Actual vs expected
    posted_match: Decimal
    expected_match: Decimal

    # True-up result
    true_up_amount: Decimal
    threshold_met: bool  # True if delta >= $5

    # Audit trail
    calculation_method: str = "formula_based_inference"
    calculation_details: Dict[str, Any] = Field(default_factory=dict)
    inferred_value: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @validator('true_up_amount')
    def validate_true_up_amount(cls, v, values):
        if 'expected_match' in values and 'posted_match' in values:
            delta = values['expected_match'] - values['posted_match']
            expected_true_up = max(delta, Decimal('0')) if delta >= Decimal('5') else Decimal('0')
            if abs(v - expected_true_up) > Decimal('0.01'):
                raise ValueError(f"True-up amount {v} doesn't match expected {expected_true_up}")
        return v
```

### Regulatory Limits Service
```python
class RegulatoryLimitsService:
    """Version-controlled service for IRS regulatory limits lookup and management"""

    def __init__(self, db_connection, cache_manager):
        self.db = db_connection
        self.cache = cache_manager
        self.cache_ttl = 3600  # 1 hour
        self._initialize_tables()

    def _initialize_tables(self):
        """Initialize regulatory limits storage tables"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS irs_limits (
                plan_year INTEGER NOT NULL,
                effective_date DATE NOT NULL,
                employee_deferral_limit DECIMAL(10,0) NOT NULL,
                catch_up_contribution_limit DECIMAL(10,0) NOT NULL,
                annual_additions_limit DECIMAL(10,0) NOT NULL,
                compensation_limit DECIMAL(10,0) NOT NULL,
                highly_compensated_threshold DECIMAL(10,0) NOT NULL,
                key_employee_threshold DECIMAL(10,0) NOT NULL,
                social_security_wage_base DECIMAL(10,0) NOT NULL,
                source_document VARCHAR NOT NULL,
                publication_date DATE,
                version VARCHAR NOT NULL,
                supersedes_version VARCHAR,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                PRIMARY KEY (plan_year, version),
                INDEX idx_plan_year_active (plan_year, is_active),
                INDEX idx_effective_date (effective_date)
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS limit_change_events (
                event_id VARCHAR PRIMARY KEY,
                limit_type VARCHAR NOT NULL,
                plan_year INTEGER NOT NULL,
                previous_limit DECIMAL(15,2),
                new_limit DECIMAL(15,2) NOT NULL,
                effective_date DATE NOT NULL,
                change_reason VARCHAR NOT NULL,
                source_document VARCHAR NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_plan_year (plan_year),
                INDEX idx_limit_type (limit_type)
            )
        """)

    def get_limits(
        self,
        plan_year: int,
        effective_date: Optional[date] = None,
        use_cache: bool = True
    ) -> IRSLimits:
        """Get IRS limits for specific plan year and date"""

        cache_key = f"irs_limits:{plan_year}:{effective_date or 'latest'}"

        if use_cache:
            cached_limits = self.cache.get(cache_key)
            if cached_limits:
                return IRSLimits(**cached_limits)

        # Query database
        query = """
            SELECT *
            FROM irs_limits
            WHERE plan_year = ? AND is_active = TRUE
        """
        params = [plan_year]

        if effective_date:
            query += " AND effective_date <= ?"
            params.append(effective_date)

        query += " ORDER BY effective_date DESC, version DESC LIMIT 1"

        result = self.db.execute(query, params).fetchone()

        if not result:
            raise ValueError(f"No IRS limits found for plan year {plan_year}")

        limits = IRSLimits(**dict(result))

        # Cache result
        if use_cache:
            self.cache.set(cache_key, limits.dict(), ttl=self.cache_ttl)

        return limits

    def get_limits_range(
        self,
        start_year: int,
        end_year: int
    ) -> List[IRSLimits]:
        """Get limits for multiple years for multi-year simulations"""

        limits_list = []
        for year in range(start_year, end_year + 1):
            try:
                limits = self.get_limits(year)
                limits_list.append(limits)
            except ValueError:
                # Year not found - could be future year
                continue

        return limits_list

    def ingest_limits_from_yaml(self, yaml_file_path: str) -> List[IRSLimits]:
        """Ingest IRS limits from YAML configuration file"""

        with open(yaml_file_path, 'r') as f:
            data = yaml.safe_load(f)

        ingested_limits = []

        for year_data in data.get('irs_limits', []):
            # Create IRSLimits object
            limits = IRSLimits(**year_data)

            # Check for existing limits
            existing = self._get_existing_limits(limits.plan_year)

            if existing:
                # Create new version
                limits.version = self._increment_version(existing.version)
                limits.supersedes_version = existing.version

                # Deactivate old version
                self._deactivate_limits(limits.plan_year, existing.version)

            # Insert new limits
            self._insert_limits(limits)

            # Track changes
            self._track_limit_changes(existing, limits)

            ingested_limits.append(limits)

        # Clear cache
        self._clear_limits_cache()

        return ingested_limits

    def ingest_limits_from_csv(self, csv_file_path: str) -> List[IRSLimits]:
        """Ingest IRS limits from CSV file"""

        ingested_limits = []

        with open(csv_file_path, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Convert string values to appropriate types
                limits_data = {
                    'plan_year': int(row['plan_year']),
                    'effective_date': date.fromisoformat(row['effective_date']),
                    'employee_deferral_limit': Decimal(row['employee_deferral_limit']),
                    'catch_up_contribution_limit': Decimal(row['catch_up_contribution_limit']),
                    'annual_additions_limit': Decimal(row['annual_additions_limit']),
                    'compensation_limit': Decimal(row['compensation_limit']),
                    'highly_compensated_threshold': Decimal(row['highly_compensated_threshold']),
                    'key_employee_threshold': Decimal(row['key_employee_threshold']),
                    'social_security_wage_base': Decimal(row['social_security_wage_base']),
                    'source_document': row['source_document']
                }

                if 'publication_date' in row and row['publication_date']:
                    limits_data['publication_date'] = date.fromisoformat(row['publication_date'])

                limits = IRSLimits(**limits_data)

                # Process same as YAML ingestion
                existing = self._get_existing_limits(limits.plan_year)

                if existing:
                    limits.version = self._increment_version(existing.version)
                    limits.supersedes_version = existing.version
                    self._deactivate_limits(limits.plan_year, existing.version)

                self._insert_limits(limits)
                self._track_limit_changes(existing, limits)

                ingested_limits.append(limits)

        self._clear_limits_cache()
        return ingested_limits

    def validate_contribution_against_limits(
        self,
        employee_id: str,
        plan_year: int,
        contribution_type: str,
        contribution_amount: Decimal,
        ytd_contributions: Dict[str, Decimal]
    ) -> Dict[str, Any]:
        """Validate contribution against applicable IRS limits"""

        limits = self.get_limits(plan_year)

        validation_result = {
            'is_valid': True,
            'violations': [],
            'warnings': [],
            'applicable_limits': {},
            'remaining_capacity': {}
        }

        # 402(g) validation for employee deferrals
        if contribution_type in ['employee_pre_tax', 'employee_roth']:
            current_deferrals = (
                ytd_contributions.get('employee_pre_tax', Decimal('0')) +
                ytd_contributions.get('employee_roth', Decimal('0'))
            )
            projected_deferrals = current_deferrals + contribution_amount

            if projected_deferrals > limits.employee_deferral_limit:
                validation_result['is_valid'] = False
                validation_result['violations'].append({
                    'limit_type': '402g',
                    'limit_value': float(limits.employee_deferral_limit),
                    'projected_amount': float(projected_deferrals),
                    'excess_amount': float(projected_deferrals - limits.employee_deferral_limit)
                })

            validation_result['applicable_limits']['402g'] = float(limits.employee_deferral_limit)
            validation_result['remaining_capacity']['402g'] = float(limits.employee_deferral_limit - current_deferrals)

        # 415(c) validation for all contributions
        total_contributions = sum(ytd_contributions.values()) + contribution_amount

        if total_contributions > limits.annual_additions_limit:
            validation_result['is_valid'] = False
            validation_result['violations'].append({
                'limit_type': '415c',
                'limit_value': float(limits.annual_additions_limit),
                'projected_amount': float(total_contributions),
                'excess_amount': float(total_contributions - limits.annual_additions_limit)
            })

        validation_result['applicable_limits']['415c'] = float(limits.annual_additions_limit)
        validation_result['remaining_capacity']['415c'] = float(limits.annual_additions_limit - sum(ytd_contributions.values()))

        return validation_result

    def _get_existing_limits(self, plan_year: int) -> Optional[IRSLimits]:
        """Get existing active limits for plan year"""
        query = """
            SELECT * FROM irs_limits
            WHERE plan_year = ? AND is_active = TRUE
            ORDER BY version DESC LIMIT 1
        """
        result = self.db.execute(query, [plan_year]).fetchone()
        return IRSLimits(**dict(result)) if result else None

    def _increment_version(self, current_version: str) -> str:
        """Increment version number"""
        try:
            major, minor = current_version.split('.')
            return f"{major}.{int(minor) + 1}"
        except:
            return "1.1"

    def _deactivate_limits(self, plan_year: int, version: str):
        """Deactivate previous version of limits"""
        self.db.execute(
            "UPDATE irs_limits SET is_active = FALSE WHERE plan_year = ? AND version = ?",
            [plan_year, version]
        )

    def _insert_limits(self, limits: IRSLimits):
        """Insert new limits into database"""
        query = """
            INSERT INTO irs_limits (
                plan_year, effective_date, employee_deferral_limit, catch_up_contribution_limit,
                annual_additions_limit, compensation_limit, highly_compensated_threshold,
                key_employee_threshold, social_security_wage_base, source_document,
                publication_date, version, supersedes_version, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        self.db.execute(query, [
            limits.plan_year, limits.effective_date, limits.employee_deferral_limit,
            limits.catch_up_contribution_limit, limits.annual_additions_limit,
            limits.compensation_limit, limits.highly_compensated_threshold,
            limits.key_employee_threshold, limits.social_security_wage_base,
            limits.source_document, limits.publication_date, limits.version,
            limits.supersedes_version, limits.is_active
        ])

    def _track_limit_changes(self, previous: Optional[IRSLimits], current: IRSLimits):
        """Track changes between limit versions"""
        if not previous:
            return

        # Compare each limit type
        limit_comparisons = [
            ('employee_deferral_limit', previous.employee_deferral_limit, current.employee_deferral_limit),
            ('catch_up_contribution_limit', previous.catch_up_contribution_limit, current.catch_up_contribution_limit),
            ('annual_additions_limit', previous.annual_additions_limit, current.annual_additions_limit),
            ('compensation_limit', previous.compensation_limit, current.compensation_limit),
            ('highly_compensated_threshold', previous.highly_compensated_threshold, current.highly_compensated_threshold)
        ]

        for limit_name, prev_value, curr_value in limit_comparisons:
            if prev_value != curr_value:
                change_event = LimitChangeEvent(
                    event_id=str(uuid.uuid4()),
                    limit_type=LimitType(limit_name),
                    plan_year=current.plan_year,
                    previous_limit=prev_value,
                    new_limit=curr_value,
                    effective_date=current.effective_date,
                    change_reason="irs_update",
                    source_document=current.source_document
                )

                self._insert_change_event(change_event)

    def _insert_change_event(self, event: LimitChangeEvent):
        """Insert limit change event"""
        query = """
            INSERT INTO limit_change_events (
                event_id, limit_type, plan_year, previous_limit, new_limit,
                effective_date, change_reason, source_document
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

        self.db.execute(query, [
            event.event_id, event.limit_type.value, event.plan_year,
            event.previous_limit, event.new_limit, event.effective_date,
            event.change_reason, event.source_document
        ])

    def _clear_limits_cache(self):
        """Clear cached limits data"""
        # Implementation would clear relevant cache keys
        pass
```

### Employer Match True-Up Calculator
```python
class EmployerMatchTrueUpCalculator:
    """Calculator for employer match true-up amounts during data ingestion"""

    def __init__(self, plan_service):
        self.plan_service = plan_service
        self.true_up_threshold = Decimal('5')  # $5 minimum threshold

    def calculate_true_up(
        self,
        employee_id: str,
        plan_id: str,
        plan_year: int,
        employee_deferrals: Decimal,
        posted_match: Decimal,
        match_formula: Optional[Dict[str, Any]] = None
    ) -> TrueUpCalculation:
        """Calculate employer match true-up amount"""

        # Get match formula if not provided
        if not match_formula:
            plan_config = self.plan_service.get_plan_config(plan_id, plan_year)
            match_formula = plan_config.get('matching', {})

        # Calculate expected match using formula
        expected_match = self._apply_match_formula(
            employee_deferrals=employee_deferrals,
            match_formula=match_formula
        )

        # Calculate true-up
        delta = expected_match - posted_match
        true_up_amount = max(delta, Decimal('0')) if delta >= self.true_up_threshold else Decimal('0')
        threshold_met = delta >= self.true_up_threshold

        # Build calculation details
        calculation_details = {
            'employee_deferrals': float(employee_deferrals),
            'match_formula': match_formula,
            'expected_match': float(expected_match),
            'posted_match': float(posted_match),
            'delta': float(delta),
            'threshold': float(self.true_up_threshold),
            'formula_type': match_formula.get('formula_type', 'tiered')
        }

        return TrueUpCalculation(
            employee_id=employee_id,
            plan_id=plan_id,
            plan_year=plan_year,
            employee_deferrals=employee_deferrals,
            match_formula=match_formula,
            posted_match=posted_match,
            expected_match=expected_match,
            true_up_amount=true_up_amount,
            threshold_met=threshold_met,
            calculation_details=calculation_details
        )

    def _apply_match_formula(
        self,
        employee_deferrals: Decimal,
        match_formula: Dict[str, Any]
    ) -> Decimal:
        """Apply match formula to calculate expected match"""

        formula_type = match_formula.get('formula_type', 'tiered')

        if formula_type == 'tiered':
            return self._calculate_tiered_match(employee_deferrals, match_formula)
        elif formula_type == 'flat_percentage':
            return self._calculate_flat_percentage_match(employee_deferrals, match_formula)
        elif formula_type == 'dollar_for_dollar':
            return self._calculate_dollar_for_dollar_match(employee_deferrals, match_formula)
        else:
            raise ValueError(f"Unknown match formula type: {formula_type}")

    def _calculate_tiered_match(
        self,
        employee_deferrals: Decimal,
        match_formula: Dict[str, Any]
    ) -> Decimal:
        """Calculate match using tiered formula (e.g., 100% on first 3%, 50% on next 2%)"""

        tiers = match_formula.get('tiers', [])
        if not tiers:
            return Decimal('0')

        total_match = Decimal('0')
        remaining_deferrals = employee_deferrals
        previous_tier_max = Decimal('0')

        for tier in tiers:
            tier_max = Decimal(str(tier['employee_max']))
            match_rate = Decimal(str(tier['match_rate']))

            # Calculate tier width
            tier_width = tier_max - previous_tier_max

            # Calculate deferrals eligible for this tier
            tier_deferrals = min(remaining_deferrals, tier_width)

            # Calculate match for this tier
            tier_match = tier_deferrals * match_rate
            total_match += tier_match

            # Update for next tier
            remaining_deferrals -= tier_deferrals
            previous_tier_max = tier_max

            # Stop if no more deferrals to match
            if remaining_deferrals <= 0:
                break

        return total_match

    def _calculate_flat_percentage_match(
        self,
        employee_deferrals: Decimal,
        match_formula: Dict[str, Any]
    ) -> Decimal:
        """Calculate match using flat percentage (e.g., 50% of all deferrals up to 6%)"""

        match_rate = Decimal(str(match_formula.get('match_rate', 0)))
        max_match_percentage = Decimal(str(match_formula.get('max_match_percentage', 1)))

        # Apply maximum
        eligible_deferrals = min(employee_deferrals, max_match_percentage)

        return eligible_deferrals * match_rate

    def _calculate_dollar_for_dollar_match(
        self,
        employee_deferrals: Decimal,
        match_formula: Dict[str, Any]
    ) -> Decimal:
        """Calculate dollar-for-dollar match up to limit"""

        max_match_amount = Decimal(str(match_formula.get('max_match_amount', 0)))

        return min(employee_deferrals, max_match_amount)

    def process_batch_true_up_calculations(
        self,
        participant_data: List[Dict[str, Any]]
    ) -> List[TrueUpCalculation]:
        """Process true-up calculations for batch of participants"""

        results = []

        for participant in participant_data:
            try:
                true_up = self.calculate_true_up(
                    employee_id=participant['employee_id'],
                    plan_id=participant['plan_id'],
                    plan_year=participant['plan_year'],
                    employee_deferrals=Decimal(str(participant['employee_deferrals'])),
                    posted_match=Decimal(str(participant['posted_match'])),
                    match_formula=participant.get('match_formula')
                )
                results.append(true_up)

            except Exception as e:
                # Log error but continue processing
                print(f"Error calculating true-up for {participant['employee_id']}: {e}")

        return results

    def validate_against_golden_dataset(
        self,
        golden_dataset_path: str,
        calculated_results: List[TrueUpCalculation]
    ) -> Dict[str, Any]:
        """Validate calculated true-ups against golden benchmark dataset"""

        # Load golden dataset
        golden_data = self._load_golden_dataset(golden_dataset_path)

        # Create lookup map
        calculated_map = {
            (calc.employee_id, calc.plan_year): calc.true_up_amount
            for calc in calculated_results
        }

        validation_results = {
            'total_records': len(golden_data),
            'matched_records': 0,
            'discrepancies': [],
            'max_variance': Decimal('0'),
            'is_benchmark_match': True
        }

        for golden_record in golden_data:
            employee_id = golden_record['employee_id']
            plan_year = golden_record['plan_year']
            expected_true_up = Decimal(str(golden_record['expected_true_up']))

            calculated_true_up = calculated_map.get((employee_id, plan_year))

            if calculated_true_up is None:
                validation_results['discrepancies'].append({
                    'employee_id': employee_id,
                    'plan_year': plan_year,
                    'error': 'Missing calculation result'
                })
                validation_results['is_benchmark_match'] = False
                continue

            variance = abs(calculated_true_up - expected_true_up)
            validation_results['max_variance'] = max(validation_results['max_variance'], variance)

            if variance > Decimal('0.01'):  # More than 1 cent difference
                validation_results['discrepancies'].append({
                    'employee_id': employee_id,
                    'plan_year': plan_year,
                    'expected': float(expected_true_up),
                    'calculated': float(calculated_true_up),
                    'variance': float(variance)
                })
                validation_results['is_benchmark_match'] = False
            else:
                validation_results['matched_records'] += 1

        return validation_results

    def _load_golden_dataset(self, dataset_path: str) -> List[Dict[str, Any]]:
        """Load golden dataset from CSV or JSON file"""
        # Implementation would load and parse golden dataset
        return []
```

### Enhanced Data Ingestion Pipeline
```python
class EnhancedDataIngestionPipeline:
    """Enhanced pipeline supporting true-up calculation during ingestion"""

    def __init__(self, true_up_calculator, validation_service):
        self.true_up_calculator = true_up_calculator
        self.validation_service = validation_service

    def ingest_participant_data(
        self,
        raw_data_path: str,
        plan_config: Dict[str, Any],
        output_path: str
    ) -> Dict[str, Any]:
        """Ingest participant data with true-up calculation"""

        ingestion_results = {
            'total_records': 0,
            'processed_records': 0,
            'true_up_inferred': 0,
            'validation_errors': [],
            'processing_time_ms': 0
        }

        start_time = datetime.utcnow()

        # Load raw data
        raw_data = self._load_raw_data(raw_data_path)
        ingestion_results['total_records'] = len(raw_data)

        processed_data = []

        for record in raw_data:
            try:
                # Calculate true-up if not provided
                if record.get('er_match_true_up') is None:
                    true_up = self.true_up_calculator.calculate_true_up(
                        employee_id=record['employee_id'],
                        plan_id=record['plan_id'],
                        plan_year=record['plan_year'],
                        employee_deferrals=Decimal(str(record.get('employee_deferrals', 0))),
                        posted_match=Decimal(str(record.get('er_match', 0))),
                        match_formula=plan_config.get('matching')
                    )

                    record['er_match_true_up'] = float(true_up.true_up_amount)
                    record['_true_up_inferred'] = True
                    ingestion_results['true_up_inferred'] += 1
                else:
                    record['_true_up_inferred'] = False

                # Validate record
                validation_result = self.validation_service.validate_record(record)

                if validation_result['is_valid']:
                    processed_data.append(record)
                    ingestion_results['processed_records'] += 1
                else:
                    ingestion_results['validation_errors'].append({
                        'employee_id': record['employee_id'],
                        'errors': validation_result['errors']
                    })

            except Exception as e:
                ingestion_results['validation_errors'].append({
                    'employee_id': record.get('employee_id', 'unknown'),
                    'errors': [str(e)]
                })

        # Write processed data
        self._write_processed_data(processed_data, output_path)

        # Calculate processing time
        end_time = datetime.utcnow()
        ingestion_results['processing_time_ms'] = int((end_time - start_time).total_seconds() * 1000)

        return ingestion_results

    def _load_raw_data(self, data_path: str) -> List[Dict[str, Any]]:
        """Load raw participant data from file"""
        # Implementation would load CSV/JSON/Parquet data
        return []

    def _write_processed_data(self, data: List[Dict[str, Any]], output_path: str):
        """Write processed data to output location"""
        # Implementation would write data in partitioned format
        pass
```

## Implementation Tasks

### Phase 1: Regulatory Limits Service
- [ ] **Implement IRS limits models** with comprehensive validation
- [ ] **Create regulatory limits service** with version control
- [ ] **Build YAML/CSV ingestion** with change tracking
- [ ] **Add comprehensive unit tests** for all limit scenarios

### Phase 2: True-Up Calculation
- [ ] **Implement true-up calculator** with multiple formula types
- [ ] **Create batch processing** for efficient calculation
- [ ] **Build golden dataset validation** framework
- [ ] **Add regression testing** against benchmarks

### Phase 3: Enhanced Ingestion
- [ ] **Create enhanced ingestion pipeline** with true-up calculation
- [ ] **Implement data validation** and error handling
- [ ] **Build audit trail** for inference vs. provided values
- [ ] **Add performance optimization** for large datasets

## Dependencies

- **S074**: Plan Configuration Schema (for match formulas)
- **S080**: IRS Compliance Engine (uses regulatory limits)
- **Golden dataset**: Benchmark data for validation
- **Plan configuration service**: Match formula definitions

## Success Metrics

### Accuracy Requirements
- [ ] **True-up calculation**: 100% match with golden benchmark (zero variance)
- [ ] **Limit lookup**: <10ms response time for validation calls
- [ ] **Version control**: Complete audit trail for all limit changes
- [ ] **Regression testing**: Zero false positives/negatives vs benchmark

### Performance Requirements
- [ ] **Batch true-up**: 100,000 calculations in <5 minutes
- [ ] **Limits service**: 10,000 lookups per second
- [ ] **Ingestion pipeline**: 1M records in <30 minutes
- [ ] **Memory efficiency**: <2GB for 100K participant calculations

## Definition of Done

- [ ] **Complete regulatory limits service** with version control
- [ ] **Automated true-up calculation** matching golden benchmarks
- [ ] **Enhanced ingestion pipeline** with validation framework
- [ ] **Comprehensive testing** including regression tests
- [ ] **Performance benchmarks met** for enterprise scale
- [ ] **Golden dataset validation** with zero variance tolerance
- [ ] **Documentation complete** with calculation formulas
- [ ] **Integration verified** with compliance enforcement engine
