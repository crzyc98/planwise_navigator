"""
Modular workforce calculation utilities for MVP orchestrator.

This module provides focused calculation functions that determine workforce
requirements based on configuration parameters, extracted from the legacy
monolithic pipeline for use in the modular MVP orchestrator.
"""

import math
from typing import Dict, Any


def calculate_workforce_requirements(
    current_workforce: int,
    target_growth_rate: float,
    total_termination_rate: float,
    new_hire_termination_rate: float
) -> Dict[str, Any]:
    """
    Calculate workforce requirements for the next simulation year.

    This function implements the exact same mathematical formula used in the
    legacy monolithic pipeline (_log_hiring_calculation_debug function) but
    as a focused, reusable utility for the MVP orchestrator.

    Args:
        current_workforce: Number of active employees at start of year
        target_growth_rate: Desired growth rate (e.g., 0.03 for 3%)
        total_termination_rate: Expected termination rate (e.g., 0.12 for 12%)
        new_hire_termination_rate: Expected termination rate for new hires (e.g., 0.25 for 25%)

    Returns:
        Dictionary containing:
        - experienced_terminations: Number of experienced employee terminations needed
        - growth_amount: Raw growth amount needed (float)
        - total_hires_needed: Total gross hires needed to hit growth target
        - expected_new_hire_terminations: Expected terminations among new hires
        - net_hiring_impact: Net workforce change after all events

    Example:
        >>> calculate_workforce_requirements(
        ...     current_workforce=10000,
        ...     target_growth_rate=0.03,
        ...     total_termination_rate=0.12,
        ...     new_hire_termination_rate=0.25
        ... )
        {
            'experienced_terminations': 1200,
            'growth_amount': 300.0,
            'total_hires_needed': 2000,
            'expected_new_hire_terminations': 500,
            'net_hiring_impact': 1500
        }
    """
    # Apply exact formula from int_hiring_events.sql and _log_hiring_calculation_debug
    experienced_terminations = math.ceil(current_workforce * total_termination_rate)
    growth_amount = current_workforce * target_growth_rate
    total_hires_needed = math.ceil(
        (experienced_terminations + growth_amount) / (1 - new_hire_termination_rate)
    )
    expected_new_hire_terminations = round(total_hires_needed * new_hire_termination_rate)

    # Calculate net impact
    net_hiring_impact = total_hires_needed - expected_new_hire_terminations

    return {
        'current_workforce': current_workforce,
        'experienced_terminations': experienced_terminations,
        'growth_amount': growth_amount,
        'total_hires_needed': total_hires_needed,
        'expected_new_hire_terminations': expected_new_hire_terminations,
        'net_hiring_impact': net_hiring_impact,
        'formula_details': {
            'experienced_formula': f'CEIL({current_workforce} * {total_termination_rate}) = {experienced_terminations}',
            'growth_formula': f'{current_workforce} * {target_growth_rate} = {growth_amount}',
            'hiring_formula': f'CEIL(({experienced_terminations} + {growth_amount}) / (1 - {new_hire_termination_rate})) = {total_hires_needed}',
            'new_hire_term_formula': f'ROUND({total_hires_needed} * {new_hire_termination_rate}) = {expected_new_hire_terminations}'
        }
    }


def calculate_workforce_requirements_from_config(
    current_workforce: int,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convenience function that takes a config dictionary and extracts the required parameters.

    Args:
        current_workforce: Number of active employees at start of year
        config: Configuration dictionary containing workforce parameters

    Returns:
        Same as calculate_workforce_requirements()

    Example:
        >>> config = {
        ...     'target_growth_rate': 0.03,
        ...     'total_termination_rate': 0.12,
        ...     'new_hire_termination_rate': 0.25
        ... }
        >>> calculate_workforce_requirements_from_config(10000, config)
    """
    return calculate_workforce_requirements(
        current_workforce=current_workforce,
        target_growth_rate=config['target_growth_rate'],
        total_termination_rate=config['total_termination_rate'],
        new_hire_termination_rate=config['new_hire_termination_rate']
    )


def validate_workforce_calculation_inputs(
    current_workforce: int,
    target_growth_rate: float,
    total_termination_rate: float,
    new_hire_termination_rate: float
) -> Dict[str, Any]:
    """
    Validate inputs for workforce calculations to catch configuration errors early.

    Args:
        current_workforce: Number of active employees
        target_growth_rate: Growth rate (should be reasonable, e.g., -0.1 to 0.2)
        total_termination_rate: Termination rate (should be 0.0 to 1.0)
        new_hire_termination_rate: New hire termination rate (should be 0.0 to 1.0)

    Returns:
        Dictionary with validation results and any warnings
    """
    validation_results = {
        'valid': True,
        'warnings': [],
        'errors': []
    }

    # Validate workforce count
    if current_workforce <= 0:
        validation_results['errors'].append(f"Current workforce must be positive, got {current_workforce}")
        validation_results['valid'] = False
    elif current_workforce < 100:
        validation_results['warnings'].append(f"Current workforce seems small: {current_workforce}")

    # Validate growth rate
    if not -0.5 <= target_growth_rate <= 0.5:
        validation_results['warnings'].append(f"Growth rate seems extreme: {target_growth_rate:.1%}")

    # Validate termination rates
    if not 0.0 <= total_termination_rate <= 1.0:
        validation_results['errors'].append(f"Total termination rate must be 0-100%, got {total_termination_rate:.1%}")
        validation_results['valid'] = False
    elif total_termination_rate > 0.5:
        validation_results['warnings'].append(f"Total termination rate seems high: {total_termination_rate:.1%}")

    if not 0.0 <= new_hire_termination_rate <= 1.0:
        validation_results['errors'].append(f"New hire termination rate must be 0-100%, got {new_hire_termination_rate:.1%}")
        validation_results['valid'] = False
    elif new_hire_termination_rate > 0.8:
        validation_results['warnings'].append(f"New hire termination rate seems high: {new_hire_termination_rate:.1%}")

    # Check for mathematical edge cases
    if new_hire_termination_rate >= 1.0:
        validation_results['errors'].append("New hire termination rate cannot be 100% or higher (would create infinite hiring loop)")
        validation_results['valid'] = False

    return validation_results
