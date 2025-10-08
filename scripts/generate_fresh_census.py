#!/usr/bin/env python3
"""
Generate a completely fresh census_preprocessed.parquet with different characteristics.

This creates a NEW dataset with:
- 7,500 employees (vs 5,000 original)
- Different salary distribution (wider range)
- Different age demographics (younger workforce)
- Different hire date patterns (bimodal: old-timers + recent hires)
- Different deferral behavior
- Edge cases to flush out bugs
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

# Set different random seed than original
np.random.seed(99999)  # Completely different from any previous seed
random.seed(99999)

def generate_employee_id(index):
    """Generate employee ID with different format."""
    # Use 2025 prefix to differentiate from 2024 original
    return f"EMP_2025_{index:07d}"

def generate_ssn(index):
    """Generate SSN with different starting number."""
    return f"SSN-200{index:06d}"  # Start at 200000001 instead of 100000001

def generate_birth_date():
    """Generate birth dates with younger demographic profile."""
    # Bimodal distribution: 60% young (25-40), 40% experienced (40-60)
    if random.random() < 0.6:
        # Younger employees (born 1985-2000)
        years_ago = random.randint(25, 40)
    else:
        # Experienced employees (born 1965-1985)
        years_ago = random.randint(40, 60)

    birth_date = datetime(2025, 1, 1) - timedelta(days=years_ago * 365 + random.randint(0, 365))
    return birth_date.strftime('%Y-%m-%d')

def generate_hire_date():
    """Generate hire dates with bimodal pattern: tenured + recent."""
    # 30% hired 2005-2015 (tenured), 70% hired 2020-2024 (recent)
    if random.random() < 0.3:
        # Tenured employees (10-20 years)
        start_date = datetime(2005, 1, 1)
        end_date = datetime(2015, 12, 31)
    else:
        # Recent hires (0-5 years)
        start_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 12, 31)

    days_between = (end_date - start_date).days
    random_days = random.randint(0, days_between)
    hire_date = start_date + timedelta(days=random_days)
    return hire_date.strftime('%Y-%m-%d')

def generate_termination_date(hire_date_str):
    """Generate termination dates for ~10% of employees."""
    if random.random() > 0.10:  # 90% active, 10% terminated
        return None

    hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d')
    # Termination between hire and 2024-12-31
    max_days = (datetime(2024, 12, 31) - hire_date).days

    # Only terminate if they've been employed at least 30 days
    if max_days < 30:
        return None

    days_employed = random.randint(30, max_days)
    term_date = hire_date + timedelta(days=days_employed)
    return term_date.strftime('%Y-%m-%d')

def generate_compensation():
    """Generate compensation with wider, more realistic range."""
    # Use lognormal distribution for realistic salary spread
    # Mean: $85k, wider range: $40k - $500k (vs $50k - $350k original)
    base_salary = np.random.lognormal(mean=11.3, sigma=0.6)

    # Clamp to realistic range
    salary = max(40000, min(500000, base_salary))

    # Round to nearest $100
    return round(salary / 100) * 100

def generate_deferral_rate():
    """Generate deferral rates with realistic distribution."""
    # 15% non-participants (0%)
    if random.random() < 0.15:
        return 0.0

    # 25% at auto-enrollment default (6%)
    if random.random() < 0.30:  # 0.30 of remaining 85%
        return 0.06

    # 60% distributed across other rates
    # Peaks at round numbers: 3%, 5%, 8%, 10%, 15%
    choice = random.random()
    if choice < 0.20:
        return 0.03
    elif choice < 0.35:
        return 0.05
    elif choice < 0.50:
        return 0.08
    elif choice < 0.65:
        return 0.10
    elif choice < 0.80:
        return 0.15
    else:
        # Random between 1% and 20%
        return round(random.uniform(0.01, 0.20), 4)

def calculate_capped_compensation(gross_comp):
    """Apply IRS 401(k) compensation cap."""
    IRS_LIMIT_2025 = 350000  # Updated for 2025
    return min(gross_comp, IRS_LIMIT_2025)

def calculate_employee_contribution(capped_comp, deferral_rate):
    """Calculate employee contributions."""
    total_contribution = capped_comp * deferral_rate

    # Split between pre-tax, Roth, after-tax (realistic distribution)
    if deferral_rate == 0:
        return 0.0, 0.0, 0.0, 0.0

    # 70% pre-tax, 25% Roth, 5% after-tax
    pre_tax = total_contribution * 0.70
    roth = total_contribution * 0.25
    after_tax = total_contribution * 0.05

    return total_contribution, pre_tax, roth, after_tax

def calculate_employer_contributions(capped_comp, employee_contrib):
    """Calculate employer contributions (core + match)."""
    # Core contribution: 3% of capped compensation for all employees
    core_contrib = capped_comp * 0.03

    # Match: 50% of employee contributions up to 6% of compensation
    # Max match = 3% of compensation (when employee contributes 6%+)
    match_limit = capped_comp * 0.06 * 0.50  # 3% of comp
    match_contrib = min(employee_contrib * 0.50, match_limit)

    return core_contrib, match_contrib

def calculate_eligibility_entry_date(hire_date_str):
    """Calculate eligibility entry date (first of month after 30 days)."""
    hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d')
    eligibility_date = hire_date + timedelta(days=30)

    # Move to first of next month
    if eligibility_date.day != 1:
        if eligibility_date.month == 12:
            eligibility_date = datetime(eligibility_date.year + 1, 1, 1)
        else:
            eligibility_date = datetime(eligibility_date.year, eligibility_date.month + 1, 1)

    return eligibility_date.strftime('%Y-%m-%d')

def main():
    """Generate fresh census dataset."""
    print("Generating fresh census dataset with 7,500 employees...")

    employees = []

    for i in range(1, 7501):  # 7,500 employees
        if i % 1000 == 0:
            print(f"  Generated {i} employees...")

        employee_id = generate_employee_id(i)
        ssn = generate_ssn(i)
        birth_date = generate_birth_date()
        hire_date = generate_hire_date()
        termination_date = generate_termination_date(hire_date)
        gross_comp = generate_compensation()
        capped_comp = calculate_capped_compensation(gross_comp)
        deferral_rate = generate_deferral_rate()

        total_contrib, pre_tax, roth, after_tax = calculate_employee_contribution(
            capped_comp, deferral_rate
        )
        core_contrib, match_contrib = calculate_employer_contributions(
            capped_comp, total_contrib
        )

        eligibility_entry_date = calculate_eligibility_entry_date(hire_date)
        active = termination_date is None

        employees.append({
            'employee_id': employee_id,
            'employee_ssn': ssn,
            'employee_birth_date': birth_date,
            'employee_hire_date': hire_date,
            'employee_termination_date': termination_date,
            'employee_gross_compensation': gross_comp,
            'employee_capped_compensation': capped_comp,
            'employee_deferral_rate': deferral_rate,
            'employee_contribution': total_contrib,
            'pre_tax_contribution': pre_tax,
            'roth_contribution': roth,
            'after_tax_contribution': after_tax,
            'employer_core_contribution': core_contrib,
            'employer_match_contribution': match_contrib,
            'eligibility_entry_date': eligibility_entry_date,
            'active': active
        })

    # Create DataFrame
    df = pd.DataFrame(employees)

    # Add edge cases to flush out bugs
    print("\nAdding edge cases to find bugs...")

    # Edge case 1: Very recent hire (hired yesterday)
    edge_case_1 = {
        'employee_id': 'EMP_2025_9999991',
        'employee_ssn': 'SSN-299999991',
        'employee_birth_date': '1990-06-15',
        'employee_hire_date': '2024-12-31',  # Very recent
        'employee_termination_date': None,
        'employee_gross_compensation': 75000.0,
        'employee_capped_compensation': 75000.0,
        'employee_deferral_rate': 0.06,
        'employee_contribution': 4500.0,
        'pre_tax_contribution': 3150.0,
        'roth_contribution': 1125.0,
        'after_tax_contribution': 225.0,
        'employer_core_contribution': 2250.0,
        'employer_match_contribution': 2250.0,
        'eligibility_entry_date': '2025-02-01',
        'active': True
    }

    # Edge case 2: Employee at max compensation
    edge_case_2 = {
        'employee_id': 'EMP_2025_9999992',
        'employee_ssn': 'SSN-299999992',
        'employee_birth_date': '1970-03-20',
        'employee_hire_date': '2005-01-15',
        'employee_termination_date': None,
        'employee_gross_compensation': 500000.0,  # Above IRS cap
        'employee_capped_compensation': 350000.0,  # Capped
        'employee_deferral_rate': 0.15,
        'employee_contribution': 52500.0,
        'pre_tax_contribution': 36750.0,
        'roth_contribution': 13125.0,
        'after_tax_contribution': 2625.0,
        'employer_core_contribution': 10500.0,
        'employer_match_contribution': 10500.0,
        'eligibility_entry_date': '2005-03-01',
        'active': True
    }

    # Edge case 3: Zero deferral rate
    edge_case_3 = {
        'employee_id': 'EMP_2025_9999993',
        'employee_ssn': 'SSN-299999993',
        'employee_birth_date': '1995-11-10',
        'employee_hire_date': '2023-06-01',
        'employee_termination_date': None,
        'employee_gross_compensation': 60000.0,
        'employee_capped_compensation': 60000.0,
        'employee_deferral_rate': 0.0,  # Non-participant
        'employee_contribution': 0.0,
        'pre_tax_contribution': 0.0,
        'roth_contribution': 0.0,
        'after_tax_contribution': 0.0,
        'employer_core_contribution': 1800.0,  # Still gets core
        'employer_match_contribution': 0.0,  # No match
        'eligibility_entry_date': '2023-07-01',
        'active': True
    }

    # Edge case 4: Terminated employee (mid-year)
    edge_case_4 = {
        'employee_id': 'EMP_2025_9999994',
        'employee_ssn': 'SSN-299999994',
        'employee_birth_date': '1988-08-25',
        'employee_hire_date': '2020-03-15',
        'employee_termination_date': '2024-06-30',  # Mid-year termination
        'employee_gross_compensation': 80000.0,
        'employee_capped_compensation': 80000.0,
        'employee_deferral_rate': 0.10,
        'employee_contribution': 8000.0,
        'pre_tax_contribution': 5600.0,
        'roth_contribution': 2000.0,
        'after_tax_contribution': 400.0,
        'employer_core_contribution': 2400.0,
        'employer_match_contribution': 2400.0,
        'eligibility_entry_date': '2020-05-01',
        'active': False
    }

    # Edge case 5: Minimum compensation
    edge_case_5 = {
        'employee_id': 'EMP_2025_9999995',
        'employee_ssn': 'SSN-299999995',
        'employee_birth_date': '2000-01-01',
        'employee_hire_date': '2024-09-01',
        'employee_termination_date': None,
        'employee_gross_compensation': 40000.0,  # Minimum
        'employee_capped_compensation': 40000.0,
        'employee_deferral_rate': 0.03,
        'employee_contribution': 1200.0,
        'pre_tax_contribution': 840.0,
        'roth_contribution': 300.0,
        'after_tax_contribution': 60.0,
        'employer_core_contribution': 1200.0,
        'employer_match_contribution': 600.0,
        'eligibility_entry_date': '2024-10-01',
        'active': True
    }

    # Add edge cases
    edge_cases_df = pd.DataFrame([
        edge_case_1, edge_case_2, edge_case_3, edge_case_4, edge_case_5
    ])
    df = pd.concat([df, edge_cases_df], ignore_index=True)

    # Save to parquet
    output_path = 'data/census_preprocessed.parquet'
    df.to_parquet(output_path, index=False)

    print(f"\n✅ Fresh census dataset created: {output_path}")
    print(f"   Total employees: {len(df):,}")
    print(f"   Active employees: {df['active'].sum():,}")
    print(f"   Terminated employees: {(~df['active']).sum():,}")
    print(f"\nDataset characteristics:")
    print(f"   Salary range: ${df['employee_gross_compensation'].min():,.0f} - ${df['employee_gross_compensation'].max():,.0f}")
    print(f"   Deferral rate range: {df['employee_deferral_rate'].min():.1%} - {df['employee_deferral_rate'].max():.1%}")
    print(f"   Non-participants (0% deferral): {(df['employee_deferral_rate'] == 0).sum():,}")
    print(f"   Edge cases included: 5 (recent hire, max comp, zero deferral, terminated, min comp)")

    # Show sample
    print("\nSample of new census data:")
    print(df[['employee_id', 'employee_hire_date', 'employee_gross_compensation',
              'employee_deferral_rate', 'active']].head(10))

    print("\nEdge cases:")
    print(df[df['employee_id'].str.startswith('EMP_2025_9999')][
        ['employee_id', 'employee_hire_date', 'employee_termination_date',
         'employee_gross_compensation', 'employee_deferral_rate']
    ])

if __name__ == '__main__':
    main()
