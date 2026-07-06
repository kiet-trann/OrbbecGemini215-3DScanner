"""Point cloud merge helpers."""

import numpy as np
import open3d as o3d

from scanner_app.pointcloud.generate import PointCloudData


def transform_points(points_xyz: np.ndarray, camera_to_world: np.ndarray) -> np.ndarray:
    points_h = np.c_[points_xyz, np.ones(len(points_xyz))]
    transformed = (camera_to_world @ points_h.T).T
    return transformed[:, :3]


def transform_point_cloud(
    point_cloud: PointCloudData,
    camera_to_world: np.ndarray,
) -> PointCloudData:
    return PointCloudData(
        points_xyz=transform_points(point_cloud.points_xyz, camera_to_world),
        colors_rgb=point_cloud.colors_rgb,
    )


def merge_point_clouds(point_clouds: list[PointCloudData]) -> PointCloudData:
    if not point_clouds:
        return PointCloudData(points_xyz=np.empty((0, 3), dtype=np.float32))

    points_xyz = np.vstack([point_cloud.points_xyz for point_cloud in point_clouds]).astype(
        np.float32
    )
    colors_rgb = None
    if all(point_cloud.colors_rgb is not None for point_cloud in point_clouds):
        colors_rgb = np.vstack([point_cloud.colors_rgb for point_cloud in point_clouds]).astype(
            np.float32
        )
    return PointCloudData(points_xyz=points_xyz, colors_rgb=colors_rgb)


def voxel_downsample_point_cloud(
    point_cloud: PointCloudData,
    voxel_size_m: float,
) -> PointCloudData:
    if voxel_size_m <= 0 or len(point_cloud.points_xyz) == 0:
        return point_cloud

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(point_cloud.points_xyz)
    if point_cloud.colors_rgb is not None:
        cloud.colors = o3d.utility.Vector3dVector(point_cloud.colors_rgb)

    downsampled = cloud.voxel_down_sample(float(voxel_size_m))
    points_xyz = np.asarray(downsampled.points, dtype=np.float32)
    colors_rgb = None
    if point_cloud.colors_rgb is not None and len(downsampled.colors) == len(downsampled.points):
        colors_rgb = np.asarray(downsampled.colors, dtype=np.float32)
    return PointCloudData(points_xyz=points_xyz, colors_rgb=colors_rgb)
