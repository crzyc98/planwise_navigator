# Story S077: Account State Snapshots

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 8
**Priority**: Medium

## Story

**As a** system architect
**I want** optimized account state reconstruction
**So that** account queries perform efficiently at enterprise scale

## Business Context

This story implements an efficient snapshot-based architecture for participant account states, enabling sub-second queries across 100K+ participants while maintaining the event-sourced audit trail. The system balances between pure event sourcing and performance requirements through strategic snapshotting.

## Acceptance Criteria

### Core Snapshot Features
- [ ] **Participant account state snapshots** for performance optimization
- [ ] **Incremental snapshot updates** from latest processed events
- [ ] **Version control** for state reconstruction validation
- [ ] **Sub-second account balance queries** for 100K+ participants
- [ ] **Integration with real-time contribution processing**

### Performance Requirements
- [ ] **Query latency**: <100ms for single account lookup
- [ ] **Batch queries**: <1 second for 1,000 accounts
- [ ] **Snapshot generation**: <5 minutes for 100K participants
- [ ] **Memory efficiency**: <4GB for snapshot processing
- [ ] **Storage optimization**: Compressed snapshots with efficient indexing

## Technical Specifications

### Account State Model
```python
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from datetime import date, datetime
from decimal import Decimal
import uuid

class AccountSnapshot(BaseModel):
    """Point-in-time snapshot of participant account state"""
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str
    plan_id: str
    scenario_id: str = "baseline"
    plan_design_id: str = "standard"
    snapshot_date: date
    snapshot_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Balance components
    balances: Dict[str, Decimal] = Field(default_factory=dict)
    vested_balances: Dict[str, Decimal] = Field(default_factory=dict)

    # Aggregate balances
    total_balance: Decimal = Decimal('0')
    vested_balance: Decimal = Decimal('0')
    unvested_balance: Decimal = Decimal('0')

    # Vesting information
    years_of_service: float = 0.0
    vesting_percentages: Dict[str, float] = Field(default_factory=dict)

    # Event tracking
    last_processed_event_id: str
    last_event_timestamp: datetime
    event_count: int = 0

    # Snapshot metadata
    version: int = 1
    is_current: bool = True
    checksum: Optional[str] = None

    @validator('total_balance', always=True)
    def calculate_total_balance(cls, v, values):
        if 'balances' in values:
            return sum(values['balances'].values())
        return v

    @validator('vested_balance', always=True)
    def calculate_vested_balance(cls, v, values):
        if 'vested_balances' in values:
            return sum(values['vested_balances'].values())
        return v

    @validator('unvested_balance', always=True)
    def calculate_unvested_balance(cls, v, values):
        if 'total_balance' in values and 'vested_balance' in values:
            return values['total_balance'] - values['vested_balance']
        return v

class SnapshotDelta(BaseModel):
    """Represents changes between snapshots"""
    from_snapshot_id: str
    to_snapshot_id: str
    employee_id: str
    plan_id: str

    # Balance changes
    balance_changes: Dict[str, Decimal]
    vested_balance_changes: Dict[str, Decimal]

    # Events applied
    events_applied: List[str]  # Event IDs
    event_count: int

    # Timing
    delta_start_date: date
    delta_end_date: date
    processing_time_ms: int
```

