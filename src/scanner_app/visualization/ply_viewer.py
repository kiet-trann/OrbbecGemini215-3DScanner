"""Offline Open3D helpers for inspecting saved PLY point clouds."""

from pathlib import Path

import numpy as np
import open3d as o3d


def read_point_cloud(path: Path) -> o3d.geometry.PointCloud:
    if not path.exists():
        raise FileNotFoundError(f"PLY file not found: {path}")

    cloud = o3d.io.read_point_cloud(str(path))
    if len(cloud.points) == 0:
        raise ValueError(f"PLY file has no readable points: {path}")
    return cloud


def describe_point_cloud(cloud: o3d.geometry.PointCloud) -> str:
    point_count = len(cloud.points)
    has_color = cloud.has_colors()

    if point_count == 0:
        return "points=0 | color=no"

    points = np.asarray(cloud.points)
    bounds_min = points.min(axis=0)
    bounds_max = points.max(axis=0)
    size = bounds_max - bounds_min

    return (
        f"points={point_count} | color={'yes' if has_color else 'no'} | "
        f"bounds_min={_format_vector(bounds_min)}m | "
        f"bounds_max={_format_vector(bounds_max)}m | "
        f"size={_format_vector(size)}m"
    )


def show_point_cloud(
    cloud: o3d.geometry.PointCloud,
    *,
    window_name: str = "PLY Point Cloud Viewer",
    width: int = 1280,
    height: int = 720,
    point_size: float = 2.0,
) -> None:
    visualizer = o3d.visualization.Visualizer()
    visualizer.create_window(window_name=window_name, width=width, height=height)
    try:
        visualizer.add_geometry(cloud)
        render_option = visualizer.get_render_option()
        render_option.background_color = np.array([0.05, 0.05, 0.05])
        render_option.point_size = point_size
        visualizer.run()
    finally:
        visualizer.destroy_window()


def _format_vector(values: np.ndarray) -> str:
    return f"({values[0]:.3f}, {values[1]:.3f}, {values[2]:.3f})"
