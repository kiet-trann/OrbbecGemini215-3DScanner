"""Open3D helpers for live point cloud preview."""

import numpy as np
import open3d as o3d

from scanner_app.pointcloud.generate import PointCloudData


def make_open3d_point_cloud(point_cloud: PointCloudData) -> o3d.geometry.PointCloud:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(point_cloud.points_xyz.astype(np.float64))
    if point_cloud.colors_rgb is not None:
        cloud.colors = o3d.utility.Vector3dVector(point_cloud.colors_rgb.astype(np.float64))
    return cloud


def format_pointcloud_status(
    frame_count: int,
    elapsed_seconds: float,
    point_count: int,
    has_color: bool = False,
) -> str:
    fps = frame_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    color_status = "color" if has_color else "depth-only"
    return (
        f"Point cloud frames: {frame_count} | {fps:.1f} FPS | "
        f"points={point_count} | {color_status}"
    )


class Open3DPointCloudViewer:
    """Non-blocking Open3D viewer for streaming point cloud frames."""

    def __init__(
        self,
        window_name: str = "Gemini 215 Point Cloud",
        width: int = 1280,
        height: int = 720,
        point_size: float = 2.0,
    ) -> None:
        self._vis = o3d.visualization.VisualizerWithKeyCallback()
        self._vis.create_window(window_name=window_name, width=width, height=height)
        self._vis.register_key_callback(ord("Q"), self._request_close)
        self._vis.register_key_callback(256, self._request_close)

        render_option = self._vis.get_render_option()
        render_option.background_color = np.array([0.05, 0.05, 0.05])
        render_option.point_size = point_size

        self._cloud = o3d.geometry.PointCloud()
        self._geometry_added = False
        self._close_requested = False

    def update(self, point_cloud: PointCloudData) -> bool:
        self._cloud.points = o3d.utility.Vector3dVector(point_cloud.points_xyz.astype(np.float64))
        if point_cloud.colors_rgb is not None:
            self._cloud.colors = o3d.utility.Vector3dVector(point_cloud.colors_rgb.astype(np.float64))
        else:
            self._cloud.colors = o3d.utility.Vector3dVector(np.empty((0, 3), dtype=np.float64))

        if not self._geometry_added:
            self._vis.add_geometry(self._cloud)
            self._geometry_added = True
            view_control = self._vis.get_view_control()
            view_control.set_front([0.0, -0.25, -1.0])
            view_control.set_up([0.0, -1.0, 0.0])
            view_control.set_zoom(0.35)
        else:
            self._vis.update_geometry(self._cloud)

        alive = self._vis.poll_events()
        self._vis.update_renderer()
        return alive and not self._close_requested

    def close(self) -> None:
        self._vis.destroy_window()

    def _request_close(self, _vis) -> bool:
        self._close_requested = True
        return False
