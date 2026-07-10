"""Object ROI estimation from processed central depth."""

from dataclasses import dataclass

import numpy as np

from scanner_app.camera.models import CameraIntrinsics
from scanner_app.processing.depth_pipeline import ProcessedDepth


@dataclass(frozen=True)
class ObjectRoi:
    center_camera_m: np.ndarray
    min_bound: np.ndarray
    max_bound: np.ndarray


def estimate_object_roi(
    processed_depth: ProcessedDepth,
    intrinsics: CameraIntrinsics,
    extent_m: float = 0.35,
    min_valid_pixels: int = 20,
) -> ObjectRoi:
    if extent_m <= 0:
        raise ValueError("ROI extent must be positive.")
    if min_valid_pixels <= 0:
        raise ValueError("Minimum valid pixels must be positive.")

    height, width = processed_depth.depth_m.shape
    y0, y1 = int(height * 0.4), int(height * 0.6)
    x0, x1 = int(width * 0.4), int(width * 0.6)
    central = processed_depth.depth_m[y0:y1, x0:x1]
    valid = central[central > 0]
    if valid.size < min_valid_pixels:
        raise ValueError(
            f"At least {min_valid_pixels} valid central depth pixels are required."
        )

    z = float(np.median(valid))
    u = 0.5 * (x0 + x1 - 1)
    v = 0.5 * (y0 + y1 - 1)
    center = np.array(
        [
            (u - intrinsics.cx) * z / intrinsics.fx,
            (v - intrinsics.cy) * z / intrinsics.fy,
            z,
        ],
        dtype=np.float32,
    )
    half_extent = 0.5 * float(extent_m)
    return ObjectRoi(
        center_camera_m=center,
        min_bound=center - half_extent,
        max_bound=center + half_extent,
    )

