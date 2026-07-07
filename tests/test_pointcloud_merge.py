import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.fusion.merge import (
    crop_point_cloud_bounds,
    merge_point_clouds,
    transform_point_cloud,
    transform_points,
    voxel_downsample_point_cloud,
)
from scanner_app.pointcloud.generate import PointCloudData


class PointCloudMergeTests(unittest.TestCase):
    def test_transform_points_applies_camera_to_world_translation(self) -> None:
        points = np.array([[0.0, 0.0, 1.0], [1.0, 2.0, 3.0]], dtype=np.float32)
        camera_to_world = np.eye(4, dtype=np.float64)
        camera_to_world[:3, 3] = [10.0, 20.0, 30.0]

        transformed = transform_points(points, camera_to_world)

        np.testing.assert_array_equal(
            transformed,
            np.array([[10.0, 20.0, 31.0], [11.0, 22.0, 33.0]], dtype=np.float64),
        )

    def test_transform_point_cloud_preserves_rgb_colors(self) -> None:
        point_cloud = PointCloudData(
            points_xyz=np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
            colors_rgb=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
        )
        camera_to_world = np.eye(4, dtype=np.float64)
        camera_to_world[:3, 3] = [0.0, 0.0, 1.0]

        transformed = transform_point_cloud(point_cloud, camera_to_world)

        np.testing.assert_array_equal(transformed.points_xyz, np.array([[0.0, 0.0, 2.0]]))
        np.testing.assert_array_equal(transformed.colors_rgb, point_cloud.colors_rgb)

    def test_merge_point_clouds_concatenates_points_and_colors(self) -> None:
        first = PointCloudData(
            points_xyz=np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
            colors_rgb=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
        )
        second = PointCloudData(
            points_xyz=np.array([[1.0, 0.0, 1.0]], dtype=np.float32),
            colors_rgb=np.array([[0.0, 1.0, 0.0]], dtype=np.float32),
        )

        merged = merge_point_clouds([first, second])

        np.testing.assert_array_equal(
            merged.points_xyz,
            np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            merged.colors_rgb,
            np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32),
        )

    def test_merge_point_clouds_omits_colors_when_any_frame_is_depth_only(self) -> None:
        colored = PointCloudData(
            points_xyz=np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
            colors_rgb=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
        )
        depth_only = PointCloudData(points_xyz=np.array([[1.0, 0.0, 1.0]], dtype=np.float32))

        merged = merge_point_clouds([colored, depth_only])

        self.assertIsNone(merged.colors_rgb)
        self.assertEqual(len(merged.points_xyz), 2)

    def test_crop_point_cloud_bounds_keeps_points_inside_roi_and_preserves_colors(self) -> None:
        point_cloud = PointCloudData(
            points_xyz=np.array(
                [
                    [-0.20, 0.00, 0.02],
                    [-0.08, 0.04, 0.03],
                    [0.10, 0.00, 0.02],
                ],
                dtype=np.float32,
            ),
            colors_rgb=np.array(
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float32,
            ),
        )

        cropped = crop_point_cloud_bounds(
            point_cloud,
            min_bound=np.array([-0.12, -0.05, 0.00], dtype=np.float32),
            max_bound=np.array([0.02, 0.08, 0.05], dtype=np.float32),
        )

        np.testing.assert_array_equal(
            cropped.points_xyz,
            np.array([[-0.08, 0.04, 0.03]], dtype=np.float32),
        )
        np.testing.assert_array_equal(
            cropped.colors_rgb,
            np.array([[0.0, 1.0, 0.0]], dtype=np.float32),
        )

    def test_crop_point_cloud_bounds_keeps_unbounded_axes(self) -> None:
        point_cloud = PointCloudData(
            points_xyz=np.array(
                [[-0.10, 0.00, 0.00], [0.05, 0.00, 0.00]],
                dtype=np.float32,
            )
        )

        cropped = crop_point_cloud_bounds(
            point_cloud,
            min_bound=np.array([-np.inf, -np.inf, -np.inf], dtype=np.float32),
            max_bound=np.array([0.00, np.inf, np.inf], dtype=np.float32),
        )

        np.testing.assert_array_equal(
            cropped.points_xyz,
            np.array([[-0.10, 0.00, 0.00]], dtype=np.float32),
        )

    def test_voxel_downsample_point_cloud_reduces_nearby_points_and_preserves_color(self) -> None:
        point_cloud = PointCloudData(
            points_xyz=np.array(
                [
                    [0.000, 0.000, 0.000],
                    [0.001, 0.001, 0.001],
                    [0.020, 0.000, 0.000],
                ],
                dtype=np.float32,
            ),
            colors_rgb=np.array(
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float32,
            ),
        )

        downsampled = voxel_downsample_point_cloud(point_cloud, voxel_size_m=0.01)

        self.assertEqual(len(downsampled.points_xyz), 2)
        self.assertIsNotNone(downsampled.colors_rgb)
        self.assertEqual(len(downsampled.colors_rgb), 2)

    def test_voxel_downsample_point_cloud_returns_original_when_disabled(self) -> None:
        point_cloud = PointCloudData(points_xyz=np.array([[0.0, 0.0, 0.0]], dtype=np.float32))

        downsampled = voxel_downsample_point_cloud(point_cloud, voxel_size_m=0.0)

        self.assertIs(downsampled, point_cloud)


if __name__ == "__main__":
    unittest.main()
