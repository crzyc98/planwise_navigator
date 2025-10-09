# ADR E077-A: Growth Equation & Rounding Policy

**Status**: Approved
**Date**: 2025-10-09
**Epic**: E077 - Bulletproof Workforce Growth Accuracy
**Decision Makers**: Workforce Simulation Team

---

## Context

Workforce growth calculations previously used 5+ sequential `ROUND()` operations, causing cumulative rounding errors that produced growth variance from -4% to +40% on real census data. We need a mathematically rigorous rounding policy that guarantees exact integer reconciliation.

**Problem**: The growth equation `Start + Hires - ExpTerms - NHTerms = End` must balance exactly (integer-for-integer), but multiple independent rounding operations prevent this.

---

## Decision

### **Single-Rounding Algebraic Solver**

We enforce **exactly one rounding operation** (for hires) and compute all other values to force the growth equation to balance exactly.

#### **Rounding Rules** (applies to ALL growth calculations):

| Value | Rounding Function | Rationale |
|-------|-------------------|-----------|
| **Target Ending Workforce** | `ROUND()` | Banker's rounding for unbiased target |
| **Experienced Terminations** | `FLOOR()` | Conservative (don't over-terminate existing workforce) |
| **Total Hires Needed** | `CEILING()` | Aggressive (ensure capacity to hit target) |
| **Implied NH Terminations** | **Computed as residual** | Forces exact balance (no rounding) |

#### **Exact Algorithm**:

```
Given:
  start = starting_workforce_count (integer)
  growth_rate (decimal, e.g., 0.03)
  exp_term_rate (decimal, e.g., 0.25)
  nh_term_rate (decimal, e.g., 0.40)

Step 1: Calculate target ending (banker's rounding)
  target_ending = ROUND(start × (1 + growth_rate))

Step 2: Calculate experienced terminations (conservative)
  exp_terms = FLOOR(start × exp_term_rate)
  survivors = start - exp_terms

Step 3: Calculate net hires needed
  net_from_hires = target_ending - survivors

Step 4: Solve for hires (aggressive rounding)
  GUARD: ASSERT (1 - nh_term_rate) > 0.01  -- Feasibility check
  hires_exact = net_from_hires / (1 - nh_term_rate)
  hires = CEILING(hires_exact)  -- ONLY rounding point for hires

Step 5: Compute implied NH terminations (exact, no rounding)
  implied_nh_terms = hires - net_from_hires
  GUARD: ASSERT implied_nh_terms >= 0 AND implied_nh_terms <= hires

Step 6: Validate exact balance
  ASSERT start + hires - exp_terms - implied_nh_terms == target_ending
  -- Must be EXACT (error = 0) or FAIL
```

---

### **Negative/Zero Growth Branch (RIF Scenario)**

When `net_from_hires <= 0` (negative growth or RIF):

```
If net_from_hires <= 0:
  hires = 0  -- No hiring during RIF
  additional_rif_terms = ABS(net_from_hires)  -- Additional terminations needed
  total_exp_terms = exp_terms + additional_rif_terms  -- Total RIF pool
  implied_nh_terms = 0  -- No new hires to terminate

  Validate: start - total_exp_terms == target_ending

  Selection: Use deterministic RIF ranking (hash + employee_id tiebreaker)
             for additional_rif_terms beyond natural attrition
```

---

### **Feasibility Guards** (FAIL simulation if violated):

1. **NH Term Rate Feasibility**: `(1 - nh_term_rate) > 0.01`
   - Prevents divide-by-zero or infeasible scenarios (≥99% NH termination rate)
   - Error message: "New hire termination rate must be <99%"

2. **Hire Ratio Feasibility**: `hires <= start × max_hire_ratio`
   - Default: `max_hire_ratio = 0.50` (50% of starting workforce)
   - Prevents unrealistic hiring scenarios (e.g., doubling workforce in 1 year)
   - Error message: "Hiring target exceeds 50% of starting workforce - check growth/term rates"

3. **Implied NH Terms Validity**: `implied_nh_terms >= 0 AND implied_nh_terms <= hires`
   - Prevents negative terminations or terminating more than hired
   - Error message: "Implied NH terminations invalid - check growth equation parameters"

4. **Growth Rate Bounds**: `ABS(growth_rate) <= 1.0`
   - Prevents ±100%+ growth rates (double or zero workforce)
   - Error message: "Growth rate must be between -100% and +100%"

---

### **DuckDB Implementation Notes**

#### **Banker's Rounding (ROUND)**:
- DuckDB uses IEEE 754 "round half to even" (banker's rounding)
- `ROUND(2.5) = 2`, `ROUND(3.5) = 4`
- Reduces bias in repeated rounding operations

#### **Decimal Precision**:
```sql
-- Use DECIMAL for exact math (avoid float drift)
CAST(start * (1 + growth_rate) AS DECIMAL(18,4))  -- 4 decimal places
```

#### **Integer Coercion**:
```sql
-- Cast to INTEGER after rounding functions
CAST(ROUND(target_ending_exact) AS INTEGER)
CAST(FLOOR(exp_terms_exact) AS INTEGER)
CAST(CEILING(hires_exact) AS INTEGER)
```

---

### **Polars Implementation Notes**

```python
import polars as pl
from decimal import Decimal, ROUND_HALF_EVEN
import numpy as np

def calculate_exact_needs(start: int, growth_rate: Decimal,
                          exp_term_rate: Decimal, nh_term_rate: Decimal) -> dict:
    """Algebraic solver with single-rounding policy."""

    # Use Decimal for exact arithmetic (no float drift)
    start_dec = Decimal(start)

    # Guard 1: NH term rate feasibility
    if (1 - nh_term_rate) <= Decimal('0.01'):
        raise ValueError("NH termination rate must be <99%")

    # Guard 2: Growth rate bounds
    if abs(growth_rate) > Decimal('1.0'):
        raise ValueError("Growth rate must be between -100% and +100%")

    # Step 1: Target ending (banker's rounding)
    target_ending_exact = start_dec * (1 + growth_rate)
    target_ending = int(target_ending_exact.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))

    # Step 2: Experienced terminations (floor)
    exp_terms_exact = start_dec * exp_term_rate
    exp_terms = int(np.floor(float(exp_terms_exact)))
    survivors = start - exp_terms

    # Step 3: Net hires needed
    net_from_hires = target_ending - survivors

    # Step 4: Hires (ceiling)
    if net_from_hires <= 0:
        # RIF branch
        hires = 0
        additional_rif_terms = abs(net_from_hires)
        total_exp_terms = exp_terms + additional_rif_terms
        implied_nh_terms = 0

        # Validate RIF balance
        assert start - total_exp_terms == target_ending, "RIF balance failed"
    else:
        # Growth branch
        hires_exact = Decimal(net_from_hires) / (1 - nh_term_rate)
        hires = int(np.ceil(float(hires_exact)))

        # Guard 3: Hire ratio feasibility (default 50%)
        max_hire_ratio = Decimal('0.50')
        if hires > float(start_dec * max_hire_ratio):
            raise ValueError(f"Hiring target ({hires}) exceeds 50% of starting workforce ({start})")

        # Step 5: Implied NH terms (residual, no rounding)
        implied_nh_terms = hires - net_from_hires

        # Guard 4: Implied NH terms validity
        if implied_nh_terms < 0 or implied_nh_terms > hires:
            raise ValueError(f"Implied NH terminations invalid: {implied_nh_terms}")

        total_exp_terms = exp_terms

    # Step 6: Validate exact balance (EXACT or FAIL)
    calculated_ending = start + hires - total_exp_terms - implied_nh_terms
    if calculated_ending != target_ending:
        raise AssertionError(
            f"Growth equation balance failed: "
            f"{start} + {hires} - {total_exp_terms} - {implied_nh_terms} = {calculated_ending} "
            f"!= {target_ending} (error: {calculated_ending - target_ending})"
        )

    return {
        'starting_workforce': start,
        'target_ending_workforce': target_ending,
        'total_hires_needed': hires,
        'expected_experienced_terminations': total_exp_terms,
        'implied_new_hire_terminations': implied_nh_terms,
        'reconciliation_error': 0  # Guaranteed by assertion
    }
```

---

## Consequences

### **Positive**:
- ✅ **Mathematical guarantee**: Growth equation balances exactly (error = 0)
- ✅ **Deterministic**: Same inputs → identical outputs (no floating point variance)
- ✅ **Transparent**: Single rounding point makes debugging trivial
- ✅ **RIF support**: Handles negative growth scenarios explicitly
- ✅ **Fail-fast**: Feasibility guards catch invalid scenarios immediately

### **Negative**:
- ⚠️ **Learning curve**: Team must understand residual calculation for `implied_nh_terms`
- ⚠️ **Testing overhead**: Must validate all edge cases (negative growth, zero hires, etc.)

### **Mitigations**:
- Document algorithm in code comments with worked examples
- Create comprehensive test suite covering all branches and edge cases
- Add diagnostic logging showing intermediate calculations

---

## Alternatives Considered

### **Alternative 1: Round All Values Independently**
- **Rejected**: Creates rounding cascades (5+ sequential ROUND operations)
- **Problem**: Impossible to guarantee exact balance with independent rounding
- **Example**: Cumulative error of ±5-10 employees over 5 years

### **Alternative 2: Iterative Adjustment**
- **Rejected**: Compute all rounded values, then adjust smallest residual to force balance
- **Problem**: Non-deterministic (depends on which value gets adjusted)
- **Complexity**: Requires complex tie-breaking logic

### **Alternative 3: Exact Decimal Throughout**
- **Rejected**: Never round, use Decimal(18,4) for all values including headcounts
- **Problem**: Headcount must be integer (can't have 7,210.3 employees)
- **Impractical**: Final snapshot requires integer employee counts

---

## Validation

### **Unit Test Cases** (must pass before deployment):

```python
def test_positive_growth():
    result = calculate_exact_needs(
        start=7000, growth_rate=Decimal('0.03'),
        exp_term_rate=Decimal('0.25'), nh_term_rate=Decimal('0.40')
    )
    assert result['reconciliation_error'] == 0
    assert result['target_ending_workforce'] == 7210
    assert result['total_hires_needed'] == 3267

def test_zero_growth():
    result = calculate_exact_needs(
        start=7000, growth_rate=Decimal('0.00'),
        exp_term_rate=Decimal('0.12'), nh_term_rate=Decimal('0.25')
    )
    assert result['reconciliation_error'] == 0
    assert result['target_ending_workforce'] == 7000

def test_negative_growth_rif():
    result = calculate_exact_needs(
        start=7000, growth_rate=Decimal('-0.10'),
        exp_term_rate=Decimal('0.12'), nh_term_rate=Decimal('0.40')
    )
    assert result['total_hires_needed'] == 0
    assert result['implied_new_hire_terminations'] == 0
    assert result['target_ending_workforce'] == 6300

def test_feasibility_guard_nh_term_rate():
    with pytest.raises(ValueError, match="must be <99%"):
        calculate_exact_needs(
            start=7000, growth_rate=Decimal('0.03'),
            exp_term_rate=Decimal('0.25'), nh_term_rate=Decimal('0.99')
        )

def test_feasibility_guard_hire_ratio():
    with pytest.raises(ValueError, match="exceeds 50%"):
        calculate_exact_needs(
            start=1000, growth_rate=Decimal('0.60'),  # Requires >50% hiring
            exp_term_rate=Decimal('0.05'), nh_term_rate=Decimal('0.10')
        )
```

---

## References

- **Epic E077**: Bulletproof Workforce Growth Accuracy
- **ADR E077-B**: Apportionment & Quotas
- **ADR E077-C**: Determinism & State Integrity
- **IEEE 754**: Floating-point arithmetic standard (banker's rounding)
- **Largest-Remainder Method**: Quota allocation algorithm (Hare-Niemeyer method)

---

**Approved By**: Workforce Simulation Team
**Implementation Start**: 2025-10-09
**Review Date**: After 30 days in production
