# Story S072-05: Loan & Investment Events

**Epic**: E021-A - DC Plan Event Schema Foundation
**Story Points**: 3
**Priority**: High
**Sprint**: 2
**Owner**: DC Plan Team

## Story

**As a** plan administrator
**I want** loan and investment management events for participant self-direction
**So that** I can track loan origination/repayment and investment elections with complete audit trail

## Business Context

This story implements participant self-direction events for loan management and investment elections. These events handle participant-initiated activities including plan loans (origination and repayment) and investment fund allocation changes. While less critical than core plan events, these features are essential for full participant experience and plan administration.

## Acceptance Criteria

### Loan Management Events
- [ ] **LoanInitiatedPayload**: Participant loan origination with compliance checks
- [ ] **LoanRepaymentPayload**: Loan payment processing with balance tracking
- [ ] **Loan type distinction** between general purpose and primary residence loans
- [ ] **Interest rate and term tracking** with regulatory limit enforcement

### Investment Management Events
- [ ] **InvestmentElectionPayload**: Fund allocation changes with validation
- [ ] **Election scope tracking** (future contributions vs. existing balance reallocation)
- [ ] **Source of change tracking** (participant, advisor, administrator, QDIA)
- [ ] **Fund allocation validation** ensuring allocations sum to 100%

### Participant Services Features
- [ ] **Rollover processing** with source plan type tracking
- [ ] **Model portfolio support** for target-date and risk-based investing
- [ ] **Transaction correlation** with custodian systems
- [ ] **Complete audit trail** for all participant-directed activities

## Technical Specifications

### Loan & Investment Event Payloads

```python
from typing import Literal, Optional, Dict
from pydantic import BaseModel, Field, field_validator
from datetime import date
from decimal import Decimal

class LoanInitiatedPayload(BaseModel):
    """Participant loan origination with compliance tracking"""

    event_type: Literal["loan_initiated"] = "loan_initiated"
    plan_id: str = Field(..., min_length=1)
    loan_id: str = Field(..., min_length=1)
    principal_amount: Decimal = Field(..., gt=0, decimal_places=6)
    interest_rate: Decimal = Field(..., gt=0, decimal_places=4)
    term_months: int = Field(..., gt=0, le=120)  # Max 10 years per IRS
    origination_date: date

    # Loan type affects compliance rules and fees
    loan_type: Literal["general_purpose", "primary_residence"] = "general_purpose"
    origination_fee: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=6)

class LoanRepaymentPayload(BaseModel):
    """Loan payment processing with balance tracking"""

    event_type: Literal["loan_repayment"] = "loan_repayment"
    plan_id: str = Field(..., min_length=1)
    loan_id: str = Field(..., min_length=1)
    principal_paid: Decimal = Field(..., ge=0, decimal_places=6)
    interest_paid: Decimal = Field(..., ge=0, decimal_places=6)
    outstanding_balance: Decimal = Field(..., ge=0, decimal_places=6)
    remaining_term_months: int = Field(..., ge=0)

class RolloverPayload(BaseModel):
    """External plan money movement tracking"""

    event_type: Literal["rollover"] = "rollover"
    plan_id: str = Field(..., min_length=1)
    source_plan_type: Literal[
        "401k", "403b", "457b", "ira_traditional", "ira_roth"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    is_roth_rollover: bool = False
    rollover_source: str = Field(..., min_length=1)  # Source plan identifier

class InvestmentElectionPayload(BaseModel):
    """Fund allocation changes with comprehensive tracking"""

    event_type: Literal["investment_election"] = "investment_election"
    plan_id: str = Field(..., min_length=1)
    election_effective_date: date

    # Election scope and source tracking for complete audit trail
    election_scope: Literal[
        "future_contributions",      # Only affects new contributions
        "rebalance_existing_balance", # Only affects current balance
        "full_reallocation"          # Affects both existing and future
    ] = "future_contributions"

    source_of_change: Literal[
        "participant",         # Participant-directed change
        "advisor",            # Investment advisor recommendation
        "administrator",      # Plan administrator adjustment
        "system_default_qdia" # Qualified Default Investment Alternative
    ] = "participant"

    model_portfolio_id: Optional[str] = None  # If plan uses model portfolios
    transaction_id: Optional[str] = None      # For reconciliation with custodian

    fund_allocations: Dict[str, Decimal]  # fund_id -> allocation_percentage

    @field_validator('fund_allocations')
    def validate_allocations_sum_to_one(cls, v):
        """Ensure fund allocations sum to exactly 1.0 (100%)"""
        total = sum(v.values())
        if abs(total - Decimal('1.0')) > Decimal('0.0001'):
            raise ValueError(f'Fund allocations must sum to 1.0, got {total}')
        return v

    @field_validator('fund_allocations')
    def validate_allocation_values(cls, v):
        """Ensure all allocation percentages are between 0 and 1"""
        for fund_id, allocation in v.items():
            if allocation < 0 or allocation > 1:
                raise ValueError(f'Allocation for {fund_id} must be between 0 and 1, got {allocation}')
        return v
```

