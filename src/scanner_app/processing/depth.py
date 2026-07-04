"""Depth preprocessing helpers."""

import numpy as np


def depth_to_meters(depth_raw: np.ndarray, depth_scale: float) -> np.ndarray:
    return depth_raw.astype(np.float32) * float(depth_scale)


def filter_depth_range(
    depth_m: np.ndarray,
    min_depth_m: float = 0.15,
    max_depth_m: float = 0.70,
) -> np.ndarray:
    filtered = depth_m.copy()
    invalid = (filtered < min_depth_m) | (filtered > max_depth_m)
    filtered[invalid] = 0.0
    return filtered