### Snapshot Management Engine
```python
class SnapshotManager:
    """Manages account snapshot creation and updates"""

    def __init__(self, event_store, snapshot_store, vesting_engine):
        self.event_store = event_store
        self.snapshot_store = snapshot_store
        self.vesting_engine = vesting_engine
        self.snapshot_interval = 1000  # Create snapshot every N events

    def create_initial_snapshot(
        self,
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        as_of_date: date
    ) -> AccountSnapshot:
        """Create initial snapshot for new participant"""
        snapshot = AccountSnapshot(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            snapshot_date=as_of_date,
            last_processed_event_id="INITIAL",
            last_event_timestamp=datetime.utcnow()
        )

        self.snapshot_store.save(snapshot)
        return snapshot

    def update_snapshot(
        self,
        employee_id: str,
        plan_id: str,
        events: List[Dict[str, Any]],
        force_new: bool = False
    ) -> AccountSnapshot:
        """Update account snapshot with new events"""
        # Get current snapshot
        current_snapshot = self.snapshot_store.get_latest(
            employee_id=employee_id,
            plan_id=plan_id
        )

        if not current_snapshot:
            raise ValueError(f"No snapshot found for employee {employee_id}")

        # Determine if we need a new snapshot or can update existing
        total_events = current_snapshot.event_count + len(events)
        create_new_snapshot = force_new or (total_events % self.snapshot_interval == 0)

        if create_new_snapshot:
            # Create new snapshot
            new_snapshot = self._create_new_snapshot(current_snapshot, events)
            self.snapshot_store.save(new_snapshot)

            # Mark old snapshot as not current
            current_snapshot.is_current = False
            self.snapshot_store.update(current_snapshot)

            return new_snapshot
        else:
            # Update existing snapshot
            self._apply_events_to_snapshot(current_snapshot, events)
            self.snapshot_store.update(current_snapshot)
            return current_snapshot

    def _apply_events_to_snapshot(
        self,
        snapshot: AccountSnapshot,
        events: List[Dict[str, Any]]
    ) -> None:
        """Apply events to update snapshot state"""
        for event in events:
            event_type = event.get('event_type')
            payload = event.get('payload', {})

            if event_type == 'contribution':
                self._apply_contribution(snapshot, payload)
            elif event_type == 'forfeiture':
                self._apply_forfeiture(snapshot, payload)
            elif event_type == 'distribution':
                self._apply_distribution(snapshot, payload)
            elif event_type == 'vesting':
                self._apply_vesting_update(snapshot, payload)

            # Update tracking
            snapshot.last_processed_event_id = event['event_id']
            snapshot.last_event_timestamp = event['created_at']
            snapshot.event_count += 1

    def _apply_contribution(
        self,
        snapshot: AccountSnapshot,
        payload: Dict[str, Any]
    ) -> None:
        """Apply contribution event to snapshot"""
        source = payload['source']
        amount = Decimal(str(payload['amount']))

        # Update balance
        current_balance = snapshot.balances.get(source, Decimal('0'))
        snapshot.balances[source] = current_balance + amount

        # Update vested balance based on source
        if source.startswith('employee_'):
            # Employee contributions are always 100% vested
            current_vested = snapshot.vested_balances.get(source, Decimal('0'))
            snapshot.vested_balances[source] = current_vested + amount
        else:
            # Employer contributions use vesting schedule
            vesting_pct = snapshot.vesting_percentages.get(source, 0.0)
            current_vested = snapshot.vested_balances.get(source, Decimal('0'))
            vested_amount = amount * Decimal(str(vesting_pct))
            snapshot.vested_balances[source] = current_vested + vested_amount

    def _apply_forfeiture(
        self,
        snapshot: AccountSnapshot,
        payload: Dict[str, Any]
    ) -> None:
        """Apply forfeiture event to snapshot"""
        source = payload['contribution_source']
        amount = Decimal(str(payload['forfeited_amount']))

        # Reduce balances
        if source in snapshot.balances:
            snapshot.balances[source] = max(
                Decimal('0'),
                snapshot.balances[source] - amount
            )
            # Forfeitures only affect unvested amounts
            # Vested balance remains unchanged

    def _create_new_snapshot(
        self,
        base_snapshot: AccountSnapshot,
        events: List[Dict[str, Any]]
    ) -> AccountSnapshot:
        """Create new snapshot from base snapshot and events"""
        # Clone base snapshot
        new_snapshot = AccountSnapshot(
            employee_id=base_snapshot.employee_id,
            plan_id=base_snapshot.plan_id,
            scenario_id=base_snapshot.scenario_id,
            plan_design_id=base_snapshot.plan_design_id,
            snapshot_date=date.today(),
            balances=base_snapshot.balances.copy(),
            vested_balances=base_snapshot.vested_balances.copy(),
            years_of_service=base_snapshot.years_of_service,
            vesting_percentages=base_snapshot.vesting_percentages.copy(),
            last_processed_event_id=base_snapshot.last_processed_event_id,
            last_event_timestamp=base_snapshot.last_event_timestamp,
            event_count=base_snapshot.event_count,
            version=base_snapshot.version + 1
        )

        # Apply new events
        self._apply_events_to_snapshot(new_snapshot, events)

        # Calculate checksum for validation
        new_snapshot.checksum = self._calculate_checksum(new_snapshot)

        return new_snapshot

    def _calculate_checksum(self, snapshot: AccountSnapshot) -> str:
        """Calculate checksum for snapshot validation"""
        import hashlib

        # Create deterministic string representation
        checksum_data = f"{snapshot.employee_id}:{snapshot.plan_id}:"
        checksum_data += f"{snapshot.total_balance}:{snapshot.vested_balance}:"
        checksum_data += f"{snapshot.last_processed_event_id}"

        return hashlib.sha256(checksum_data.encode()).hexdigest()
```

