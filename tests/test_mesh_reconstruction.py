import unittest

import numpy as np
import open3d as o3d

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.processing.mesh_reconstruction import (
    ball_pivoting_radii,
    describe_mesh,
    estimate_point_spacing,
)


class MeshReconstructionTests(unittest.TestCase):
    def test_estimate_point_spacing_uses_median_nearest_neighbor_distance(self) -> None:
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [0.1, 0.0, 0.0],
                    [0.2, 0.0, 0.0],
                ],
                dtype=np.float64,
            )
        )

        self.assertAlmostEqual(estimate_point_spacing(cloud), 0.1)

    def test_ball_pivoting_radii_uses_explicit_radius_or_spacing_scales(self) -> None:
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(
            np.array(
                [
                    [0.0, 0.0, 0.0],
                    [0.1, 0.0, 0.0],
                    [0.2, 0.0, 0.0],
                ],
                dtype=np.float64,
            )
        )

        explicit = ball_pivoting_radii(cloud, base_radius_m=0.02, radius_scales=(1.0, 2.0))
        automatic = ball_pivoting_radii(cloud, base_radius_m=0.0, radius_scales=(1.5, 3.0))

        self.assertEqual(list(explicit), [0.02, 0.04])
        self.assertEqual(list(automatic), [0.15000000000000002, 0.30000000000000004])

    def test_describe_mesh_reports_vertices_and_triangles(self) -> None:
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(
            np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
        )
        mesh.triangles = o3d.utility.Vector3iVector(np.array([[0, 1, 2]], dtype=np.int32))

        self.assertEqual(describe_mesh(mesh), "vertices=3 | triangles=1")


if __name__ == "__main__":
    unittest.main()
