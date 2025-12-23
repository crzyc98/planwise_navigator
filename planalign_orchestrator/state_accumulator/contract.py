"""
StateAccumulatorContract - Pydantic model for temporal state accumulator contracts.

Defines the contract that all temporal state accumulator models must implement.
Used for registration and validation of accumulator models that follow the
Year N depends on Year N-1 pattern.

Example:
    contract = StateAccumulatorContract(
        model_name="int_enrollment_state_accumulator",
        table_name="int_enrollment_state_accumulator",
        start_year_source="int_baseline_workforce",
        description="Tracks enrollment state across years"
    )
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class StateAccumulatorContract(BaseModel):
    """Contract defining temporal state accumulator requirements.

    All state accumulator models that follow the Year N depends on Year N-1
    pattern must be registered with a contract specifying their temporal
    dependency configuration.

    Note: model_config is set to allow 'model_' prefix in field names since
    'model_name' is a domain-specific term referring to dbt model names.

    Attributes:
        model_name: dbt model name implementing the accumulator pattern.
                   Must start with 'int_' prefix (intermediate model convention).
        table_name: Database table name for the accumulator.
                   Usually identical to model_name.
        prior_year_column: Column used for year-based filtering.
                          Defaults to 'simulation_year'.
        start_year_source: Model providing initial state for the start year.
                          For start year, this model replaces the prior year self-reference.
        description: Human-readable description of the accumulator's purpose.

    Example:
        >>> contract = StateAccumulatorContract(
        ...     model_name="int_enrollment_state_accumulator",
        ...     table_name="int_enrollment_state_accumulator",
        ...     start_year_source="int_baseline_workforce",
        ...     description="Tracks enrollment state"
        ... )
        >>> contract.model_name
        'int_enrollment_state_accumulator'
    """

    model_config = {"protected_namespaces": ()}

    model_name: str = Field(
        ...,
        description="dbt model name implementing the accumulator pattern"
    )
    table_name: str = Field(
        ...,
        description="Database table name for the accumulator"
    )
    prior_year_column: str = Field(
        default="simulation_year",
        description="Column used for year-based filtering"
    )
    start_year_source: str = Field(
        ...,
        description="Model providing initial state for start year"
    )
    description: str = Field(
        default="",
        description="Human-readable description of the accumulator"
    )
    required_for_year_validation: bool = Field(
        default=True,
        description="If True, this accumulator MUST have rows for year N-1 "
                    "before year N can execute. Set to False for accumulators "
                    "that may legitimately have 0 rows (e.g., only tracking "
                    "enrolled employees when no one has enrolled yet)."
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate model_name is non-empty and starts with 'int_' prefix.

        Args:
            v: The model name value to validate

        Returns:
            The validated model name

        Raises:
            ValueError: If model_name is empty or doesn't start with 'int_'
        """
        if not v:
            raise ValueError("model_name cannot be empty")
        if not v.startswith("int_"):
            raise ValueError(
                f"model_name must start with 'int_' prefix (got '{v}'). "
                "State accumulators must be intermediate dbt models."
            )
        return v

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        """Validate table_name is non-empty.

        Args:
            v: The table name value to validate

        Returns:
            The validated table name

        Raises:
            ValueError: If table_name is empty
        """
        if not v:
            raise ValueError("table_name cannot be empty")
        return v

    @field_validator("start_year_source")
    @classmethod
    def validate_start_year_source(cls, v: str) -> str:
        """Validate start_year_source is non-empty.

        Args:
            v: The start year source model name

        Returns:
            The validated start year source

        Raises:
            ValueError: If start_year_source is empty
        """
        if not v:
            raise ValueError("start_year_source cannot be empty")
        return v

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return (
            f"StateAccumulatorContract("
            f"model_name='{self.model_name}', "
            f"table_name='{self.table_name}', "
            f"prior_year_column='{self.prior_year_column}', "
            f"start_year_source='{self.start_year_source}')"
        )

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return f"{self.model_name} -> {self.table_name}"
