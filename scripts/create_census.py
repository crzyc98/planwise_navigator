import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import pyarrow as pa
import pyarrow.parquet as pq


def generate_mock_workforce_parquet(
    num_employees: int = 5000,
    output_path: str = "mock_census_data.parquet",
    base_year: int = 2024,  # The year the "census" data represents
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
    Generates a mock Parquet file for workforce census data.

    Args:
        num_employees (int): The target number of employees to generate.
        output_path (str): The file path to save the Parquet file.
        base_year (int): The year for which the initial census data is valid.
        target_experienced_termination_rate (float): Roughly what percentage of
                                                     employees might be "terminated" in the initial data.
        target_net_new_hire_rate (float): Roughly what percentage of
                                         employees might be "new hires" in the initial data (for hire dates).
        comp_ranges (dict): Dictionary mapping mock levels to (min_comp, max_comp).
    """

    print(f"Generating mock workforce data for {num_employees} employees...")

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
        emp_id = f"EMP_{current_employee_id:06d}"
        ssn = f"SSN-{random.randint(100000000, 999999999)}"

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

        employees.append(
            {
                "employee_id": emp_id,
                "employee_ssn": ssn,
                "employee_birth_date": birth_date.strftime("%Y-%m-%d"),
                "employee_hire_date": hire_date.strftime("%Y-%m-%d"),
                "employee_termination_date": termination_date.strftime("%Y-%m-%d")
                if termination_date
                else None,
                "employee_gross_compensation": float(
                    gross_compensation
                ),  # Ensure float type for numeric operations
                "active": bool(not is_terminated),  # Ensure boolean type
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
    )