### Loan & Investment Event Factory

```python
class LoanInvestmentEventFactory(EventFactory):
    """Factory for creating loan and investment events"""

    @staticmethod
    def create_loan_initiated_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        loan_id: str,
        principal_amount: Decimal,
        interest_rate: Decimal,
        term_months: int,
        origination_date: date,
        loan_type: str = "general_purpose",
        origination_fee: Decimal = Decimal('0')
    ) -> SimulationEvent:
        """Create loan initiation event with compliance validation"""

        # Validate loan amount against available balance (would integrate with balance service)
        if principal_amount <= 0:
            raise ValueError("Loan principal must be greater than zero")

        # Validate term based on loan type
        max_term = 120 if loan_type == "primary_residence" else 60  # 5 years for general purpose
        if term_months > max_term:
            raise ValueError(f"Term of {term_months} months exceeds maximum of {max_term} for {loan_type} loan")

        payload = LoanInitiatedPayload(
            plan_id=plan_id,
            loan_id=loan_id,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            origination_date=origination_date,
            loan_type=loan_type,
            origination_fee=origination_fee
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=origination_date,
            source_system="participant_services",
            payload=payload
        )

    @staticmethod
    def create_investment_election_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        election_effective_date: date,
        fund_allocations: Dict[str, Decimal],
        election_scope: str = "future_contributions",
        source_of_change: str = "participant",
        model_portfolio_id: Optional[str] = None,
        transaction_id: Optional[str] = None
    ) -> SimulationEvent:
        """Create investment election event with allocation validation"""

        # Validate fund allocations sum to 1.0
        total_allocation = sum(fund_allocations.values())
        if abs(total_allocation - Decimal('1.0')) > Decimal('0.0001'):\n            raise ValueError(f\"Fund allocations must sum to 1.0, got {total_allocation}\")\n        \n        payload = InvestmentElectionPayload(\n            plan_id=plan_id,\n            election_effective_date=election_effective_date,\n            election_scope=election_scope,\n            source_of_change=source_of_change,\n            model_portfolio_id=model_portfolio_id,\n            transaction_id=transaction_id,\n            fund_allocations=fund_allocations\n        )\n        \n        return SimulationEvent(\n            employee_id=employee_id,\n            scenario_id=scenario_id,\n            plan_design_id=plan_design_id,\n            effective_date=election_effective_date,\n            source_system=\"participant_services\",\n            payload=payload\n        )\n    \n    @staticmethod\n    def create_rollover_event(\n        employee_id: str,\n        plan_id: str,\n        scenario_id: str,\n        plan_design_id: str,\n        source_plan_type: str,\n        amount: Decimal,\n        rollover_source: str,\n        effective_date: date,\n        is_roth_rollover: bool = False\n    ) -> SimulationEvent:\n        \"\"\"Create rollover event for external plan transfers\"\"\"\n        \n        payload = RolloverPayload(\n            plan_id=plan_id,\n            source_plan_type=source_plan_type,\n            amount=amount,\n            is_roth_rollover=is_roth_rollover,\n            rollover_source=rollover_source\n        )\n        \n        return SimulationEvent(\n            employee_id=employee_id,\n            scenario_id=scenario_id,\n            plan_design_id=plan_design_id,\n            effective_date=effective_date,\n            source_system=\"participant_services\",\n            payload=payload\n        )\n```\n\n## Implementation Tasks\n\n### Phase 1: Loan Event Implementation\n- [ ] **Create LoanInitiatedPayload** with compliance validation\n- [ ] **Create LoanRepaymentPayload** with balance tracking\n- [ ] **Add loan type distinction** (general_purpose vs primary_residence)\n- [ ] **Implement term validation** based on loan type and IRS limits\n\n### Phase 2: Investment Event Implementation\n- [ ] **Create InvestmentElectionPayload** with comprehensive tracking\n- [ ] **Add fund allocation validation** with sum-to-one checking\n- [ ] **Implement election scope tracking** for different rebalancing types\n- [ ] **Add source of change tracking** for audit compliance\n\n### Phase 3: Rollover & Integration\n- [ ] **Create RolloverPayload** with source plan tracking\n- [ ] **Extend SimulationEvent discriminated union** with 4 new payloads\n- [ ] **Create LoanInvestmentEventFactory** with validation methods\n- [ ] **Test integration** with existing event infrastructure\n\n### Phase 4: Advanced Features\n- [ ] **Add model portfolio support** for target-date investing\n- [ ] **Implement transaction correlation** with custodian systems\n- [ ] **Add loan compliance checks** for maximum amounts and terms\n- [ ] **Create comprehensive validation** for all participant-directed activities\n\n## Dependencies\n\n### Story Dependencies\n- **S072-01**: Core Event Model & Pydantic v2 Architecture (blocking)\n\n### Domain Dependencies\n- **Plan configuration**: Available loan options and investment funds\n- **Balance service**: Current account balances for loan limit validation\n- **Fund master**: Available investment options and fund metadata\n- **Custodian integration**: Transaction correlation and reconciliation\n\n## Success Metrics\n\n### Loan Management\n- [ ] **Loan origination** with compliance rule enforcement\n- [ ] **Repayment tracking** with accurate balance calculation\n- [ ] **Term validation** based on loan type and regulatory limits\n- [ ] **Interest calculation** support for ongoing loan management\n\n### Investment Management\n- [ ] **Fund allocation validation** with 100% sum requirement\n- [ ] **Election scope handling** for different rebalancing scenarios\n- [ ] **Model portfolio support** for simplified investing\n- [ ] **Transaction correlation** with external systems\n\n## Testing Strategy\n\n### Unit Tests\n- [ ] **Loan event creation** with valid/invalid parameters\n- [ ] **Investment allocation validation** with edge cases\n- [ ] **Fund allocation sum checking** with floating-point precision\n- [ ] **Field validation** for all required fields and constraints\n\n### Business Logic Tests\n- [ ] **Loan term validation** by loan type\n- [ ] **Investment election scope** handling\n- [ ] **Rollover processing** with source plan validation\n- [ ] **Model portfolio integration** with allocation overrides\n\n### Integration Tests\n- [ ] **Participant services workflow** end-to-end\n- [ ] **Loan lifecycle management** from origination to payoff\n- [ ] **Investment election processing** with custodian correlation\n- [ ] **Event correlation** between related participant activities\n\n## Regulatory Compliance\n\n### Loan Regulations\n- [ ] **IRS loan limits** (50% of vested balance, $50,000 maximum)\n- [ ] **Term limits** (5 years general purpose, 10 years primary residence)\n- [ ] **Interest rate requirements** (prime + 1% typical)\n- [ ] **Default handling** with deemed distribution consequences\n\n### Investment Regulations\n- [ ] **QDIA compliance** for default investment alternatives\n- [ ] **Fund monitoring** for prohibited investments\n- [ ] **Participant direction** documentation requirements\n- [ ] **Fiduciary compliance** for investment option oversight\n\n## Definition of Done\n\n- [ ] **All 4 loan/investment payloads** implemented and tested\n- [ ] **SimulationEvent discriminated union** extended with new payloads\n- [ ] **LoanInvestmentEventFactory** provides creation methods for all types\n- [ ] **Fund allocation validation** working correctly with edge cases\n- [ ] **Loan compliance checks** enforcing IRS regulations\n- [ ] **Integration tests passing** for all participant service scenarios\n- [ ] **Documentation complete** with participant workflow examples\n- [ ] **Code review approved** with participant services team validation\n\n## Notes\n\nThis story completes the participant self-direction capabilities of the event schema. The loan and investment events are less frequent than core plan events but are essential for full participant experience. The validation logic includes important compliance checks that prevent participants from taking invalid loans or making invalid investment elections.
