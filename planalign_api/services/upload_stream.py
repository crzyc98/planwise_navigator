"""Bounded streaming helpers for multipart uploads."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

UPLOAD_CHUNK_BYTES = 1024 * 1024


async def stream_upload_to_tempfile(
    file: UploadFile,
    *,
    suffix: str,
    max_file_bytes: int,
    request_bytes_so_far: int = 0,
    max_request_bytes: int | None = None,
) -> tuple[Path, int]:
    """Write an upload to disk without retaining the complete body in memory.

    The partially written file is removed if a size limit is exceeded or the
    request is interrupted.
    """
    temp_path: Path | None = None
    file_size = 0
    completed = False

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                file_size += len(chunk)
                if file_size > max_file_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=_size_limit_detail("File", max_file_bytes),
                    )
                if (
                    max_request_bytes is not None
                    and request_bytes_so_far + file_size > max_request_bytes
                ):
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=_size_limit_detail(
                            "Total upload size", max_request_bytes
                        ),
                    )
                temp_file.write(chunk)

        assert temp_path is not None
        completed = True
        return temp_path, file_size
    finally:
        if not completed and temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _size_limit_detail(scope: str, limit_bytes: int) -> str:
    """Format a consistent upload-size error message."""
    limit_megabytes = limit_bytes // (1024 * 1024)
    return f"{scope} exceeds {limit_megabytes}MB limit"
