#!/usr/bin/env python3
"""
Large-scale test data generation for PlanWise Navigator stress testing.

Story S063-09: Large Dataset Stress Testing
- Generate 100K+ employee datasets for single-threaded performance validation
- Memory-efficient generation with configurable employee counts
- Realistic workforce distributions for enterprise simulation scenarios
- Support for various demographic and compensation profiles
"""

import argparse
import logging
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psutil
from faker import Faker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Seed for reproducible results
SEED = 42
fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

# Realistic enterprise workforce distribution
LEVEL_DISTRIBUTION = {
    1: 0.35,  # 35% Level 1 (Individual Contributors)
    2: 0.30,  # 30% Level 2 (Senior ICs)
    3: 0.20,  # 20% Level 3 (Senior/Lead)
    4: 0.12,  # 12% Level 4 (Management)
    5: 0.03,  # 3% Level 5 (Executive)
}

# Compensation ranges by level (enterprise scale)
SALARY_RANGES = {
    1: (45000, 75000),    # Entry level
    2: (65000, 95000),    # Mid level
    3: (85000, 130000),   # Senior level
    4: (120000, 180000),  # Management
    5: (180000, 350000),  # Executive
}

# Age ranges by level
AGE_RANGES = {
    1: (22, 65),
    2: (25, 65),
    3: (28, 65),
    4: (32, 65),
    5: (35, 65)
}

# Department distribution (enterprise realistic)
DEPARTMENT_WEIGHTS = {
    "Engineering": 0.25,
    "Sales": 0.20,
    "Operations": 0.15,
    "Marketing": 0.10,
    "Finance": 0.08,
    "HR": 0.05,
    "Legal": 0.03,
    "IT": 0.07,
    "Customer Success": 0.07,
}

# Location distribution (remote-friendly enterprise)
LOCATION_WEIGHTS = {
    "Remote": 0.35,
    "New York": 0.15,
    "San Francisco": 0.12,
    "Boston": 0.08,
    "Chicago": 0.08,
    "Austin": 0.06,
    "Seattle": 0.05,
    "Los Angeles": 0.05,
    "Atlanta": 0.03,
    "Denver": 0.03,
}

class MemoryMonitor:
    """Memory usage monitoring for large dataset generation"""

    def __init__(self):
        self.process = psutil.Process()
        self.start_memory = self.get_memory_mb()
        self.peak_memory = self.start_memory

    def get_memory_mb(self) -> float:
        """Get current memory usage in MB"""
        return self.process.memory_info().rss / 1024 / 1024

    def log_memory(self, stage: str) -> float:
        """Log memory usage for a stage"""
        current_memory = self.get_memory_mb()
        self.peak_memory = max(self.peak_memory, current_memory)
        delta = current_memory - self.start_memory

        logger.info(f"{stage}: {current_memory:.1f} MB (delta: {delta:+.1f} MB, peak: {self.peak_memory:.1f} MB)")
        return current_memory

