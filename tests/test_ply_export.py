import tempfile
from pathlib import Path
import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.export.ply import write_point_cloud_ply


class PlyExportTests(unittest.TestCase):
    def test_write_point_cloud_ply_creates_parent_directory_and_accepts_colors(self) -> None:
        points = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 2.0]], dtype=np.float32)
        colors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "cloud.ply"

            write_point_cloud_ply(path, points, colors_rgb=colors)

            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
