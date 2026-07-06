import importlib.util
from pathlib import Path
import sys
import unittest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()


def load_merge_script_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "05_merge_pointcloud.py"
    spec = importlib.util.spec_from_file_location("merge_pointcloud", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MergePointCloudScriptTests(unittest.TestCase):
    def test_build_output_path_uses_ply_directory_and_timestamp(self) -> None:
        module = load_merge_script_module()

        path = module.build_output_path(now=module.datetime(2026, 7, 6, 12, 34, 56))

        self.assertEqual(path.name, "merged_cloud_20260706_123456.ply")
        self.assertEqual(path.parent.name, "ply")
        self.assertEqual(path.parent.parent.name, "outputs")

    def test_format_merge_status_reports_tracking_counts_and_points(self) -> None:
        module = load_merge_script_module()

        status = module.format_merge_status(
            frame_count=12,
            elapsed_seconds=3.0,
            tracked_frames=8,
            skipped_frames=4,
            merged_points=12345,
        )

        self.assertEqual(
            status,
            "Merge frames: 12 | 4.0 FPS | tracked=8 | skipped=4 | merged_points=12345",
        )


if __name__ == "__main__":
    unittest.main()
