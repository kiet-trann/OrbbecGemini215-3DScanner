"""Point cloud merge helpers."""

import numpy as np


def transform_points(points_xyz: np.ndarray, camera_to_world: np.ndarray) -> np.ndarray:
    points_h = np.c_[points_xyz, np.ones(len(points_xyz))]
    transformed = (camera_to_world @ points_h.T).T
    return transformed[:, :3]
