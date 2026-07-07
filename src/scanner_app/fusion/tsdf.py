"""TSDF fusion helpers for RGB-D scan integration."""

import numpy as np
import open3d as o3d

from scanner_app.camera.orbbec_capture import CameraIntrinsics, RgbdFrame
from scanner_app.tracking.pose import invert_transform


def open3d_camera_intrinsic(intrinsics: CameraIntrinsics) -> o3d.camera.PinholeCameraIntrinsic:
    return o3d.camera.PinholeCameraIntrinsic(
        int(intrinsics.width),
        int(intrinsics.height),
        float(intrinsics.fx),
        float(intrinsics.fy),
        float(intrinsics.cx),
        float(intrinsics.cy),
    )


def world_to_camera_extrinsic(camera_to_world: np.ndarray) -> np.ndarray:
    return invert_transform(np.asarray(camera_to_world, dtype=np.float64))


def mask_depth_to_world_roi(
    frame: RgbdFrame,
    intrinsics: CameraIntrinsics,
    *,
    camera_to_world: np.ndarray,
    min_depth_m: float,
    max_depth_m: float,
    min_bound: np.ndarray,
    max_bound: np.ndarray,
) -> np.ndarray:
    depth_m = frame.depth_mm * 0.001
    valid_mask = (depth_m >= float(min_depth_m)) & (depth_m <= float(max_depth_m))
    if not np.any(valid_mask):
        return np.zeros_like(depth_m, dtype=np.float32)

    height, width = depth_m.shape
    u, v = np.meshgrid(np.arange(width), np.arange(height))
    z = depth_m
    x = (u - intrinsics.cx) * z / intrinsics.fx
    y = (v - intrinsics.cy) * z / intrinsics.fy
    camera_points = np.stack((x, y, z), axis=-1).reshape(-1, 3)

    points_h = np.c_[camera_points, np.ones(len(camera_points), dtype=np.float32)]
    world_points = (np.asarray(camera_to_world, dtype=np.float64) @ points_h.T).T[:, :3]
    min_bound = np.asarray(min_bound, dtype=np.float32)
    max_bound = np.asarray(max_bound, dtype=np.float32)
    roi_mask = np.all((world_points >= min_bound) & (world_points <= max_bound), axis=1)
    roi_mask = roi_mask.reshape(height, width)

    masked_depth = np.where(valid_mask & roi_mask, depth_m, 0.0)
    return masked_depth.astype(np.float32)


def make_rgbd_image(
    *,
    color_bgr: np.ndarray | None,
    depth_m: np.ndarray,
    depth_trunc_m: float,
) -> o3d.geometry.RGBDImage:
    if color_bgr is None:
        color_rgb = np.zeros((*depth_m.shape, 3), dtype=np.uint8)
    else:
        color_rgb = np.ascontiguousarray(color_bgr[:, :, [2, 1, 0]], dtype=np.uint8)
    depth_image = np.ascontiguousarray(depth_m, dtype=np.float32)

    return o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(color_rgb),
        o3d.geometry.Image(depth_image),
        depth_scale=1.0,
        depth_trunc=float(depth_trunc_m),
        convert_rgb_to_intensity=False,
    )


def create_tsdf_volume(
    *,
    voxel_length_m: float,
    sdf_trunc_m: float,
    with_color: bool = True,
) -> o3d.pipelines.integration.ScalableTSDFVolume:
    color_type = (
        o3d.pipelines.integration.TSDFVolumeColorType.RGB8
        if with_color
        else o3d.pipelines.integration.TSDFVolumeColorType.NoColor
    )
    return o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=float(voxel_length_m),
        sdf_trunc=float(sdf_trunc_m),
        color_type=color_type,
    )


def integrate_rgbd_frame(
    volume: o3d.pipelines.integration.ScalableTSDFVolume,
    *,
    frame: RgbdFrame,
    intrinsics: CameraIntrinsics,
    camera_to_world: np.ndarray,
    min_depth_m: float,
    max_depth_m: float,
    min_bound: np.ndarray,
    max_bound: np.ndarray,
) -> int:
    depth_m = mask_depth_to_world_roi(
        frame,
        intrinsics,
        camera_to_world=camera_to_world,
        min_depth_m=min_depth_m,
        max_depth_m=max_depth_m,
        min_bound=min_bound,
        max_bound=max_bound,
    )
    valid_pixels = int(np.count_nonzero(depth_m))
    if valid_pixels == 0:
        return 0

    volume.integrate(
        make_rgbd_image(
            color_bgr=frame.color,
            depth_m=depth_m,
            depth_trunc_m=max_depth_m,
        ),
        open3d_camera_intrinsic(intrinsics),
        world_to_camera_extrinsic(camera_to_world),
    )
    return valid_pixels