### Snapshot Query Service
```python
class SnapshotQueryService:
    """Provides efficient querying of account states"""

    def __init__(self, snapshot_store, cache_manager):
        self.snapshot_store = snapshot_store
        self.cache = cache_manager
        self.cache_ttl = 300  # 5 minutes

    def get_account_balance(
        self,
        employee_id: str,
        plan_id: str,
        as_of_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Get account balance as of specific date"""
        cache_key = f"balance:{employee_id}:{plan_id}:{as_of_date or 'current'}"

        # Check cache
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result

        # Get snapshot
        if as_of_date:
            snapshot = self.snapshot_store.get_as_of_date(
                employee_id=employee_id,
                plan_id=plan_id,
                as_of_date=as_of_date
            )
        else:
            snapshot = self.snapshot_store.get_latest(
                employee_id=employee_id,
                plan_id=plan_id
            )

        if not snapshot:
            return {
                'employee_id': employee_id,
                'plan_id': plan_id,
                'total_balance': 0,
                'vested_balance': 0,
                'balances': {}
            }

        result = {
            'employee_id': employee_id,
            'plan_id': plan_id,
            'as_of_date': snapshot.snapshot_date,
            'total_balance': float(snapshot.total_balance),
            'vested_balance': float(snapshot.vested_balance),
            'unvested_balance': float(snapshot.unvested_balance),
            'balances': {k: float(v) for k, v in snapshot.balances.items()},
            'vested_balances': {k: float(v) for k, v in snapshot.vested_balances.items()},
            'last_updated': snapshot.last_event_timestamp
        }

        # Cache result
        self.cache.set(cache_key, result, ttl=self.cache_ttl)

        return result

    def get_batch_balances(
        self,
        employee_ids: List[str],
        plan_id: str,
        as_of_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """Get balances for multiple employees efficiently"""
        results = []

        # Use batch query for efficiency
        snapshots = self.snapshot_store.get_batch(
            employee_ids=employee_ids,
            plan_id=plan_id,
            as_of_date=as_of_date
        )

        # Create lookup map
        snapshot_map = {s.employee_id: s for s in snapshots}

        for employee_id in employee_ids:
            if employee_id in snapshot_map:
                snapshot = snapshot_map[employee_id]
                results.append({
                    'employee_id': employee_id,
                    'total_balance': float(snapshot.total_balance),
                    'vested_balance': float(snapshot.vested_balance)
                })
            else:
                results.append({
                    'employee_id': employee_id,
                    'total_balance': 0,
                    'vested_balance': 0
                })

        return results

    def validate_snapshot_integrity(
        self,
        employee_id: str,
        plan_id: str
    ) -> Dict[str, Any]:
        """Validate snapshot against event stream"""
        snapshot = self.snapshot_store.get_latest(
            employee_id=employee_id,
            plan_id=plan_id
        )

        if not snapshot:
            return {'valid': False, 'error': 'No snapshot found'}

        # Recalculate from events
        events = self.event_store.get_events(
            employee_id=employee_id,
            plan_id=plan_id,
            up_to_event_id=snapshot.last_processed_event_id
        )

        recalculated_balances = self._recalculate_from_events(events)

        # Compare
        discrepancies = []
        for source, balance in snapshot.balances.items():
            recalc_balance = recalculated_balances.get(source, Decimal('0'))
            if abs(balance - recalc_balance) > Decimal('0.01'):
                discrepancies.append({
                    'source': source,
                    'snapshot_balance': float(balance),
                    'recalculated_balance': float(recalc_balance),
                    'difference': float(balance - recalc_balance)
                })

        return {
            'valid': len(discrepancies) == 0,
            'snapshot_id': snapshot.snapshot_id,
            'checksum_valid': snapshot.checksum == self._calculate_checksum(snapshot),
            'discrepancies': discrepancies
        }
```

