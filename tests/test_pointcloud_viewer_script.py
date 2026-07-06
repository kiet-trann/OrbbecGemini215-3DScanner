import importlib.util
from pathlib import Path
import sys
import unittest


def load_pointcloud_viewer_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "03_pointcloud_viewer.py"
    spec = importlib.util.spec_from_file_location("pointcloud_viewer_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PointCloudViewerScriptTests(unittest.TestCase):
    def test_build_argument_parser_accepts_headless_max_frames_and_depth_range(self) -> None:
        script = load_pointcloud_viewer_script()

        args = script.build_argument_parser().parse_args(
            ["--headless", "--max-frames", "3", "--min-depth-m", "0.2", "--max-depth-m", "2.0"]
        )

        self.assertTrue(args.headless)
        self.assertEqual(args.max_frames, 3)
        self.assertEqual(args.min_depth_m, 0.2)
        self.assertEqual(args.max_depth_m, 2.0)


if __name__ == "__main__":
    unittest.main()
