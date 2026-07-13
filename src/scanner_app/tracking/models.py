"""Contracts shared by markerless tracking components."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np


class TrackingState(Enum):
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    DEGRADED = "degraded"
    LOST = "lost"


@dataclass(frozen=True)
class TrackingMetrics:
    fitness: float
    rmse_m: float
    translation_m: float
    rotation_deg: float
    depth_valid_ratio: float


@dataclass(frozen=True)
class TrackingResult:
    state: TrackingState
    camera_to_world: np.ndarray
    metrics: TrackingMetrics
    accepted: bool
    keyframe: bool
    reason: str | None = None


class PoseTracker(Protocol):
    def initialize(self, packet, processed_depth) -> TrackingResult: ...

    def track(self, packet, processed_depth) -> TrackingResult: ...
