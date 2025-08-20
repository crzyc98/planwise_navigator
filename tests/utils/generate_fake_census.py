# filename: tests/utils/generate_fake_census.py
"""Generate synthetic employee census data for testing."""

import argparse
import random
from datetime import date, timedelta
from typing import Any, Dict

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

# Configuration
LEVEL_DISTRIBUTION = {
    1: 0.40,  # 40% Level 1
    2: 0.30,  # 30% Level 2
    3: 0.20,  # 20% Level 3
    4: 0.08,  # 8% Level 4
    5: 0.02,  # 2% Level 5
}

SALARY_RANGES = {
    1: (40000, 60000),
    2: (55000, 85000),
    3: (80000, 120000),
    4: (110000, 160000),
    5: (150000, 250000),
}

AGE_RANGES = {1: (22, 65), 2: (25, 65), 3: (28, 65), 4: (32, 65), 5: (35, 65)}


def generate_employee(employee_id: str, level: int, base_date: date) -> Dict[str, Any]:
    """Generate a single employee record."""
    age = random.randint(*AGE_RANGES[level])

    # Tenure based on age and level
    max_tenure = min(age - 22, 20)  # Max 20 years tenure
    if level == 1:
        tenure = random.uniform(0, min(5, max_tenure))
    elif level == 2:
        tenure = random.uniform(1, min(8, max_tenure))
    elif level == 3:
        tenure = random.uniform(3, min(12, max_tenure))
    elif level == 4:
        tenure = random.uniform(5, min(15, max_tenure))
    else:  # Level 5
        tenure = random.uniform(7, max_tenure)

    hire_date = base_date - timedelta(days=int(tenure * 365))

    # Salary based on level and tenure
    min_sal, max_sal = SALARY_RANGES[level]
    tenure_factor = min(tenure / 20, 1.0)  # 0-1 based on tenure
    salary = min_sal + (max_sal - min_sal) * (0.3 + 0.7 * tenure_factor)
    salary = round(salary / 1000) * 1000  # Round to nearest 1000

    return {
        "employee_id": employee_id,
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        "email": f"{employee_id}@company.com",
        "level_id": level,
        "department": random.choice(
            ["Engineering", "Sales", "Marketing", "Operations", "Finance", "HR"]
        ),
        "location": random.choice(["Boston", "NYC", "Chicago", "SF", "Remote"]),
        "age": age,
        "tenure_years": round(tenure, 1),
        "hire_date": hire_date.isoformat(),
        "current_compensation": salary,
        "performance_rating": random.choice(
            [1, 2, 3, 3, 3, 4, 4, 4, 4, 5]
        ),  # Weighted towards 3-4
        "active_flag": True,
    }


def generate_census_data(num_employees: int) -> pd.DataFrame:
    """Generate complete census dataset."""
    employees = []
    base_date = date.today()

    # Calculate employees per level
    level_counts = {}
    remaining = num_employees

    for level, pct in LEVEL_DISTRIBUTION.items():
        if level < 5:
            level_counts[level] = int(num_employees * pct)
            remaining -= level_counts[level]

        # filename: tests/utils/generate_fake_census.py (continued)
        else:
            level_counts[level] = remaining  # Give remainder to highest level

    # Generate employees
    employee_counter = 1
    for level, count in level_counts.items():
        for _ in range(count):
            employee_id = f"E{employee_counter:06d}"
            employee = generate_employee(employee_id, level, base_date)
            employees.append(employee)
            employee_counter += 1

    # Create DataFrame
    df = pd.DataFrame(employees)

    # Add some terminated employees (10% of workforce)
    num_terminated = int(num_employees * 0.1)
    terminated_indices = random.sample(range(len(df)), num_terminated)
    df.loc[terminated_indices, "active_flag"] = False
    df.loc[terminated_indices, "termination_date"] = pd.to_datetime(
        [
            fake.date_between(start_date="-2y", end_date="today")
            for _ in range(num_terminated)
        ]
    ).astype(str)

    return df


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic employee census data"
    )
    parser.add_argument(
        "--employees", type=int, default=1000, help="Number of employees to generate"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/synthetic_census.csv",
        help="Output file path",
    )
    parser.add_argument(
        "--format", choices=["csv", "parquet"], default="csv", help="Output format"
    )

    args = parser.parse_args()

    print(f"Generating {args.employees} synthetic employee records...")
    df = generate_census_data(args.employees)

    # Save to file
    if args.format == "csv":
        df.to_csv(args.output, index=False)
    else:
        df.to_parquet(args.output, index=False)

    print(f"Generated {len(df)} records")
    print(f"Active employees: {df['active_flag'].sum()}")
    print("Level distribution:")
    print(df[df["active_flag"]].groupby("level_id").size())
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
