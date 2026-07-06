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


def load_pose_script_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "04_pose_estimation.py"
    spec = importlib.util.spec_from_file_location("pose_estimation", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakePoseSample:
    marker_id = 8
    camera_to_world = np.eye(4, dtype=np.float64)
    camera_to_world[:3, 3] = [0.1, 0.2, 0.3]


class PoseEstimationScriptTests(unittest.TestCase):
    def test_build_output_path_uses_session_directory_and_timestamp(self) -> None:
        module = load_pose_script_module()

        path = module.build_output_path(now=module.datetime(2026, 7, 6, 11, 22, 33))

        self.assertEqual(path.name, "poses_20260706_112233.jsonl")
        self.assertEqual(path.parent.name, "sessions")
        self.assertEqual(path.parent.parent.name, "data")

    def test_format_pose_status_includes_camera_translation(self) -> None:
        module = load_pose_script_module()

        status = module.format_pose_status(30, 2.0, FakePoseSample())

        self.assertEqual(
            status,
            "Pose frames: 30 | 15.0 FPS | tracking=OK | id=8 camera_t=(0.100, 0.200, 0.300)m",
        )

    def test_format_pose_status_reports_lost_tracking(self) -> None:
        module = load_pose_script_module()

        status = module.format_pose_status(5, 0.0, None)

        self.assertEqual(status, "Pose frames: 5 | 0.0 FPS | tracking=LOST")


if __name__ == "__main__":
    unittest.main()
