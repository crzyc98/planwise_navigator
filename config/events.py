# filename: config/events.py
"""
Compatibility shim - this file is superseded by the config/events/ package.

Python imports the config/events/ directory as a package, so this file
is no longer needed for backward compatibility. It's kept for reference
and will be removed in a future cleanup.

All imports should work via:
    from config.events import SimulationEvent, HirePayload, WorkforceEventFactory
"""

# This file is not imported by Python when config/events/ package exists.
# The package __init__.py handles all exports.
