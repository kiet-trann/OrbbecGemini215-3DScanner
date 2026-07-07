import importlib.util
from pathlib import Path
import sys
import unittest


def load_view_ply_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "08_view_ply.py"
    spec = importlib.util.spec_from_file_location("view_ply_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ViewPlyScriptTests(unittest.TestCase):
    def test_build_argument_parser_accepts_path_info_only_and_point_size(self) -> None:
        script = load_view_ply_script()

        args = script.build_argument_parser().parse_args(
            ["outputs/ply/scan.ply", "--info-only", "--point-size", "3.5"]
        )

        self.assertEqual(args.path, Path("outputs/ply/scan.ply"))
        self.assertTrue(args.info_only)
        self.assertEqual(args.point_size, 3.5)


if __name__ == "__main__":
    unittest.main()
