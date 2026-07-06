import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.orbbec_capture import CameraIntrinsics, RgbdFrame
from scanner_app.pointcloud.generate import rgbd_frame_to_point_cloud


class PointCloudGenerationTests(unittest.TestCase):
    def test_rgbd_frame_to_point_cloud_filters_depth_and_projects_xyz(self) -> None:
        frame = RgbdFrame(
            color=None,
            depth=np.array([[1000, 0], [2000, 3000]], dtype=np.uint16),
            depth_scale=1.0,
            timestamp_ms=0.0,
        )
        intrinsics = CameraIntrinsics(fx=2.0, fy=2.0, cx=0.0, cy=0.0, width=2, height=2)

        point_cloud = rgbd_frame_to_point_cloud(
            frame,
            intrinsics,
            min_depth_m=0.5,
            max_depth_m=2.5,
        )

        np.testing.assert_allclose(
            point_cloud.points_xyz,
            np.array(
                [
                    [0.0, 0.0, 1.0],
                    [0.0, 1.0, 2.0],
                ],
                dtype=np.float32,
            ),
        )
        self.assertIsNone(point_cloud.colors_rgb)

    def test_rgbd_frame_to_point_cloud_uses_matching_color_pixels_as_rgb(self) -> None:
        frame = RgbdFrame(
            color=np.array(
                [
                    [[10, 20, 30], [40, 50, 60]],
                    [[70, 80, 90], [100, 110, 120]],
                ],
                dtype=np.uint8,
            ),
            depth=np.array([[1000, 0], [2000, 0]], dtype=np.uint16),
            depth_scale=1.0,
            timestamp_ms=0.0,
        )
        intrinsics = CameraIntrinsics(fx=2.0, fy=2.0, cx=0.0, cy=0.0, width=2, height=2)

        point_cloud = rgbd_frame_to_point_cloud(frame, intrinsics, max_depth_m=2.5)

        np.testing.assert_allclose(
            point_cloud.colors_rgb,
            np.array(
                [
                    [30 / 255.0, 20 / 255.0, 10 / 255.0],
                    [90 / 255.0, 80 / 255.0, 70 / 255.0],
                ],
                dtype=np.float32,
            ),
        )

    def test_rgbd_frame_to_point_cloud_skips_color_when_resolution_differs(self) -> None:
        frame = RgbdFrame(
            color=np.zeros((1, 2, 3), dtype=np.uint8),
            depth=np.array([[1000, 2000], [0, 0]], dtype=np.uint16),
            depth_scale=1.0,
            timestamp_ms=0.0,
        )
        intrinsics = CameraIntrinsics(fx=2.0, fy=2.0, cx=0.0, cy=0.0, width=2, height=2)

        point_cloud = rgbd_frame_to_point_cloud(frame, intrinsics)

        self.assertIsNone(point_cloud.colors_rgb)


if __name__ == "__main__":
    unittest.main()