### Snapshot Storage Layer
```python
class SnapshotStore:
    """Manages snapshot persistence with DuckDB"""

    def __init__(self, db_connection):
        self.db = db_connection
        self._create_tables()

    def _create_tables(self):
        """Create snapshot storage tables"""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                snapshot_id VARCHAR PRIMARY KEY,
                employee_id VARCHAR NOT NULL,
                plan_id VARCHAR NOT NULL,
                scenario_id VARCHAR NOT NULL,
                plan_design_id VARCHAR NOT NULL,
                snapshot_date DATE NOT NULL,
                snapshot_timestamp TIMESTAMP NOT NULL,
                balances JSON NOT NULL,
                vested_balances JSON NOT NULL,
                total_balance DECIMAL(15,2) NOT NULL,
                vested_balance DECIMAL(15,2) NOT NULL,
                unvested_balance DECIMAL(15,2) NOT NULL,
                years_of_service DECIMAL(6,4),
                vesting_percentages JSON,
                last_processed_event_id VARCHAR NOT NULL,
                last_event_timestamp TIMESTAMP NOT NULL,
                event_count INTEGER NOT NULL,
                version INTEGER NOT NULL,
                is_current BOOLEAN NOT NULL,
                checksum VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_employee_plan (employee_id, plan_id),
                INDEX idx_scenario (scenario_id, plan_design_id),
                INDEX idx_current (is_current),
                INDEX idx_snapshot_date (snapshot_date)
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS snapshot_deltas (
                delta_id VARCHAR PRIMARY KEY,
                from_snapshot_id VARCHAR NOT NULL,
                to_snapshot_id VARCHAR NOT NULL,
                employee_id VARCHAR NOT NULL,
                plan_id VARCHAR NOT NULL,
                balance_changes JSON NOT NULL,
                vested_balance_changes JSON NOT NULL,
                events_applied JSON NOT NULL,
                event_count INTEGER NOT NULL,
                delta_start_date DATE NOT NULL,
                delta_end_date DATE NOT NULL,
                processing_time_ms INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_snapshots (from_snapshot_id, to_snapshot_id),
                INDEX idx_employee (employee_id, plan_id)
            )
        """)
```

