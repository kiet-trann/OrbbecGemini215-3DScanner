"""ArUco marker tracking placeholder."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MarkerPose:
    marker_id: int
    rvec: np.ndarray
    tvec: np.ndarray


def detect_markers(_color_bgr: np.ndarray) -> list[MarkerPose]:
    raise NotImplementedError("Implement with cv2.aruco marker detection.")
