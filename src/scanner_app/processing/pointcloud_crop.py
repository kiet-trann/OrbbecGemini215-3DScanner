"""Post-processing helpers for cropping scanned point clouds."""

from dataclasses import dataclass

import numpy as np
import open3d as o3d


@dataclass(frozen=True)
class PlaneRemovalResult:
    cloud: o3d.geometry.PointCloud
    removed_points: int
    plane_model: tuple[float, float, float, float] | None


def crop_axis_aligned(
    cloud: o3d.geometry.PointCloud,
    *,
    min_bound: np.ndarray,
    max_bound: np.ndarray,
) -> o3d.geometry.PointCloud:
    bbox = o3d.geometry.AxisAlignedBoundingBox(
        min_bound=np.asarray(min_bound, dtype=np.float64),
        max_bound=np.asarray(max_bound, dtype=np.float64),
    )
    return cloud.crop(bbox)


def remove_dominant_plane(
    cloud: o3d.geometry.PointCloud,
    *,
    distance_threshold_m: float = 0.01,
    ransac_n: int = 3,
    num_iterations: int = 1000,
) -> PlaneRemovalResult:
    if len(cloud.points) < ransac_n:
        return PlaneRemovalResult(cloud=cloud, removed_points=0, plane_model=None)

    plane_model, inliers = cloud.segment_plane(
        distance_threshold=distance_threshold_m,
        ransac_n=ransac_n,
        num_iterations=num_iterations,
    )
    if not inliers:
        return PlaneRemovalResult(cloud=cloud, removed_points=0, plane_model=None)

    return PlaneRemovalResult(
        cloud=cloud.select_by_index(inliers, invert=True),
        removed_points=len(inliers),
        plane_model=tuple(float(value) for value in plane_model),
    )


def keep_largest_cluster(
    cloud: o3d.geometry.PointCloud,
    *,
    eps: float = 0.03,
    min_points: int = 30,
) -> tuple[o3d.geometry.PointCloud, int]:
    if len(cloud.points) == 0:
        return cloud, 0

    labels = np.asarray(
        cloud.cluster_dbscan(
            eps=float(eps),
            min_points=int(min_points),
            print_progress=False,
        )
    )
    valid_labels = labels[labels >= 0]
    if len(valid_labels) == 0:
        return cloud, 0

    unique_labels, counts = np.unique(valid_labels, return_counts=True)
    largest_label = int(unique_labels[np.argmax(counts)])
    indices = np.flatnonzero(labels == largest_label).tolist()
    return cloud.select_by_index(indices), len(unique_labels)


def voxel_downsample(
    cloud: o3d.geometry.PointCloud,
    voxel_size_m: float,
) -> o3d.geometry.PointCloud:
    if voxel_size_m <= 0 or len(cloud.points) == 0:
        return cloud
    return cloud.voxel_down_sample(float(voxel_size_m))
