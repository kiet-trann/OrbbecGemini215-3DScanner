"""PLY export placeholder using Open3D."""

from pathlib import Path

import numpy as np
import open3d as o3d


def write_point_cloud_ply(path: str | Path, points_xyz: np.ndarray) -> None:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points_xyz)
    o3d.io.write_point_cloud(str(path), cloud)
