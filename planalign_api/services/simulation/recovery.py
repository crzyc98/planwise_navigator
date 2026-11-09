"""Clean up simulations interrupted by an API restart."""

import logging

from ...storage.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

# Run state lives in memory, so at startup none of these can still be live.
_INTERRUPTED_STATUSES = frozenset({"queued", "running"})


def fail_interrupted_simulations(storage: WorkspaceStorage) -> int:
    """Mark every scenario left mid-run by a restart as failed.

    Assumes a single API process (Studio runs one uvicorn worker); a second
    worker starting up would wrongly fail the first worker's live runs.
    An unreadable workspace is logged and skipped so it cannot stop the API
    from starting. Returns the number of scenarios marked failed.
    """
    failed = 0
    for workspace in storage.list_workspaces():
        try:
            failed += _fail_interrupted_in(storage, workspace.id)
        except Exception:
            logger.exception(
                "Could not check workspace %s for interrupted runs", workspace.id
            )
    return failed


def _fail_interrupted_in(storage: WorkspaceStorage, workspace_id: str) -> int:
    interrupted = [
        scenario
        for scenario in storage.list_scenarios(workspace_id)
        if scenario.status in _INTERRUPTED_STATUSES
    ]
    for scenario in interrupted:
        storage.update_scenario_status(workspace_id, scenario.id, "failed")
        logger.warning(
            "Marked scenario %s (%s) failed: the API restarted while it was %s",
            scenario.id,
            scenario.name,
            scenario.status,
        )
    return len(interrupted)
