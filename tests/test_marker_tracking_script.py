import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()


def load_marker_tracking_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "03_marker_tracking.py"
    spec = importlib.util.spec_from_file_location("marker_tracking", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeDetection:
    marker_id = 3
    rvec = np.array([[0.1], [0.2], [0.3]], dtype=np.float64)
    tvec = np.array([[0.01], [0.02], [0.35]], dtype=np.float64)


class MarkerTrackingScriptTests(unittest.TestCase):
    def test_format_tracking_status_includes_marker_pose(self) -> None:
        module = load_marker_tracking_module()

        status = module.format_tracking_status(
            frame_count=24,
            elapsed_seconds=2.0,
            detections=[FakeDetection()],
            rejected_count=5,
        )

        self.assertEqual(
            status,
            "Marker frames: 24 | 12.0 FPS | markers=1 | rejected=5 | "
            "id=3 t=(0.010, 0.020, 0.350)m",
        )

    def test_format_tracking_status_handles_no_marker(self) -> None:
        module = load_marker_tracking_module()

        status = module.format_tracking_status(
            frame_count=10,
            elapsed_seconds=0.0,
            detections=[],
            rejected_count=2,
        )

        self.assertEqual(status, "Marker frames: 10 | 0.0 FPS | markers=0 | rejected=2")


if __name__ == "__main__":
    unittest.main()