class LargeDatasetGenerator:
    """Generate large-scale employee datasets for stress testing"""

    def __init__(self, num_employees: int, memory_efficient: bool = True):
        self.num_employees = num_employees
        self.memory_efficient = memory_efficient
        self.monitor = MemoryMonitor()

        # Calculate level counts upfront
        self.level_counts = self._calculate_level_distribution()

    def _calculate_level_distribution(self) -> Dict[int, int]:
        """Calculate employee count by level"""
        level_counts = {}
        remaining = self.num_employees

        for level in range(1, 5):  # Levels 1-4
            count = int(self.num_employees * LEVEL_DISTRIBUTION[level])
            level_counts[level] = count
            remaining -= count

        # All remaining go to level 5
        level_counts[5] = remaining

        logger.info(f"Level distribution: {level_counts}")
        return level_counts

    def _weighted_choice(self, choices: Dict[str, float]) -> str:
        """Make a weighted random choice"""
        population = list(choices.keys())
        weights = list(choices.values())
        return random.choices(population, weights=weights)[0]

    def _generate_employee_batch(
        self,
        start_id: int,
        batch_size: int,
        level: int,
        base_date: date
    ) -> List[Dict[str, Any]]:
        """Generate a batch of employees for a specific level"""
        employees = []

        for i in range(batch_size):
            employee_id = f"E{start_id + i:06d}"
            employee = self._generate_single_employee(employee_id, level, base_date)
            employees.append(employee)

        return employees

    def _generate_single_employee(
        self,
        employee_id: str,
        level: int,
        base_date: date
    ) -> Dict[str, Any]:
        """Generate a single employee record"""
        # Demographics
        age = random.randint(*AGE_RANGES[level])

        # Tenure logic
        max_tenure = min(age - 22, 25)  # Max 25 years tenure
        if level == 1:
            tenure = random.uniform(0, min(5, max_tenure))
        elif level == 2:
            tenure = random.uniform(1, min(8, max_tenure))
        elif level == 3:
            tenure = random.uniform(3, min(12, max_tenure))
        elif level == 4:
            tenure = random.uniform(5, min(15, max_tenure))
        else:  # Level 5
            tenure = random.uniform(8, max_tenure)

        hire_date = base_date - timedelta(days=int(tenure * 365))

        # Compensation with realistic variance
        min_sal, max_sal = SALARY_RANGES[level]
        tenure_factor = min(tenure / 20, 1.0)
        performance_factor = random.uniform(0.8, 1.2)  # ±20% performance variance

        base_salary = min_sal + (max_sal - min_sal) * (0.2 + 0.6 * tenure_factor)
        salary = base_salary * performance_factor
        salary = round(salary / 1000) * 1000  # Round to nearest $1k

        # Deferral rate (realistic distribution)
        if random.random() < 0.25:  # 25% not enrolled
            deferral_rate = 0.0
        else:
            # Enrolled with realistic rates
            if level <= 2:
                deferral_rate = random.uniform(0.03, 0.08)  # 3-8%
            elif level <= 3:
                deferral_rate = random.uniform(0.05, 0.12)  # 5-12%
            elif level <= 4:
                deferral_rate = random.uniform(0.08, 0.15)  # 8-15%
            else:  # Executive level
                deferral_rate = random.uniform(0.10, 0.20)  # 10-20%

        return {
            "employee_id": employee_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": f"{employee_id}@company.com",
            "level_id": level,
            "department": self._weighted_choice(DEPARTMENT_WEIGHTS),
            "location": self._weighted_choice(LOCATION_WEIGHTS),
            "age": age,
            "tenure_years": round(tenure, 1),
            "hire_date": hire_date.isoformat(),
            "current_compensation": salary,
            "employee_deferral_rate": round(deferral_rate, 4),  # For Epic E049 census integration
            "performance_rating": random.choices(
                [1, 2, 3, 4, 5],
                weights=[0.05, 0.15, 0.40, 0.30, 0.10]  # Realistic performance distribution
            )[0],
            "active_flag": True,
        }

    def generate_dataset(
        self,
        batch_size: int = 10000,
        include_terminated: bool = True,
        termination_rate: float = 0.08
    ) -> pd.DataFrame:
        """
        Generate complete large dataset with memory-efficient batch processing

        Args:
            batch_size: Number of employees to generate per batch (memory management)
            include_terminated: Whether to include terminated employees
            termination_rate: Percentage of workforce to mark as terminated

        Returns:
            DataFrame with all generated employees
        """
        logger.info(f"Generating {self.num_employees:,} employee dataset...")
        start_time = time.time()

        self.monitor.log_memory("Generation start")

        all_employees = []
        base_date = date.today()
        employee_counter = 1

        # Generate by level to maintain realistic distributions
        for level, count in self.level_counts.items():
            logger.info(f"Generating Level {level}: {count:,} employees")

            batches_needed = (count + batch_size - 1) // batch_size

            for batch_idx in range(batches_needed):
                batch_start = batch_idx * batch_size
                batch_end = min(batch_start + batch_size, count)
                actual_batch_size = batch_end - batch_start

                # Generate batch
                batch_employees = self._generate_employee_batch(
                    employee_counter, actual_batch_size, level, base_date
                )

                all_employees.extend(batch_employees)
                employee_counter += actual_batch_size

                # Memory monitoring every 50k employees
                if employee_counter % 50000 == 0:
                    self.monitor.log_memory(f"Generated {employee_counter:,} employees")

                    # Optional garbage collection for very large datasets
                    if self.memory_efficient and employee_counter % 100000 == 0:
                        import gc
                        gc.collect()

        self.monitor.log_memory("Employee generation complete")

        # Convert to DataFrame
        logger.info("Converting to DataFrame...")
        df = pd.DataFrame(all_employees)

        self.monitor.log_memory("DataFrame creation complete")

        # Add terminated employees if requested
        if include_terminated and termination_rate > 0:
            self._add_terminated_employees(df, termination_rate)

        generation_time = time.time() - start_time
        logger.info(f"Dataset generation completed in {generation_time:.1f} seconds")
        logger.info(f"Generated {len(df):,} total records")

        self.monitor.log_memory("Generation final")

        return df

    def _add_terminated_employees(self, df: pd.DataFrame, termination_rate: float):
        """Add terminated employees to the dataset"""
        num_terminated = int(len(df) * termination_rate)
        terminated_indices = random.sample(range(len(df)), num_terminated)

        # Mark as terminated
        df.loc[terminated_indices, "active_flag"] = False

        # Add termination dates (realistic distribution over past 2 years)
        termination_dates = []
        for _ in range(num_terminated):
            days_ago = random.randint(30, 730)  # 30 days to 2 years ago
            term_date = date.today() - timedelta(days=days_ago)
            termination_dates.append(term_date.isoformat())

        df.loc[terminated_indices, "termination_date"] = termination_dates

        # Reset deferral rates for terminated employees
        df.loc[terminated_indices, "employee_deferral_rate"] = 0.0

        logger.info(f"Added {num_terminated:,} terminated employees ({termination_rate:.1%})")

