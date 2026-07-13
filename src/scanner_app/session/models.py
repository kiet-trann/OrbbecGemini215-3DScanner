"""Session state and immutable UI snapshot contracts."""

from dataclasses import dataclass
from enum import Enum

import numpy as np

from scanner_app.tracking.models import TrackingResult


class ScanSessionState(Enum):
    IDLE = "idle"
    CALIBRATING = "calibrating"
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass(frozen=True)
class ScannerSnapshot:
    state: ScanSessionState
    color_bgr: np.ndarray | None
    tracking: TrackingResult | None
    preview_geometry: object | None
    capture_fps: float
    tracking_fps: float
    preview_fps: float
    depth_valid_ratio: float
    coverage_ratio: float
    trajectory_points: tuple[np.ndarray, ...]
    message: str | None = None

    @classmethod
    def idle(cls) -> "ScannerSnapshot":
        return cls(
            state=ScanSessionState.IDLE,
            color_bgr=None,
            tracking=None,
            preview_geometry=None,
            capture_fps=0.0,
            tracking_fps=0.0,
            preview_fps=0.0,
            depth_valid_ratio=0.0,
            coverage_ratio=0.0,
            trajectory_points=tuple(),
            message=None,
        )

