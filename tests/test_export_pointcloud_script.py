import importlib.util
from datetime import datetime
from pathlib import Path
import sys
import unittest


def load_export_script_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "02_export_pointcloud.py"
    spec = importlib.util.spec_from_file_location("export_pointcloud_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExportPointCloudScriptTests(unittest.TestCase):
    def test_build_output_path_uses_ply_output_directory_and_timestamp(self) -> None:
        script = load_export_script_module()

        path = script.build_output_path(datetime(2026, 7, 6, 9, 8, 7))

        self.assertEqual(path.name, "single_frame_20260706_090807.ply")
        self.assertEqual(path.parent.name, "ply")
        self.assertEqual(path.parent.parent.name, "outputs")


if __name__ == "__main__":
    unittest.main()
