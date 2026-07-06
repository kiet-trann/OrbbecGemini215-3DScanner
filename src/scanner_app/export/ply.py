"""PLY export placeholder using Open3D."""

from pathlib import Path

import numpy as np
import open3d as o3d


def write_point_cloud_ply(
    path: str | Path,
    points_xyz: np.ndarray,
    colors_rgb: np.ndarray | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points_xyz)
    if colors_rgb is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors_rgb)
    o3d.io.write_point_cloud(str(path), cloud)
