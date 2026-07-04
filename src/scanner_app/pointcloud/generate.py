"""Point cloud generation from RGB-D frames."""

import numpy as np

from scanner_app.camera.orbbec_capture import CameraIntrinsics


def depth_to_xyz(depth_m: np.ndarray, intrinsics: CameraIntrinsics) -> np.ndarray:
    height, width = depth_m.shape
    u, v = np.meshgrid(np.arange(width), np.arange(height))

    z = depth_m
    x = (u - intrinsics.cx) * z / intrinsics.fx
    y = (v - intrinsics.cy) * z / intrinsics.fy

    xyz = np.stack((x, y, z), axis=-1)
    return xyz[z > 0]
