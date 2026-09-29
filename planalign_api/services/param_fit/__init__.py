"""Studio parameter fit & backtest jobs (#588).

``history`` stores uploaded census snapshot sets, ``jobs`` persists job
records, ``runner`` executes the ``planalign fit|backtest`` CLI as cancellable
subprocesses, ``results`` reads packs back, and ``apply`` turns a reviewed
pack into a new scenario. :class:`ParamFitService` is the facade routers use.
"""

from .history import UploadedFile
from .service import ParamFitError, ParamFitService

__all__ = ["ParamFitError", "ParamFitService", "UploadedFile"]
