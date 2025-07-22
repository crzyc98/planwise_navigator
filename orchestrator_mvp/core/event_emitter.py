#!/usr/bin/env python3
"""Event emission module for MVP orchestrator.

Generates simulation events based on workforce calculations and stores them
in the database following the event schema from fct_yearly_events.
"""

import random
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import uuid
import time
import hashlib

from .database_manager import get_connection


def generate_experienced_termination_events(
    num_terminations: int,
    simulation_year: int,
    random_seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Generate experienced termination events by sampling from active workforce.

    Args:
        num_terminations: Number of termination events to generate
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random sampling

    Returns:
        List of termination event dictionaries
    """
    if random_seed is not None:
        random.seed(random_seed)

    conn = get_connection()
    try:
        # Get active workforce - use year-aware logic for multi-year simulations
        if simulation_year == 2025:
            # First simulation year - use baseline workforce
            workforce_query = """
            SELECT
                employee_id,
                employee_ssn,
                employee_birth_date,
                employee_hire_date,
                current_compensation,
                current_age,
                current_tenure,
                level_id
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
            ORDER BY employee_id
            """
            print(f"🔍 Using baseline workforce for experienced terminations (year {simulation_year})")
        else:
            # Subsequent years - use previous year's active workforce
            previous_year = simulation_year - 1
            workforce_query = """
            SELECT
                employee_id,
                employee_ssn,
                employee_birth_date,
                employee_hire_date,
                current_compensation,
                current_age,
                current_tenure,
                level_id
            FROM fct_workforce_snapshot
            WHERE simulation_year = ?
            AND employment_status = 'active'
            ORDER BY employee_id
            """
            print(f"🔍 Using previous year ({previous_year}) workforce for experienced terminations")

        # Execute query with parameters if needed
        if simulation_year == 2025:
            workforce_df = conn.execute(workforce_query).df()
        else:
            workforce_df = conn.execute(workforce_query, [simulation_year - 1]).df()

            # Fallback to baseline if no previous year data found
            if len(workforce_df) == 0:
                print(f"⚠️  No workforce data found for year {simulation_year - 1}, falling back to baseline")
                fallback_query = """
                SELECT
                    employee_id,
                    employee_ssn,
                    employee_birth_date,
                    employee_hire_date,
                    current_compensation,
                    current_age,
                    current_tenure,
                    level_id
                FROM int_baseline_workforce
                WHERE employment_status = 'active'
                ORDER BY employee_id
                """
                workforce_df = conn.execute(fallback_query).df()

        if len(workforce_df) == 0:
            raise ValueError("No active workforce found in int_baseline_workforce")

        if num_terminations > len(workforce_df):
            raise ValueError(f"Cannot generate {num_terminations} terminations from {len(workforce_df)} employees")

        # Sample employees for termination
        sampled_employees = workforce_df.sample(n=num_terminations, random_state=random_seed)

        events = []
        for _, employee in sampled_employees.iterrows():
            # Calculate age and tenure bands
            age_band = _calculate_age_band(employee['current_age'])
            tenure_band = _calculate_tenure_band(employee['current_tenure'])

            # Generate random effective date within simulation year
            effective_date = _generate_random_date(simulation_year)

            # Create termination event
            event = {
                'employee_id': employee['employee_id'],
                'employee_ssn': employee['employee_ssn'],
                'event_type': 'termination',
                'simulation_year': simulation_year,
                'effective_date': effective_date,
                'event_details': 'experienced_termination',
                'compensation_amount': employee['current_compensation'],
                'previous_compensation': None,
                'employee_age': employee['current_age'],
                'employee_tenure': employee['current_tenure'],
                'level_id': employee['level_id'],
                'age_band': age_band,
                'tenure_band': tenure_band,
                'event_probability': 0.12,  # Default termination rate
                'event_category': 'experienced_termination',
                'event_sequence': 1,  # Terminations have highest priority
                'created_at': datetime.now(),
                'parameter_scenario_id': 'mvp_test',
                'parameter_source': 'dynamic',
                'data_quality_flag': 'VALID'
            }

            events.append(event)

        return events

    finally:
        conn.close()


def store_events_in_database(events: List[Dict[str, Any]], table_name: str = "fct_yearly_events") -> None:
    """Store events in the database.

    Args:
        events: List of event dictionaries to store
        table_name: Name of table to store events in
    """
    if not events:
        print("No events to store")
        return

    conn = get_connection()
    try:
        # Create table if it doesn't exist (schema aligned with dbt expectations)
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            employee_id VARCHAR,
            employee_ssn VARCHAR,
            event_type VARCHAR,
            simulation_year INTEGER,
            effective_date TIMESTAMP,
            event_details VARCHAR,
            compensation_amount DOUBLE,
            previous_compensation DOUBLE,
            employee_age BIGINT,
            employee_tenure BIGINT,
            level_id INTEGER,
            age_band VARCHAR,
            tenure_band VARCHAR,
            event_probability DOUBLE,
            event_category VARCHAR,
            event_sequence BIGINT,
            created_at TIMESTAMP WITH TIME ZONE,
            parameter_scenario_id VARCHAR,
            parameter_source VARCHAR,
            data_quality_flag VARCHAR
        )
        """
        conn.execute(create_table_sql)

        # Clear existing events for this simulation year
        clear_sql = f"DELETE FROM {table_name} WHERE simulation_year = ?"
        conn.execute(clear_sql, [events[0]['simulation_year']])

        # Insert events
        for event in events:
            insert_sql = f"""
            INSERT INTO {table_name} VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """
            conn.execute(insert_sql, [
                event['employee_id'],
                event['employee_ssn'],
                event['event_type'],
                event['simulation_year'],
                event['effective_date'],
                event['event_details'],
                event['compensation_amount'],
                event['previous_compensation'],
                event['employee_age'],
                event['employee_tenure'],
                event['level_id'],
                event['age_band'],
                event['tenure_band'],
                event['event_probability'],
                event['event_category'],
                event['event_sequence'],
                event['created_at'],
                event['parameter_scenario_id'],
                event['parameter_source'],
                event['data_quality_flag']
            ])

        print(f"✅ Stored {len(events)} events in {table_name}")

    finally:
        conn.close()


def _calculate_age_band(age: int) -> str:
    """Calculate age band from age."""
    if age < 25:
        return '< 25'
    elif age < 35:
        return '25-34'
    elif age < 45:
        return '35-44'
    elif age < 55:
        return '45-54'
    elif age < 65:
        return '55-64'
    else:
        return '65+'


def _calculate_tenure_band(tenure: float) -> str:
    """Calculate tenure band from tenure."""
    if tenure < 2:
        return '< 2'
    elif tenure < 5:
        return '2-4'
    elif tenure < 10:
        return '5-9'
    elif tenure < 20:
        return '10-19'
    else:
        return '20+'


def _generate_random_date(year: int) -> date:
    """Generate random date within the given year."""
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    # Generate random number of days between start and end
    days_range = (end_date - start_date).days
    random_days = random.randint(0, days_range)

    return start_date + timedelta(days=random_days)


def _load_promotion_hazard_config(conn, validation_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """Load promotion hazard configuration from seed files with enhanced validation.

    Args:
        conn: Database connection
        validation_callback: Optional callback for validation hooks

    Returns:
        Dictionary containing hazard configuration
    """
    start_time = time.time()
    try:
        # Load base configuration
        base_config = conn.execute("""
            SELECT base_rate, level_dampener_factor
            FROM config_promotion_hazard_base
        """).fetchone()

        if not base_config:
            # Default values if seed not found
            base_rate = 0.1
            level_dampener_factor = 0.15
        else:
            base_rate, level_dampener_factor = base_config

        # Load age multipliers
        age_multipliers = {}
        age_results = conn.execute("""
            SELECT age_band, multiplier
            FROM config_promotion_hazard_age_multipliers
        """).fetchall()

        for age_band, multiplier in age_results:
            age_multipliers[age_band] = multiplier

        # Load tenure multipliers
        tenure_multipliers = {}
        tenure_results = conn.execute("""
            SELECT tenure_band, multiplier
            FROM config_promotion_hazard_tenure_multipliers
        """).fetchall()

        for tenure_band, multiplier in tenure_results:
            tenure_multipliers[tenure_band] = multiplier

        # Set defaults if no data found
        if not age_multipliers:
            age_multipliers = {
                '< 25': 1.0, '25-34': 1.2, '35-44': 1.1,
                '45-54': 0.9, '55-64': 0.7, '65+': 0.5
            }

        if not tenure_multipliers:
            tenure_multipliers = {
                '< 2': 0.8, '2-4': 1.0, '5-9': 1.2,
                '10-19': 1.1, '20+': 0.9
            }

        # Validate configuration values
        config = {
            'base_rate': base_rate,
            'level_dampener_factor': level_dampener_factor,
            'age_multipliers': age_multipliers,
            'tenure_multipliers': tenure_multipliers
        }

        # Enhanced validation
        validation_errors = []

        # Validate base_rate is within reasonable range (0-50%)
        if not 0 < base_rate <= 0.5:
            validation_errors.append(f"Base rate {base_rate} outside valid range (0, 0.5]")

        # Validate level_dampener_factor is within reasonable range (0-50%)
        if not 0 <= level_dampener_factor <= 0.5:
            validation_errors.append(f"Level dampener factor {level_dampener_factor} outside valid range [0, 0.5]")

        # Validate multipliers are positive
        for age_band, mult in age_multipliers.items():
            if mult <= 0:
                validation_errors.append(f"Age multiplier for {age_band} is non-positive: {mult}")

        for tenure_band, mult in tenure_multipliers.items():
            if mult <= 0:
                validation_errors.append(f"Tenure multiplier for {tenure_band} is non-positive: {mult}")

        if validation_errors:
            error_msg = "Hazard configuration validation failed:\n" + "\n".join(validation_errors)
            if validation_callback:
                validation_callback("hazard_config_validation", False, error_msg)
            raise ValueError(error_msg)

        # Log loading time
        load_time = time.time() - start_time
        print(f"✅ Hazard configuration loaded in {load_time:.3f} seconds")

        if validation_callback:
            validation_callback("hazard_config_loaded", True, config)

        return config

    except Exception as e:
        load_time = time.time() - start_time
        print(f"⚠️  Error loading hazard config after {load_time:.3f} seconds: {e}")
        # Return default configuration
        return {
            'base_rate': 0.1,
            'level_dampener_factor': 0.15,
            'age_multipliers': {
                '< 25': 1.0, '25-34': 1.2, '35-44': 1.1,
                '45-54': 0.9, '55-64': 0.7, '65+': 0.5
            },
            'tenure_multipliers': {
                '< 2': 0.8, '2-4': 1.0, '5-9': 1.2,
                '10-19': 1.1, '20+': 0.9
            }
        }


def get_legacy_random_value(employee_id: str, simulation_year: int, random_seed: int) -> float:
    """Generate a random value using the legacy hash-based approach for consistency.

    This matches the legacy dbt pipeline's random value generation to ensure
    consistent promotion decisions across runs.

    Args:
        employee_id: Employee identifier
        simulation_year: Year of simulation
        random_seed: Random seed for reproducibility

    Returns:
        Float between 0.0 and 1.0
    """
    # Combine inputs into a single string
    combined_string = f"{employee_id}_{simulation_year}_{random_seed}"

    # Generate SHA256 hash
    hash_object = hashlib.sha256(combined_string.encode())
    hash_hex = hash_object.hexdigest()

    # Convert first 8 hex characters to integer
    hash_int = int(hash_hex[:8], 16)

    # Normalize to 0.0-1.0 range
    random_value = hash_int / (2**32 - 1)

    return random_value


def calculate_promotion_probability(level: int, tenure: float, age: int, hazard_config: Dict[str, Any]) -> float:
    """Calculate promotion probability for testing purposes.

    This is a public interface for the internal _calculate_promotion_probability
    function, used by test suites.
    """
    age_band = _calculate_age_band(age)
    tenure_band = _calculate_tenure_band(tenure)
    return _calculate_promotion_probability(level, age_band, tenure_band, hazard_config)


def _calculate_promotion_probability(level_id: int, age_band: str, tenure_band: str, hazard_config: Dict[str, Any]) -> float:
    """Calculate promotion probability using hazard-based formula matching legacy dbt logic."""
    base_rate = hazard_config['base_rate']
    level_dampener_factor = hazard_config['level_dampener_factor']
    age_multipliers = hazard_config['age_multipliers']
    tenure_multipliers = hazard_config['tenure_multipliers']

    # Get multipliers with defaults
    age_mult = age_multipliers.get(age_band, 1.0)
    tenure_mult = tenure_multipliers.get(tenure_band, 1.0)

    # Apply legacy formula: base_rate * tenure_mult * age_mult * max(0, 1 - level_dampener_factor * (level_id - 1))
    level_dampener = max(0, 1 - level_dampener_factor * (level_id - 1))

    promotion_rate = base_rate * tenure_mult * age_mult * level_dampener

    # Cap at reasonable maximum
    return min(promotion_rate, 0.5)  # Maximum 50% promotion rate


def generate_and_store_termination_events(
    num_terminations: int,
    simulation_year: int,
    random_seed: Optional[int] = None,
    table_name: str = "fct_yearly_events"
) -> None:
    """Generate and store termination events in one operation.

    Args:
        num_terminations: Number of termination events to generate
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random sampling
        table_name: Name of table to store events in
    """
    print(f"\n🎯 Generating {num_terminations} termination events for year {simulation_year}")

    # Generate events
    events = generate_experienced_termination_events(
        num_terminations=num_terminations,
        simulation_year=simulation_year,
        random_seed=random_seed
    )

    # Store events
    store_events_in_database(events, table_name)

    print(f"✅ Event generation completed: {len(events)} termination events stored")


def generate_hiring_events(
    num_hires: int,
    simulation_year: int,
    random_seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Generate hiring events based on target growth and termination replacement needs.

    Args:
        num_hires: Number of new hires to generate
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random generation

    Returns:
        List of hiring event dictionaries
    """
    if random_seed is not None:
        random.seed(random_seed)

    # Level distribution (weighted toward entry levels)
    level_distribution = [
        (1, 0.40),  # 40% Level 1 (entry level)
        (2, 0.30),  # 30% Level 2
        (3, 0.20),  # 20% Level 3
        (4, 0.08),  # 8% Level 4
        (5, 0.02)   # 2% Level 5 (senior)
    ]

    # Calculate hires per level
    hires_per_level = []
    remaining_hires = num_hires
    for level_id, weight in level_distribution[:-1]:  # All but last
        level_hires = int(num_hires * weight)
        hires_per_level.append((level_id, level_hires))
        remaining_hires -= level_hires
    # Give remaining to last level to ensure exact count
    hires_per_level.append((level_distribution[-1][0], remaining_hires))

    # Get compensation ranges by level
    conn = get_connection()
    try:
        comp_query = """
        SELECT
            level_id,
            min_compensation,
            CASE
                WHEN level_id <= 3 THEN max_compensation
                WHEN level_id = 4 THEN LEAST(max_compensation, 250000)
                WHEN level_id = 5 THEN LEAST(max_compensation, 350000)
                ELSE max_compensation
            END AS max_compensation,
            (min_compensation +
             CASE
                 WHEN level_id <= 3 THEN max_compensation
                 WHEN level_id = 4 THEN LEAST(max_compensation, 250000)
                 WHEN level_id = 5 THEN LEAST(max_compensation, 350000)
                 ELSE max_compensation
             END) / 2 AS avg_compensation
        FROM stg_config_job_levels
        """
        comp_df = conn.execute(comp_query).df()
        comp_ranges = comp_df.set_index('level_id').to_dict('index')
    finally:
        conn.close()

    events = []
    hire_sequence_num = 0

    for level_id, level_hire_count in hires_per_level:
        for i in range(level_hire_count):
            hire_sequence_num += 1

            # Generate unique employee ID
            employee_id = f'NH_{simulation_year}_{uuid.uuid4().hex[:8]}_{hire_sequence_num:06d}'

            # Generate SSN
            employee_ssn = f'SSN-{100000000 + hire_sequence_num:09d}'

            # Assign age based on sequence (deterministic with some variation)
            age_options = [25, 28, 32, 35, 40]
            employee_age = age_options[hire_sequence_num % len(age_options)]

            # Calculate birth date
            birth_date = date(simulation_year, 1, 1) - timedelta(days=employee_age * 365)

            # Hire date evenly distributed throughout year
            hire_date = date(simulation_year, 1, 1) + timedelta(days=hire_sequence_num % 365)

            # Calculate compensation (avg with small variance)
            avg_comp = comp_ranges[level_id]['avg_compensation']
            variance_factor = 0.9 + (hire_sequence_num % 10) * 0.02
            compensation = round(avg_comp * variance_factor, 2)

            # Calculate age and tenure bands
            age_band = _calculate_age_band(employee_age)
            tenure_band = '< 2'  # All new hires start in lowest tenure band

            event = {
                'employee_id': employee_id,
                'employee_ssn': employee_ssn,
                'event_type': 'hire',
                'simulation_year': simulation_year,
                'effective_date': hire_date,
                'event_details': 'external_hire',
                'compensation_amount': compensation,
                'previous_compensation': None,
                'employee_age': employee_age,
                'employee_tenure': 0,  # New hires have 0 tenure
                'level_id': level_id,
                'age_band': age_band,
                'tenure_band': tenure_band,
                'event_probability': 1.0,  # Hire events are deterministic
                'event_category': 'hiring',
                'event_sequence': 2,  # Hires come after terminations
                'created_at': datetime.now(),
                'parameter_scenario_id': 'mvp_test',
                'parameter_source': 'dynamic',
                'data_quality_flag': 'VALID'
            }

            events.append(event)

    return events


def generate_new_hire_termination_events(
    hiring_events: List[Dict[str, Any]],
    new_hire_termination_rate: float,
    simulation_year: int,
    random_seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Generate termination events for new hires based on termination rate.

    Args:
        hiring_events: List of hiring events to select from
        new_hire_termination_rate: Rate of new hire terminations (e.g., 0.25 for 25%)
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random selection

    Returns:
        List of new hire termination event dictionaries
    """
    if random_seed is not None:
        random.seed(random_seed)

    # Calculate exact number of terminations
    num_terminations = round(len(hiring_events) * new_hire_termination_rate)

    if num_terminations == 0:
        return []

    # Sort hiring events by a deterministic but pseudo-random value
    # This ensures consistent selection while appearing random
    def pseudo_random_key(event):
        # Use last digits of employee_id for deterministic randomness
        id_hash = sum(ord(c) for c in event['employee_id'][-4:])
        return (id_hash * 17 + simulation_year * 7) % 1000

    sorted_hires = sorted(hiring_events, key=pseudo_random_key)

    # Select top N for termination
    selected_for_termination = sorted_hires[:num_terminations]

    events = []
    for hire_event in selected_for_termination:
        # Calculate remaining days in simulation year from hire date
        hire_date = hire_event['effective_date']
        year_end = date(simulation_year, 12, 31)
        days_remaining = (year_end - hire_date).days

        # Use employee_id for deterministic date variation
        id_hash = sum(ord(c) for c in hire_event['employee_id'][-3:])

        # Adaptive termination window based on hire timing
        if days_remaining < 90:  # Late-year hire (less than 3 months remaining)
            # Use shorter 1-6 month window for late hires
            max_possible = min(180, days_remaining - 1)
            days_after_hire = 30 + (id_hash % (max_possible - 29)) if max_possible > 30 else 1
        else:
            # Use standard 3-9 month window, but cap at available days
            max_possible = min(275, days_remaining - 1)
            if max_possible >= 90:
                days_after_hire = 90 + (id_hash % (max_possible - 89))
            else:
                # Fallback for edge cases
                days_after_hire = 30 + (id_hash % (max_possible - 29)) if max_possible > 30 else 1

        termination_date = hire_date + timedelta(days=days_after_hire)

        # Validate termination date doesn't exceed simulation year
        if termination_date > year_end:
            # Fallback: distribute within remaining days using hash for variation
            if days_remaining > 1:
                # Use hash to vary within available days, ensuring some spread
                fallback_days = 1 + (id_hash % max(1, days_remaining - 1))
                termination_date = hire_date + timedelta(days=fallback_days)
            else:
                # Extreme edge case: hire on Dec 31 or very close
                termination_date = hire_date + timedelta(days=1)

        event = {
            'employee_id': hire_event['employee_id'],
            'employee_ssn': hire_event['employee_ssn'],
            'event_type': 'termination',
            'simulation_year': simulation_year,
            'effective_date': termination_date,
            'event_details': 'new_hire_departure',
            'compensation_amount': hire_event['compensation_amount'],
            'previous_compensation': None,
            'employee_age': hire_event['employee_age'],
            'employee_tenure': 0,  # New hires have minimal tenure
            'level_id': hire_event['level_id'],
            'age_band': hire_event['age_band'],
            'tenure_band': '< 2',
            'event_probability': new_hire_termination_rate,
            'event_category': 'new_hire_termination',
            'event_sequence': 3,  # New hire terminations come after hires
            'created_at': datetime.now(),
            'parameter_scenario_id': 'mvp_test',
            'parameter_source': 'dynamic',
            'data_quality_flag': 'VALID'
        }

        events.append(event)

    return events


def generate_merit_events(
    simulation_year: int,
    random_seed: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Generate merit raise events for eligible employees.

    Args:
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random generation

    Returns:
        List of merit event dictionaries
    """
    if random_seed is not None:
        random.seed(random_seed)

    conn = get_connection()
    try:
        # Get active workforce from baseline (employees with 1+ years tenure)
        workforce_query = """
        SELECT
            employee_id,
            employee_ssn,
            employee_birth_date,
            employee_hire_date,
            current_compensation,
            current_age,
            current_tenure,
            level_id
        FROM int_baseline_workforce
        WHERE employment_status = 'active'
        AND current_tenure >= 1  -- At least 1 year of service for merit eligibility
        ORDER BY employee_id
        """

        workforce_df = conn.execute(workforce_query).df()

        if len(workforce_df) == 0:
            return []

        # Get merit rates from comp_levers for the simulation year
        merit_query = """
        SELECT
            job_level as level_id,
            parameter_value as merit_rate
        FROM comp_levers
        WHERE scenario_id = 'default'
        AND fiscal_year = ?
        AND event_type = 'RAISE'
        AND parameter_name = 'merit_base'
        """
        merit_df = conn.execute(merit_query, [simulation_year]).df()
        merit_rates = dict(zip(merit_df['level_id'], merit_df['merit_rate']))

        # Get COLA rate for the year
        cola_query = """
        SELECT cola_rate
        FROM config_cola_by_year
        WHERE year = ?
        """
        cola_result = conn.execute(cola_query, [simulation_year]).fetchone()
        cola_rate = cola_result[0] if cola_result else 0.025  # Default 2.5%

    finally:
        conn.close()

    events = []

    for _, employee in workforce_df.iterrows():
        # Get merit rate for employee's level
        merit_rate = merit_rates.get(employee['level_id'], 0.03)  # Default 3%

        # Calculate new salary with merit + COLA
        previous_salary = employee['current_compensation']
        total_increase = merit_rate + cola_rate
        new_salary = round(previous_salary * (1 + total_increase), 2)

        # Calculate age and tenure bands
        age_band = _calculate_age_band(employee['current_age'])
        tenure_band = _calculate_tenure_band(employee['current_tenure'])

        # Generate raise effective date (spread throughout year)
        # Use employee_id hash for consistent but varied dates
        id_hash = sum(ord(c) for c in employee['employee_id'][-4:])
        days_offset = id_hash % 365
        effective_date = date(simulation_year, 1, 1) + timedelta(days=days_offset)

        event = {
            'employee_id': employee['employee_id'],
            'employee_ssn': employee['employee_ssn'],
            'event_type': 'raise',
            'simulation_year': simulation_year,
            'effective_date': effective_date,
            'event_details': f'merit_{merit_rate:.1%}_cola_{cola_rate:.1%}',
            'compensation_amount': new_salary,
            'previous_compensation': previous_salary,
            'employee_age': employee['current_age'],
            'employee_tenure': employee['current_tenure'],
            'level_id': employee['level_id'],
            'age_band': age_band,
            'tenure_band': tenure_band,
            'event_probability': 1.0,  # Merit events are deterministic for eligible employees
            'event_category': 'merit_raise',
            'event_sequence': 4,  # Merit events come after hiring/termination events
            'created_at': datetime.now(),
            'parameter_scenario_id': 'mvp_test',
            'parameter_source': 'dynamic',
            'data_quality_flag': 'VALID'
        }

        events.append(event)

    return events


def generate_promotion_events(
    simulation_year: int,
    random_seed: Optional[int] = None,
    workforce: Optional[Any] = None,
    scenario_id: str = 'mvp_test',
    validation_callback: Optional[Callable] = None
) -> List[Dict[str, Any]]:
    """Generate promotion events using hazard-based probabilities matching legacy pipeline.

    Args:
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random generation
        workforce: Optional workforce DataFrame (for testing)
        scenario_id: Scenario identifier
        validation_callback: Optional callback for validation hooks

    Returns:
        List of promotion event dictionaries
    """
    start_time = time.time()

    if random_seed is not None:
        random.seed(random_seed)

    conn = get_connection() if workforce is None else None
    try:
        # Load hazard table configuration from seed files
        if conn:
            hazard_config = _load_promotion_hazard_config(conn, validation_callback)
        else:
            # For testing - load a mock config
            hazard_config = {
                'base_rate': 0.08,
                'level_dampener_factor': 0.15,
                'age_multipliers': {
                    '< 25': 1.0, '25-34': 1.2, '35-44': 1.1,
                    '45-54': 0.9, '55-64': 0.7, '65+': 0.5
                },
                'tenure_multipliers': {
                    '< 2': 0.8, '2-4': 1.0, '5-9': 1.2,
                    '10-19': 1.1, '20+': 0.9
                }
            }

        # Get workforce data
        if workforce is not None:
            # Use provided workforce (for testing)
            workforce_df = workforce
            # Rename columns if needed for compatibility
            if 'level' in workforce_df.columns and 'level_id' not in workforce_df.columns:
                workforce_df['level_id'] = workforce_df['level']
            if 'base_salary' in workforce_df.columns and 'employee_gross_compensation' not in workforce_df.columns:
                workforce_df['employee_gross_compensation'] = workforce_df['base_salary']
            if 'age' in workforce_df.columns and 'current_age' not in workforce_df.columns:
                workforce_df['current_age'] = workforce_df['age']
            if 'tenure' in workforce_df.columns and 'current_tenure' not in workforce_df.columns:
                workforce_df['current_tenure'] = workforce_df['tenure']
            # Add missing columns with defaults
            if 'employee_ssn' not in workforce_df.columns:
                workforce_df['employee_ssn'] = workforce_df['employee_id'].apply(lambda x: f'SSN-{x}')
            if 'employee_birth_date' not in workforce_df.columns:
                workforce_df['employee_birth_date'] = date.today()
            if 'employee_hire_date' not in workforce_df.columns:
                workforce_df['employee_hire_date'] = date.today()
        else:
            # Get active workforce from database
            try:
                # Try to use int_workforce_previous_year first
                workforce_query = """
                SELECT
                    employee_id,
                    employee_ssn,
                    employee_birth_date,
                    employee_hire_date,
                    employee_gross_compensation,
                    current_age,
                    current_tenure,
                    level_id
                FROM int_workforce_previous_year
                WHERE employment_status = 'active'
                AND current_tenure >= 1  -- Minimum 1 year tenure
                AND level_id < 5  -- Can't promote beyond max level
                AND current_age < 65  -- No promotions near retirement
                ORDER BY employee_id
                """
                workforce_df = conn.execute(workforce_query).df()
                if validation_callback:
                    validation_callback("workforce_source", True, "int_workforce_previous_year")
            except Exception as e:
                # Fallback to baseline workforce if previous year doesn't exist
                print(f"⚠️  Failed to load int_workforce_previous_year: {e}")
                workforce_query = """
                SELECT
                    employee_id,
                    employee_ssn,
                    employee_birth_date,
                    employee_hire_date,
                    current_compensation as employee_gross_compensation,
                    current_age,
                    current_tenure,
                    level_id
                FROM int_baseline_workforce
                WHERE employment_status = 'active'
                AND current_tenure >= 1  -- Minimum 1 year tenure
                AND level_id < 5  -- Can't promote beyond max level
                AND current_age < 65  -- No promotions near retirement
                ORDER BY employee_id
                """
                workforce_df = conn.execute(workforce_query).df()
                if validation_callback:
                    validation_callback("workforce_source", True, "int_baseline_workforce")

        print(f"🔍 DEBUG: Found {len(workforce_df)} employees eligible for promotion")

        if len(workforce_df) == 0:
            print("❌ No eligible employees found for promotion")
            return []

    finally:
        if conn:
            conn.close()

    events = []
    promotion_decisions = []

    for _, employee in workforce_df.iterrows():
        # Calculate age and tenure bands (matches legacy logic)
        age_band = _calculate_age_band(employee['current_age'])
        tenure_band = _calculate_tenure_band(employee['current_tenure'])

        # Calculate hazard-based promotion probability
        promotion_rate = _calculate_promotion_probability(
            employee['level_id'], age_band, tenure_band, hazard_config
        )

        # Generate random value using legacy hash-based approach
        employee_id_str = str(employee['employee_id'])
        random_value = get_legacy_random_value(employee_id_str, simulation_year, random_seed or 42)

        # Track promotion decision for debugging
        promotion_decisions.append({
            'employee_id': employee['employee_id'],
            'level_id': employee['level_id'],
            'age_band': age_band,
            'tenure_band': tenure_band,
            'promotion_rate': promotion_rate,
            'random_value': random_value,
            'promoted': random_value < promotion_rate
        })

        # Check if employee gets promoted based on probability
        if random_value < promotion_rate:
            # Calculate promotion salary increase (15-25% increase)
            # Use employee ID for deterministic but varied increase
            id_hash_salary = sum(ord(c) for c in employee_id_str[-4:])
            increase_variation = ((id_hash_salary % 100) / 1000.0)  # 0-0.1
            salary_multiplier = 1.15 + increase_variation  # 1.15-1.25

            previous_salary = employee['employee_gross_compensation']
            new_salary = round(previous_salary * salary_multiplier, 2)

            # Generate promotion effective date (spread throughout year)
            days_offset = (id_hash_salary + simulation_year) % 365
            effective_date = date(simulation_year, 1, 1) + timedelta(days=days_offset)

            event = {
                'employee_id': employee['employee_id'],
                'employee_ssn': employee['employee_ssn'],
                'event_type': 'promotion',
                'simulation_year': simulation_year,
                'effective_date': effective_date,
                'event_details': f'level_{employee["level_id"]}_to_{employee["level_id"] + 1}',
                'compensation_amount': new_salary,
                'previous_compensation': previous_salary,
                'employee_age': employee['current_age'],
                'employee_tenure': employee['current_tenure'],
                'level_id': employee['level_id'] + 1,  # Promoted to next level
                'age_band': age_band,
                'tenure_band': tenure_band,
                'event_probability': promotion_rate,
                'event_category': 'promotion',
                'event_sequence': 5,  # Promotions come after merit events
                'created_at': datetime.now(),
                'parameter_scenario_id': scenario_id,
                'parameter_source': 'dynamic',
                'data_quality_flag': 'VALID'
            }

            # Validate event structure before adding
            required_fields = {'employee_id', 'employee_ssn', 'event_type', 'simulation_year',
                             'effective_date', 'level_id', 'compensation_amount', 'previous_compensation'}
            if not all(field in event for field in required_fields):
                missing = required_fields - set(event.keys())
                raise ValueError(f"Promotion event missing required fields: {missing}")

            events.append(event)

    # Debug summary
    promoted_count = sum(1 for d in promotion_decisions if d['promoted'])
    print(f"🔍 DEBUG: Promotion decisions made for {len(promotion_decisions)} employees")
    print(f"   Total promoted: {promoted_count}")

    # Show promotion rate by level
    import pandas as pd
    decisions_df = pd.DataFrame(promotion_decisions)
    level_summary = decisions_df.groupby('level_id').agg({
        'promoted': ['count', 'sum'],
        'promotion_rate': 'first',
        'random_value': ['min', 'max', 'mean']
    }).round(4)

    print("📊 Promotion results by level:")
    for level_id in level_summary.index:
        total = level_summary.loc[level_id, ('promoted', 'count')]
        promoted = level_summary.loc[level_id, ('promoted', 'sum')]
        prob = level_summary.loc[level_id, ('promotion_rate', 'first')]
        min_rand = level_summary.loc[level_id, ('random_value', 'min')]
        max_rand = level_summary.loc[level_id, ('random_value', 'max')]
        mean_rand = level_summary.loc[level_id, ('random_value', 'mean')]
        actual_rate = promoted / total if total > 0 else 0
        print(f"   Level {level_id}: {promoted}/{total} promoted ({actual_rate:.1%} actual vs {prob:.1%} expected)")
        print(f"     Random values: min={min_rand:.3f}, max={max_rand:.3f}, mean={mean_rand:.3f}")

    # Performance metrics
    generation_time = time.time() - start_time
    print(f"\n⏱️  Promotion event generation completed in {generation_time:.3f} seconds")
    print(f"   Performance: {len(events) / generation_time:.1f} events/second")

    # Final validation callback
    if validation_callback:
        validation_callback("promotion_generation_complete", True, {
            "total_eligible": len(workforce_df),
            "total_promoted": len(events),
            "generation_time": generation_time,
            "events_per_second": len(events) / generation_time if generation_time > 0 else 0
        })

    return events


def validate_events_in_database(simulation_year: int, table_name: str = "fct_yearly_events") -> None:
    """Validate events stored in database.

    Args:
        simulation_year: Year to validate events for
        table_name: Name of table to validate
    """
    conn = get_connection()
    try:
        # Check event counts
        count_query = f"SELECT COUNT(*) FROM {table_name} WHERE simulation_year = ?"
        count_result = conn.execute(count_query, [simulation_year]).fetchone()
        total_events = count_result[0]

        # Check by event type
        type_query = f"""
        SELECT event_type, COUNT(*) as count
        FROM {table_name}
        WHERE simulation_year = ?
        GROUP BY event_type
        ORDER BY count DESC
        """
        type_results = conn.execute(type_query, [simulation_year]).fetchall()

        # Check data quality
        quality_query = f"""
        SELECT data_quality_flag, COUNT(*) as count
        FROM {table_name}
        WHERE simulation_year = ?
        GROUP BY data_quality_flag
        """
        quality_results = conn.execute(quality_query, [simulation_year]).fetchall()

        print(f"\n📊 EVENT VALIDATION RESULTS for {table_name}")
        print(f"   Total events: {total_events}")
        print(f"   Events by type:")
        for event_type, count in type_results:
            print(f"     • {event_type}: {count}")
        print(f"   Data quality:")
        for flag, count in quality_results:
            print(f"     • {flag}: {count}")

    finally:
        conn.close()


def generate_and_store_all_events(
    calc_result: Dict[str, Any],
    simulation_year: int,
    random_seed: Optional[int] = None,
    table_name: str = "fct_yearly_events"
) -> None:
    """Generate and store all event types based on workforce calculations.

    This is the main function that orchestrates the generation of all event types:
    1. Experienced terminations
    2. New hires
    3. New hire terminations

    Args:
        calc_result: Workforce calculation results from calculate_workforce_requirements
        simulation_year: Year for the simulation
        random_seed: Optional seed for reproducible random generation
        table_name: Name of table to store events in
    """
    print(f"\n🎯 GENERATING ALL SIMULATION EVENTS for year {simulation_year}")
    print(f"   Using random seed: {random_seed}")

    all_events = []

    # 1. Generate experienced terminations
    print(f"\n📋 Generating {calc_result['experienced_terminations']} experienced termination events...")
    termination_events = generate_experienced_termination_events(
        num_terminations=calc_result['experienced_terminations'],
        simulation_year=simulation_year,
        random_seed=random_seed
    )
    all_events.extend(termination_events)
    print(f"   ✅ Generated {len(termination_events)} termination events")

    # 2. Generate new hires
    print(f"\n📋 Generating {calc_result['total_hires_needed']} hiring events...")
    hiring_events = generate_hiring_events(
        num_hires=calc_result['total_hires_needed'],
        simulation_year=simulation_year,
        random_seed=random_seed if random_seed is None else random_seed + 1
    )
    all_events.extend(hiring_events)
    print(f"   ✅ Generated {len(hiring_events)} hiring events")

    # 3. Generate new hire terminations
    new_hire_term_rate = calc_result.get('new_hire_termination_rate', 0.25)
    expected_nh_terms = calc_result['expected_new_hire_terminations']
    print(f"\n📋 Generating ~{expected_nh_terms} new hire termination events (rate: {new_hire_term_rate:.1%})...")
    nh_termination_events = generate_new_hire_termination_events(
        hiring_events=hiring_events,
        new_hire_termination_rate=new_hire_term_rate,
        simulation_year=simulation_year,
        random_seed=random_seed if random_seed is None else random_seed + 2
    )
    all_events.extend(nh_termination_events)
    print(f"   ✅ Generated {len(nh_termination_events)} new hire termination events")

    # 4. Generate merit raise events
    print(f"\n📋 Generating merit raise events for eligible employees...")
    merit_events = generate_merit_events(
        simulation_year=simulation_year,
        random_seed=random_seed if random_seed is None else random_seed + 3
    )
    all_events.extend(merit_events)
    print(f"   ✅ Generated {len(merit_events)} merit raise events")

    # 5. Generate promotion events
    print(f"\n📋 Generating promotion events for eligible employees...")
    promotion_events = generate_promotion_events(
        simulation_year=simulation_year,
        random_seed=random_seed if random_seed is None else random_seed + 4
    )
    all_events.extend(promotion_events)
    print(f"   ✅ Generated {len(promotion_events)} promotion events")

    # Store all events
    print(f"\n💾 Storing all {len(all_events)} events in database...")
    store_events_in_database(all_events, table_name)

    # Summary
    print(f"\n✅ EVENT GENERATION SUMMARY:")
    print(f"   • Experienced terminations: {len(termination_events)}")
    print(f"   • New hires: {len(hiring_events)}")
    print(f"   • New hire terminations: {len(nh_termination_events)}")
    print(f"   • Merit raises: {len(merit_events)}")
    print(f"   • Promotions: {len(promotion_events)}")
    print(f"   • Total events: {len(all_events)}")
    print(f"   • Net workforce change: {len(hiring_events) - len(termination_events) - len(nh_termination_events)}")
    print(f"   • Expected net change: {calc_result['net_hiring_impact'] - calc_result['experienced_terminations']}")
