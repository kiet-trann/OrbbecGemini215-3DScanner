"""Point cloud generation from RGB-D frames."""

from dataclasses import dataclass

import numpy as np

from scanner_app.camera.orbbec_capture import CameraIntrinsics, RgbdFrame
from scanner_app.processing.depth import filter_depth_range


@dataclass(frozen=True)
class PointCloudData:
    points_xyz: np.ndarray
    colors_rgb: np.ndarray | None = None


def depth_to_xyz(depth_m: np.ndarray, intrinsics: CameraIntrinsics) -> np.ndarray:
    height, width = depth_m.shape
    u, v = np.meshgrid(np.arange(width), np.arange(height))

    z = depth_m
    x = (u - intrinsics.cx) * z / intrinsics.fx
    y = (v - intrinsics.cy) * z / intrinsics.fy

    xyz = np.stack((x, y, z), axis=-1)
    return xyz[z > 0]


def rgbd_frame_to_point_cloud(
    frame: RgbdFrame,
    intrinsics: CameraIntrinsics,
    min_depth_m: float = 0.15,
    max_depth_m: float = 1.50,
) -> PointCloudData:
    depth_m = frame.depth_mm * 0.001
    filtered_depth = filter_depth_range(depth_m, min_depth_m=min_depth_m, max_depth_m=max_depth_m)
    valid_mask = filtered_depth > 0
    points_xyz = depth_to_xyz(filtered_depth, intrinsics).astype(np.float32)

    colors_rgb = None
    if frame.color is not None and frame.color.shape[:2] == filtered_depth.shape:
        colors_bgr = frame.color[valid_mask].astype(np.float32) / 255.0
        colors_rgb = colors_bgr[:, [2, 1, 0]]

    return PointCloudData(points_xyz=points_xyz, colors_rgb=colors_rgb)
