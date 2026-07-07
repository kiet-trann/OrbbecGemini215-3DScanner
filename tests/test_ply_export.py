import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_write_point_cloud_ply_falls_back_to_ascii_when_open3d_write_fails(self) -> None:
        points = np.array([[0.0, 0.0, 1.0]], dtype=np.float32)
        colors = np.array([[0.25, 0.5, 1.0]], dtype=np.float32)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fallback.ply"

            with patch("scanner_app.export.ply.o3d.io.write_point_cloud", return_value=False):
                write_point_cloud_ply(path, points, colors_rgb=colors)

            text = path.read_text(encoding="ascii")
            self.assertIn("format ascii 1.0", text)
            self.assertIn("property uchar red", text)
            self.assertIn("0.000000 0.000000 1.000000 64 128 255", text)

    def test_write_point_cloud_ply_can_force_ascii_without_calling_open3d_writer(self) -> None:
        points = np.array([[0.0, 0.0, 1.0]], dtype=np.float32)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "forced_ascii.ply"

            with patch("scanner_app.export.ply.o3d.io.write_point_cloud") as write_mock:
                write_point_cloud_ply(path, points, prefer_ascii=True)

            write_mock.assert_not_called()
            self.assertIn("format ascii 1.0", path.read_text(encoding="ascii"))


if __name__ == "__main__":
    unittest.main()
