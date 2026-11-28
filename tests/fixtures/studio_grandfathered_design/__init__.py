"""Plan-design payload produced by Studio's grandfathered-design editor (#646).

``payload.json`` is the exact output of ``buildConfigPayload`` for a match-and-core
change with a 2015-01-01 hire-date cutoff. The Studio test
``grandfatheredDesign.test.ts`` fails if the editor stops producing it, so the
engine tests below exercise what Studio actually sends.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from planalign_orchestrator.config import (
    PlanDesignAssignmentSettings,
    PlanDesignParametersMap,
    SimulationConfig,
)

PAYLOAD_PATH = Path(__file__).with_name("payload.json")
CUTOFF = "2015-01-01"
EXISTING_DESIGN = "existing_employees"
NEW_HIRE_DESIGN = "new_hires"


def load_studio_payload() -> dict[str, Any]:
    """Return the Studio plan-design payload."""
    payload: dict[str, Any] = json.loads(PAYLOAD_PATH.read_text())
    return payload


def apply_studio_payload(config: SimulationConfig) -> SimulationConfig:
    """Return a copy of ``config`` running the Studio payload's two designs."""
    payload = load_studio_payload()
    configured = config.model_copy(deep=True)
    configured.plan_design_id = None
    configured.plan_design_assignment = PlanDesignAssignmentSettings.model_validate(
        payload["plan_design_assignment"]
    )
    configured.plan_design_parameters = PlanDesignParametersMap.model_validate(
        payload["plan_design_parameters"]
    )
    return configured
