import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.pointcloud.generate import PointCloudData
from scanner_app.visualization.open3d_pointcloud import (
    format_pointcloud_status,
    make_open3d_point_cloud,
)


class Open3DPointCloudViewerTests(unittest.TestCase):
    def test_format_pointcloud_status_includes_frame_rate_and_point_count(self) -> None:
        status = format_pointcloud_status(
            frame_count=20,
            elapsed_seconds=2.0,
            point_count=1234,
            has_color=True,
        )

        self.assertEqual(status, "Point cloud frames: 20 | 10.0 FPS | points=1234 | color")

    def test_make_open3d_point_cloud_sets_points_and_optional_colors(self) -> None:
        points = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 2.0]], dtype=np.float32)
        colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)

        cloud = make_open3d_point_cloud(PointCloudData(points_xyz=points, colors_rgb=colors))

        np.testing.assert_allclose(np.asarray(cloud.points), points)
        np.testing.assert_allclose(np.asarray(cloud.colors), colors)


if __name__ == "__main__":
    unittest.main()
