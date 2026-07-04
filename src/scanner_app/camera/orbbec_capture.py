"""Orbbec Gemini 215 capture adapter.

The implementation will wrap pyorbbecsdk2 and expose a small stable interface
for the rest of the prototype.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


@dataclass(frozen=True)
class RgbdFrame:
    color: np.ndarray | None
    depth: np.ndarray
    timestamp_ms: float


class OrbbecCapture:
    """Thin wrapper around pyorbbecsdk2 for Gemini 215."""

    def __init__(self) -> None:
        self._pipeline: Any | None = None

    def start(self) -> None:
        raise NotImplementedError("Wire this to pyorbbecsdk2 pipeline startup.")

    def read(self) -> RgbdFrame:
        raise NotImplementedError("Read synchronized RGB-D frames from Gemini 215.")

    def intrinsics(self) -> CameraIntrinsics:
        raise NotImplementedError("Return camera intrinsics from Orbbec SDK.")

    def depth_scale(self) -> float:
        raise NotImplementedError("Return depth scale from Orbbec SDK.")

    def stop(self) -> None:
        raise NotImplementedError("Stop Orbbec pipeline safely.")
