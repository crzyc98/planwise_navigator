import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import pyarrow as pa
import pyarrow.parquet as pq
import sys
import os

# Add project root to path for importing UnifiedIDGenerator
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from orchestrator_mvp.core.id_generator import UnifiedIDGenerator


def generate_mock_workforce_parquet(
    num_employees: int = 5000,
    output_path: str = "mock_census_data.parquet",
    base_year: int = 2024,  # The year the "census" data represents
    random_seed: int = 42,  # NEW: Add seed parameter for deterministic generation
    target_experienced_termination_rate: float = 0.13,
    target_net_new_hire_rate: float = 0.16,  # This will influence the *initial* state, not the simulation
    # Compensation ranges for different "levels" (approximate)
    comp_ranges={
        1: (50000, 70000),
        2: (65000, 90000),
        3: (85000, 120000),
        4: (110000, 180000),
        5: (170000, 350000),
    },
):
    """
    Generates a mock Parquet file for workforce census data using unified ID generation.

    Args:
        num_employees (int): The target number of employees to generate.
        output_path (str): The file path to save the Parquet file.
        base_year (int): The year for which the initial census data is valid.
        random_seed (int): Random seed for deterministic, reproducible generation.
        target_experienced_termination_rate (float): Roughly what percentage of
                                                     employees might be "terminated" in the initial data.
        target_net_new_hire_rate (float): Roughly what percentage of
                                         employees might be "new hires" in the initial data (for hire dates).
        comp_ranges (dict): Dictionary mapping mock levels to (min_comp, max_comp).
    """

    print(f"Generating mock workforce data for {num_employees} employees...")
    print(f"Using random seed: {random_seed} for deterministic generation")

    # Initialize unified ID generator and set global random seed
    id_generator = UnifiedIDGenerator(random_seed, base_year)
    random.seed(random_seed)
    np.random.seed(random_seed)

    employees = []
    current_employee_id = 1

    # Simulate levels based on a distribution
    # More entry/mid-level, fewer senior
    level_distribution = {
        1: 0.35,  # Level 1
        2: 0.30,  # Level 2
        3: 0.20,  # Level 3
        4: 0.10,  # Level 4
        5: 0.05,  # Level 5
    }
    levels = random.choices(
        list(level_distribution.keys()),
        weights=list(level_distribution.values()),
        k=num_employees,
    )

    for i in range(num_employees):
        # Generate unified baseline employee ID using seeded approach
        emp_id = id_generator.generate_employee_id(
            sequence=current_employee_id,
            is_baseline=True  # This is baseline workforce data
        )
        # Use seeded SSN generation for consistency
        ssn = f"SSN-{100000000 + current_employee_id:09d}"

        # Age distribution (skewed slightly younger, then broader middle)
        age = int(np.random.normal(38, 10))  # Mean 38, Std Dev 10
        age = max(22, min(65, age))  # Clamp between 22 and 65

        # Birth date relative to base_year
        birth_date = datetime(
            base_year - age, random.randint(1, 12), random.randint(1, 28)
        )

        # Tenure distribution (skewed towards shorter tenure)
        tenure = int(np.random.exponential(5))  # Mean 5 years
        tenure = max(0, min(30, tenure))  # Clamp between 0 and 30

        # Hire date relative to base_year and tenure
        hire_date = datetime(
            base_year - tenure, random.randint(1, 12), random.randint(1, 28)
        )
        # Ensure hire_date is not in the future relative to base_year's end
        hire_date = min(hire_date, datetime(base_year, 12, 31))

        # Assign level and compensation
        emp_level = levels[i]
        min_comp, max_comp = comp_ranges.get(emp_level, (50000, 100000))
        # Add some variance around the mean for compensation
        gross_compensation = (
            round(random.uniform(min_comp, max_comp) / 100) * 100
        )  # Round to nearest 100

        # Termination status
        is_terminated = False
        termination_date = None
        if random.random() < target_experienced_termination_rate:
            is_terminated = True
            # Termination date within the base_year, but after hire date
            term_date_start = max(hire_date, datetime(base_year, 1, 1))
            term_date_end = datetime(base_year, 12, 31)
            # Ensure term_date_start is not after term_date_end
            if term_date_start <= term_date_end:
                time_delta = term_date_end - term_date_start
                days_to_add = (
                    random.randint(0, time_delta.days) if time_delta.days > 0 else 0
                )
                termination_date = term_date_start + timedelta(days=days_to_add)
            else:  # If hire date is in future of base_year, no termination for this year
                is_terminated = False

        # Generate DC plan fields with realistic values
        # First determine if employee participates (80% participation rate)
        participates = random.random() > 0.2

        if participates:
            # Generate total deferral rate between 3% and 15%
            total_deferral_rate = random.uniform(0.03, 0.15)
            employee_contribution = gross_compensation * total_deferral_rate

            # Break down employee contribution into three types
            # Most common: pre-tax, then Roth, then after-tax
            pre_tax_pct = random.uniform(0.6, 1.0)  # 60-100% pre-tax
            remaining_pct = 1.0 - pre_tax_pct

            if remaining_pct > 0:
                # Split remaining between Roth and after-tax (favor Roth)
                roth_pct = random.uniform(0.5, 1.0) * remaining_pct
                after_tax_pct = remaining_pct - roth_pct
            else:
                roth_pct = 0.0
                after_tax_pct = 0.0

            pre_tax_contribution = employee_contribution * pre_tax_pct
            roth_contribution = employee_contribution * roth_pct
            after_tax_contribution = employee_contribution * after_tax_pct
        else:
            employee_contribution = 0.0
            pre_tax_contribution = 0.0
            roth_contribution = 0.0
            after_tax_contribution = 0.0

        # Employer contributions based on realistic match formulas
        employer_match_rate = random.uniform(0.02, 0.06) if participates else 0.0
        employer_match_contribution = min(employee_contribution * employer_match_rate, gross_compensation * 0.03)
        employer_core_contribution = gross_compensation * random.uniform(0.01, 0.03)

        # Capped compensation (IRS limits - $345,000 for 2024)
        employee_capped_compensation = min(gross_compensation, 345000.0)

        # Calculate actual deferral rate based on total contribution and capped compensation
        employee_deferral_rate = employee_contribution / employee_capped_compensation if employee_capped_compensation > 0 else 0.0

        # Eligibility entry date (typically hire date or next plan entry date)
        eligibility_months_delay = random.choice([0, 1, 3, 6, 12])  # Common eligibility periods
        eligibility_entry_date = hire_date + timedelta(days=eligibility_months_delay * 30)

        employees.append(
            {
                "employee_id": emp_id,
                "employee_ssn": ssn,
                "employee_birth_date": birth_date.strftime("%Y-%m-%d"),
                "employee_hire_date": hire_date.strftime("%Y-%m-%d"),
                "employee_termination_date": termination_date.strftime("%Y-%m-%d")
                if termination_date
                else None,
                "employee_gross_compensation": float(gross_compensation),
                "employee_capped_compensation": float(employee_capped_compensation),
                "employee_deferral_rate": float(employee_deferral_rate),
                "employee_contribution": float(employee_contribution),
                "pre_tax_contribution": float(pre_tax_contribution),
                "roth_contribution": float(roth_contribution),
                "after_tax_contribution": float(after_tax_contribution),
                "employer_core_contribution": float(employer_core_contribution),
                "employer_match_contribution": float(employer_match_contribution),
                "eligibility_entry_date": eligibility_entry_date.strftime("%Y-%m-%d"),
                "active": bool(not is_terminated),
            }
        )
        current_employee_id += 1

    # Create DataFrame
    df = pd.DataFrame(employees)

    # Convert date strings to datetime.date objects
    date_columns = [
        "employee_birth_date",
        "employee_hire_date",
        "employee_termination_date",
        "eligibility_entry_date",
    ]
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.date

    # Convert to PyArrow Table with explicit schema to ensure date types are preserved
    schema = pa.schema(
        [
            ("employee_id", pa.string()),
            ("employee_ssn", pa.string()),
            ("employee_birth_date", pa.date32()),
            ("employee_hire_date", pa.date32()),
            ("employee_termination_date", pa.date32()),
            ("employee_gross_compensation", pa.float64()),
            ("employee_capped_compensation", pa.float64()),
            ("employee_deferral_rate", pa.float64()),
            ("employee_contribution", pa.float64()),
            ("pre_tax_contribution", pa.float64()),
            ("roth_contribution", pa.float64()),
            ("after_tax_contribution", pa.float64()),
            ("employer_core_contribution", pa.float64()),
            ("employer_match_contribution", pa.float64()),
            ("eligibility_entry_date", pa.date32()),
            ("active", pa.bool_()),
        ]
    )

    table = pa.Table.from_pandas(df, schema=schema)
    pq.write_table(table, output_path)

    print(f"Mock Parquet file saved to: {output_path}")
    print(f"Generated {len(df)} records.")
    print("\nSample Data:")
    print(df.head())
    print("\nSummary Statistics:")
    print(df.describe())
    print("\nActive/Terminated Split:")
    print(df["active"].value_counts())


if __name__ == "__main__":
    # Generate the census data file in the location expected by the dbt model
    generate_mock_workforce_parquet(
        num_employees=5000,
        output_path="data/census_preprocessed.parquet",
        base_year=2024,
        random_seed=42,  # Use consistent seed for reproducible baseline data
    )