def generate_multiple_dataset_sizes(
    output_dir: Path,
    dataset_sizes: List[int],
    formats: List[str] = ["parquet", "csv"]
) -> Dict[int, Dict[str, Path]]:
    """
    Generate multiple dataset sizes for comprehensive stress testing

    Args:
        output_dir: Directory to save generated datasets
        dataset_sizes: List of employee counts to generate
        formats: File formats to save (parquet, csv)

    Returns:
        Dictionary mapping dataset size to file paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_files = {}

    for size in dataset_sizes:
        logger.info(f"\n{'='*50}")
        logger.info(f"GENERATING DATASET: {size:,} EMPLOYEES")
        logger.info(f"{'='*50}")

        # Generate dataset
        generator = LargeDatasetGenerator(size, memory_efficient=True)
        df = generator.generate_dataset(
            batch_size=min(10000, size // 10),  # Adaptive batch size
            include_terminated=True,
            termination_rate=0.08
        )

        # Save in requested formats
        size_files = {}
        for fmt in formats:
            if fmt == "parquet":
                file_path = output_dir / f"stress_test_{size:06d}_employees.parquet"
                df.to_parquet(file_path, index=False, compression="snappy")
            elif fmt == "csv":
                file_path = output_dir / f"stress_test_{size:06d}_employees.csv"
                df.to_csv(file_path, index=False)
            else:
                logger.warning(f"Unsupported format: {fmt}")
                continue

            size_files[fmt] = file_path
            file_size_mb = file_path.stat().st_size / 1024 / 1024
            logger.info(f"Saved {fmt.upper()}: {file_path} ({file_size_mb:.1f} MB)")

        generated_files[size] = size_files

        # Print dataset summary
        logger.info(f"\nDATASET SUMMARY ({size:,} employees):")
        logger.info(f"Active employees: {df['active_flag'].sum():,}")
        logger.info(f"Terminated employees: {(~df['active_flag']).sum():,}")
        logger.info("Level distribution:")
        for level, count in df.groupby("level_id").size().sort_index().items():
            pct = count / len(df) * 100
            logger.info(f"  Level {level}: {count:,} ({pct:.1f}%)")

        logger.info(f"Deferral participation: {(df['employee_deferral_rate'] > 0).sum():,} enrolled")
        logger.info(f"Avg deferral rate (enrolled): {df[df['employee_deferral_rate'] > 0]['employee_deferral_rate'].mean():.2%}")

    return generated_files

def main():
    """CLI entry point for large dataset generation"""
    parser = argparse.ArgumentParser(
        description="Generate large-scale employee datasets for PlanWise Navigator stress testing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Dataset size options
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[1000, 10000, 50000, 100000, 250000],
        help="Employee counts to generate"
    )

    # Output configuration
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/stress_test"),
        help="Output directory for generated datasets"
    )

    parser.add_argument(
        "--formats",
        choices=["parquet", "csv"],
        nargs="+",
        default=["parquet"],
        help="Output formats"
    )

    # Generation options
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for memory-efficient generation"
    )

    parser.add_argument(
        "--termination-rate",
        type=float,
        default=0.08,
        help="Percentage of workforce to mark as terminated"
    )

    # Performance options
    parser.add_argument(
        "--memory-efficient",
        action="store_true",
        default=True,
        help="Enable memory-efficient generation"
    )

    parser.add_argument(
        "--single-size",
        type=int,
        help="Generate only a single dataset size"
    )

    args = parser.parse_args()

    # Determine sizes to generate
    if args.single_size:
        dataset_sizes = [args.single_size]
    else:
        dataset_sizes = sorted(args.sizes)

    logger.info(f"PlanWise Navigator Large Dataset Generator")
    logger.info(f"Dataset sizes: {[f'{s:,}' for s in dataset_sizes]}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Output formats: {args.formats}")
    logger.info(f"Memory efficient: {args.memory_efficient}")

    try:
        generated_files = generate_multiple_dataset_sizes(
            output_dir=args.output_dir,
            dataset_sizes=dataset_sizes,
            formats=args.formats
        )

        # Summary report
        logger.info(f"\n{'='*60}")
        logger.info(f"GENERATION COMPLETE")
        logger.info(f"{'='*60}")

        total_files = sum(len(files) for files in generated_files.values())
        logger.info(f"Generated {total_files} files across {len(dataset_sizes)} dataset sizes")

        for size, files in generated_files.items():
            logger.info(f"\n{size:,} employees:")
            for fmt, path in files.items():
                size_mb = path.stat().st_size / 1024 / 1024
                logger.info(f"  {fmt.upper()}: {path} ({size_mb:.1f} MB)")

        logger.info(f"\nFiles ready for stress testing in: {args.output_dir}")

    except Exception as e:
        logger.error(f"Dataset generation failed: {e}")
        raise

if __name__ == "__main__":
    main()
