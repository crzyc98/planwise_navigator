"""Short-lived, path-bound tickets for browser artifact downloads."""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, status

from ..config import get_settings

_LOCAL_SECRET = secrets.token_bytes(32)
TICKET_TTL_SECONDS = 60


def _sign(payload: bytes) -> bytes:
    secret = (get_settings().api_token or "").encode() or _LOCAL_SECRET
    return hmac.new(secret, payload, hashlib.sha256).digest()


def create_artifact_ticket(scenario_id: str, artifact_path: str) -> str:
    payload = json.dumps(
        [scenario_id, artifact_path, int(time.time()) + TICKET_TTL_SECONDS],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload + _sign(payload)).decode().rstrip("=")


def verify_artifact_ticket(ticket: str) -> tuple[str, str]:
    try:
        encoded = ticket + "=" * (-len(ticket) % 4)
        signed = base64.b64decode(encoded, altchars=b"-_", validate=True)
        payload, signature = signed[:-32], signed[-32:]
        if not hmac.compare_digest(_sign(payload), signature):
            raise ValueError("Invalid signature")
        scenario_id, artifact_path, expires_at = json.loads(payload)
        if not isinstance(scenario_id, str) or not isinstance(artifact_path, str):
            raise ValueError("Invalid path")
        if not isinstance(expires_at, int) or time.time() > expires_at:
            raise ValueError("Expired ticket")
        return scenario_id, artifact_path
    except (ValueError, TypeError, binascii.Error):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired artifact download link",
        ) from None
