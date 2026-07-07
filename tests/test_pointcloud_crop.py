import unittest

import numpy as np
import open3d as o3d

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.processing.pointcloud_crop import (
    crop_axis_aligned,
    keep_largest_cluster,
)


def make_cloud(points: np.ndarray, colors: np.ndarray | None = None) -> o3d.geometry.PointCloud:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    if colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors.astype(np.float64))
    return cloud


class PointCloudCropTests(unittest.TestCase):
    def test_crop_axis_aligned_keeps_points_inside_bounds_and_preserves_colors(self) -> None:
        points = np.array(
            [
                [0.0, 0.0, 0.0],
                [0.5, 0.5, 0.5],
                [1.5, 0.5, 0.5],
            ],
            dtype=np.float64,
        )
        colors = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        cropped = crop_axis_aligned(
            make_cloud(points, colors),
            min_bound=np.array([-0.1, -0.1, -0.1]),
            max_bound=np.array([1.0, 1.0, 1.0]),
        )

        np.testing.assert_allclose(np.asarray(cropped.points), points[:2])
        np.testing.assert_allclose(np.asarray(cropped.colors), colors[:2])

    def test_keep_largest_cluster_ignores_noise_and_returns_largest_label(self) -> None:
        large_cluster = np.array(
            [
                [0.0, 0.0, 0.0],
                [0.01, 0.0, 0.0],
                [0.0, 0.01, 0.0],
                [0.01, 0.01, 0.0],
            ],
            dtype=np.float64,
        )
        small_cluster = np.array(
            [
                [1.0, 1.0, 1.0],
                [1.01, 1.0, 1.0],
            ],
            dtype=np.float64,
        )
        noise = np.array([[3.0, 3.0, 3.0]], dtype=np.float64)
        points = np.vstack([small_cluster, large_cluster, noise])

        cropped, cluster_count = keep_largest_cluster(
            make_cloud(points),
            eps=0.05,
            min_points=2,
        )

        self.assertEqual(cluster_count, 2)
        np.testing.assert_allclose(np.asarray(cropped.points), large_cluster)


if __name__ == "__main__":
    unittest.main()
