import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np


def load_viewer_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    viewer_path = project_root / "scripts" / "01_rgbd_viewer.py"
    spec = importlib.util.spec_from_file_location("rgbd_viewer", viewer_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeFrame:
    color = np.zeros((720, 1280, 3), dtype=np.uint8)
    depth = np.zeros((800, 1280), dtype=np.uint16)
    depth_scale = 1.0


class RgbdViewerTests(unittest.TestCase):
    def test_format_frame_status_includes_frame_rate_and_shapes(self) -> None:
        viewer = load_viewer_module()

        status = viewer.format_frame_status(frame_count=30, elapsed_seconds=2.0, frame=FakeFrame())

        self.assertEqual(
            status,
            "RGB-D frames: 30 | 15.0 FPS | depth=(800, 1280) scale=1.0 | color=(720, 1280, 3)",
        )


if __name__ == "__main__":
    unittest.main()
