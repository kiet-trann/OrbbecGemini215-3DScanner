"""Capture-quality summaries used before a live markerless scan."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CaptureDiagnostic:
    color_visible: bool
    alignment_target: str
    depth_valid_ratio: float


def summarize_capture_visibility(
    color_bgr: np.ndarray,
    alignment_target: str,
    depth_raw: np.ndarray,
    *,
    depth_scale_mm: float,
    min_depth_m: float,
    max_depth_m: float,
) -> CaptureDiagnostic:
    color = np.asarray(color_bgr, dtype=np.uint8)
    depth_m = np.asarray(depth_raw, dtype=np.float32) * float(depth_scale_mm) * 0.001
    valid_depth = (depth_m >= float(min_depth_m)) & (depth_m <= float(max_depth_m))
    return CaptureDiagnostic(
        color_visible=bool(color.size and float(np.mean(color)) > 5.0),
        alignment_target=str(alignment_target),
        depth_valid_ratio=float(np.mean(valid_depth)) if depth_m.size else 0.0,
    )
