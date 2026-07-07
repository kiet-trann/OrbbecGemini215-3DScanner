"""PLY export placeholder using Open3D."""

from pathlib import Path

import numpy as np
import open3d as o3d


def write_point_cloud_ply(
    path: str | Path,
    points_xyz: np.ndarray,
    colors_rgb: np.ndarray | None = None,
    prefer_ascii: bool = False,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if prefer_ascii:
        _write_ascii_point_cloud_ply(path, points_xyz, colors_rgb=colors_rgb)
        return

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points_xyz)
    if colors_rgb is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors_rgb)
    if o3d.io.write_point_cloud(str(path), cloud):
        return

    _write_ascii_point_cloud_ply(path, points_xyz, colors_rgb=colors_rgb)


def _write_ascii_point_cloud_ply(
    path: Path,
    points_xyz: np.ndarray,
    colors_rgb: np.ndarray | None = None,
) -> None:
    points = np.asarray(points_xyz, dtype=np.float32)
    colors = None
    if colors_rgb is not None:
        colors = np.rint(np.clip(np.asarray(colors_rgb, dtype=np.float32), 0.0, 1.0) * 255.0).astype(
            np.uint8
        )
        if len(colors) != len(points):
            raise ValueError("colors_rgb must have the same point count as points_xyz.")

    with path.open("w", encoding="ascii", newline="\n") as file:
        file.write("ply\n")
        file.write("format ascii 1.0\n")
        file.write(f"element vertex {len(points)}\n")
        file.write("property float x\n")
        file.write("property float y\n")
        file.write("property float z\n")
        if colors is not None:
            file.write("property uchar red\n")
            file.write("property uchar green\n")
            file.write("property uchar blue\n")
        file.write("end_header\n")

        if colors is None:
            for x, y, z in points:
                file.write(f"{x:.6f} {y:.6f} {z:.6f}\n")
        else:
            for (x, y, z), (red, green, blue) in zip(points, colors, strict=True):
                file.write(f"{x:.6f} {y:.6f} {z:.6f} {red} {green} {blue}\n")
