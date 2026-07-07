import unittest

import numpy as np
import open3d as o3d

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.ply_viewer import describe_point_cloud


class PlyViewerTests(unittest.TestCase):
    def test_describe_point_cloud_reports_points_bounds_and_color(self) -> None:
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(
            np.array(
                [
                    [0.0, -1.0, 0.5],
                    [2.0, 3.0, 4.5],
                ],
                dtype=np.float64,
            )
        )
        cloud.colors = o3d.utility.Vector3dVector(
            np.array(
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                dtype=np.float64,
            )
        )

        description = describe_point_cloud(cloud)

        self.assertEqual(
            description,
            "points=2 | color=yes | bounds_min=(0.000, -1.000, 0.500)m | "
            "bounds_max=(2.000, 3.000, 4.500)m | size=(2.000, 4.000, 4.000)m",
        )


if __name__ == "__main__":
    unittest.main()