### dbt Models for Snapshots
```sql
-- fct_account_snapshots.sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'plan_id', 'scenario_id', 'plan_design_id', 'snapshot_date'],
    on_schema_change='fail',
    contract={'enforced': true},
    tags=['critical', 'dc_plan', 'snapshots'],
    indexes=[
        {'columns': ['employee_id', 'plan_id'], 'type': 'hash'},
        {'columns': ['is_current'], 'type': 'btree'},
        {'columns': ['snapshot_date'], 'type': 'btree'}
    ]
) }}

WITH latest_events AS (
    SELECT
        employee_id,
        plan_id,
        scenario_id,
        plan_design_id,
        MAX(created_at) as last_event_timestamp,
        COUNT(*) as event_count
    FROM {{ ref('fct_retirement_events') }}
    WHERE event_type IN ('contribution', 'forfeiture', 'distribution')
    {% if is_incremental() %}
        AND created_at > (SELECT MAX(last_event_timestamp) FROM {{ this }})
    {% endif %}
    GROUP BY employee_id, plan_id, scenario_id, plan_design_id
),
balance_aggregation AS (
    SELECT
        re.employee_id,
        re.plan_id,
        re.scenario_id,
        re.plan_design_id,
        re.contribution_source,
        SUM(
            CASE
                WHEN re.event_type = 'contribution' THEN re.contribution_amount
                WHEN re.event_type = 'forfeiture' THEN -re.contribution_amount
                WHEN re.event_type = 'distribution' THEN -re.contribution_amount
                ELSE 0
            END
        ) as source_balance
    FROM {{ ref('fct_retirement_events') }} re
    GROUP BY re.employee_id, re.plan_id, re.scenario_id, re.plan_design_id, re.contribution_source
),
vesting_data AS (
    SELECT
        vc.employee_id,
        vc.vested_percentage,
        vc.years_of_service
    FROM {{ ref('int_vesting_calculation') }} vc
),
snapshot_calculation AS (
    SELECT
        ba.employee_id,
        ba.plan_id,
        ba.scenario_id,
        ba.plan_design_id,
        CURRENT_DATE as snapshot_date,
        CURRENT_TIMESTAMP as snapshot_timestamp,
        -- Aggregate balances by source
        JSON_OBJECT(
            ba.contribution_source,
            ba.source_balance
        ) as balances,
        -- Calculate vested balances
        JSON_OBJECT(
            ba.contribution_source,
            CASE
                WHEN ba.contribution_source LIKE 'employee_%' THEN ba.source_balance
                ELSE ba.source_balance * COALESCE(vd.vested_percentage, 0)
            END
        ) as vested_balances,
        -- Total balances
        SUM(ba.source_balance) OVER (PARTITION BY ba.employee_id, ba.plan_id) as total_balance,
        SUM(
            CASE
                WHEN ba.contribution_source LIKE 'employee_%' THEN ba.source_balance
                ELSE ba.source_balance * COALESCE(vd.vested_percentage, 0)
            END
        ) OVER (PARTITION BY ba.employee_id, ba.plan_id) as vested_balance,
        vd.years_of_service,
        vd.vested_percentage,
        le.last_event_timestamp,
        le.event_count
    FROM balance_aggregation ba
    JOIN latest_events le ON ba.employee_id = le.employee_id AND ba.plan_id = le.plan_id
    LEFT JOIN vesting_data vd ON ba.employee_id = vd.employee_id
)
SELECT
    employee_id,
    plan_id,
    scenario_id,
    plan_design_id,
    snapshot_date,
    snapshot_timestamp,
    balances,
    vested_balances,
    total_balance,
    vested_balance,
    total_balance - vested_balance as unvested_balance,
    years_of_service,
    vested_percentage as default_vesting_percentage,
    last_event_timestamp,
    event_count,
    TRUE as is_current,
    1 as version
FROM snapshot_calculation
```

## Implementation Tasks

### Phase 1: Core Snapshot Infrastructure
- [ ] **Implement account snapshot model** with validation
- [ ] **Create snapshot manager** for creation and updates
- [ ] **Build snapshot storage layer** with DuckDB integration
- [ ] **Add checksum validation** for data integrity

### Phase 2: Query Optimization
- [ ] **Implement query service** with caching
- [ ] **Create batch query methods** for efficiency
- [ ] **Build snapshot validation** against event stream
- [ ] **Add performance monitoring** and metrics

### Phase 3: Integration and Optimization
- [ ] **Create dbt models** for snapshot generation
- [ ] **Implement incremental updates** from event stream
- [ ] **Add compression** for storage optimization
- [ ] **Build snapshot archival** for historical data

## Dependencies

- **S072**: Event Schema (provides event structure)
- **S076**: Vesting Management (provides vesting calculations)
- **Event processing pipeline**: Source of truth for account states
- **DuckDB**: Storage layer for snapshots

## Success Metrics

### Performance Requirements
- [ ] **Single account query**: <100ms response time
- [ ] **Batch query (1,000 accounts)**: <1 second
- [ ] **Snapshot generation**: <5 minutes for 100K participants
- [ ] **Storage efficiency**: <50MB per 10K participants

### Data Integrity Requirements
- [ ] **Checksum validation**: 100% accuracy
- [ ] **Event reconstruction**: Zero discrepancies
- [ ] **Version tracking**: Complete audit trail
- [ ] **Recovery capability**: <5 minutes to rebuild from events

## Definition of Done

- [ ] **Complete snapshot system** with efficient storage
- [ ] **Query service** meeting performance requirements
- [ ] **Validation framework** ensuring data integrity
- [ ] **Incremental updates** from event stream
- [ ] **Comprehensive testing** including performance tests
- [ ] **Monitoring and metrics** for production operations
- [ ] **Documentation** including architecture diagrams
- [ ] **Integration verified** with event processing pipeline
