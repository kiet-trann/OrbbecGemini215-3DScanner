import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.camera.orbbec_capture import CameraIntrinsics, RgbdFrame
from scanner_app.fusion.tsdf import (
    mask_depth_to_world_roi,
    open3d_camera_intrinsic,
    world_to_camera_extrinsic,
)


class TsdfFusionTests(unittest.TestCase):
    def test_mask_depth_to_world_roi_keeps_only_depth_pixels_inside_world_bounds(self) -> None:
        frame = RgbdFrame(
            color=None,
            depth=np.array([[1000, 1000, 1000]], dtype=np.uint16),
            depth_scale=1.0,
            timestamp_ms=0.0,
        )
        intrinsics = CameraIntrinsics(
            fx=1.0,
            fy=1.0,
            cx=1.0,
            cy=0.0,
            width=3,
            height=1,
        )
        camera_to_world = np.eye(4, dtype=np.float64)

        masked = mask_depth_to_world_roi(
            frame,
            intrinsics,
            camera_to_world=camera_to_world,
            min_depth_m=0.15,
            max_depth_m=1.50,
            min_bound=np.array([-0.10, -0.10, 0.50], dtype=np.float32),
            max_bound=np.array([0.10, 0.10, 1.50], dtype=np.float32),
        )

        np.testing.assert_array_equal(masked, np.array([[0.0, 1.0, 0.0]], dtype=np.float32))

    def test_world_to_camera_extrinsic_inverts_camera_to_world(self) -> None:
        camera_to_world = np.eye(4, dtype=np.float64)
        camera_to_world[:3, 3] = [0.1, 0.2, 0.3]

        extrinsic = world_to_camera_extrinsic(camera_to_world)

        expected = np.eye(4, dtype=np.float64)
        expected[:3, 3] = [-0.1, -0.2, -0.3]
        np.testing.assert_allclose(extrinsic, expected)

    def test_open3d_camera_intrinsic_uses_depth_intrinsic_values(self) -> None:
        intrinsics = CameraIntrinsics(
            fx=500.0,
            fy=501.0,
            cx=320.0,
            cy=240.0,
            width=640,
            height=480,
        )

        open3d_intrinsic = open3d_camera_intrinsic(intrinsics)

        self.assertEqual(open3d_intrinsic.width, 640)
        self.assertEqual(open3d_intrinsic.height, 480)
        np.testing.assert_allclose(
            open3d_intrinsic.intrinsic_matrix,
            np.array(
                [
                    [500.0, 0.0, 320.0],
                    [0.0, 501.0, 240.0],
                    [0.0, 0.0, 1.0],
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
