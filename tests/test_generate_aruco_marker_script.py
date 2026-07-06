import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import cv2
import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.tracking.aruco import detect_markers


def load_generate_marker_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "00_generate_aruco_marker.py"
    spec = importlib.util.spec_from_file_location("generate_aruco_marker", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GenerateArucoMarkerScriptTests(unittest.TestCase):
    def test_build_output_path_includes_dictionary_id_and_size(self) -> None:
        module = load_generate_marker_module()

        path = module.build_output_path("DICT_4X4_50", marker_id=7, marker_size_px=800)

        self.assertEqual(path.name, "aruco_DICT_4X4_50_id7_800px.png")
        self.assertEqual(path.parent.name, "calibration")

    def test_generate_marker_image_has_white_margin_and_detectable_marker(self) -> None:
        module = load_generate_marker_module()

        image = module.generate_marker_image(
            dictionary_name="DICT_4X4_50",
            marker_id=7,
            marker_size_px=200,
            border_px=40,
        )

        self.assertEqual(image.shape, (280, 280))
        self.assertEqual(int(image[0, 0]), 255)
        detections = detect_markers(
            cv2.cvtColor(image, cv2.COLOR_GRAY2BGR),
            dictionary_name="DICT_4X4_50",
        )
        self.assertEqual([detection.marker_id for detection in detections], [7])

    def test_write_marker_image_creates_png_file(self) -> None:
        module = load_generate_marker_module()
        image = np.full((20, 20), 255, dtype=np.uint8)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "marker.png"

            module.write_marker_image(output_path, image)

            self.assertTrue(output_path.is_file())
            self.assertIsNotNone(cv2.imread(str(output_path), cv2.IMREAD_GRAYSCALE))


if __name__ == "__main__":
    unittest.main()
