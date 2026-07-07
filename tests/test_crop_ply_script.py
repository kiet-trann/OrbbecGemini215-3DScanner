import importlib.util
from pathlib import Path
import sys
import unittest


def load_crop_ply_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "09_crop_ply.py"
    spec = importlib.util.spec_from_file_location("crop_ply_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CropPlyScriptTests(unittest.TestCase):
    def test_build_argument_parser_accepts_auto_crop_options(self) -> None:
        script = load_crop_ply_script()

        args = script.build_argument_parser().parse_args(
            [
                "outputs/ply/scan.ply",
                "--plane-distance-threshold-m",
                "0.008",
                "--cluster-eps-m",
                "0.03",
                "--cluster-min-points",
                "25",
            ]
        )

        self.assertEqual(args.path, Path("outputs/ply/scan.ply"))
        self.assertEqual(args.plane_distance_threshold_m, 0.008)
        self.assertEqual(args.cluster_eps_m, 0.03)
        self.assertEqual(args.cluster_min_points, 25)
        self.assertFalse(args.keep_largest_cluster)

    def test_build_argument_parser_accepts_keep_largest_cluster(self) -> None:
        script = load_crop_ply_script()

        args = script.build_argument_parser().parse_args(
            ["outputs/ply/scan.ply", "--keep-largest-cluster"]
        )

        self.assertTrue(args.keep_largest_cluster)

    def test_build_output_path_adds_cropped_suffix_in_ply_directory(self) -> None:
        script = load_crop_ply_script()

        output = script.build_output_path(Path("outputs/ply/merged_cloud_1.ply"))

        self.assertEqual(output, Path("outputs/ply/merged_cloud_1_cropped.ply"))

    def test_resolve_output_path_returns_absolute_path(self) -> None:
        script = load_crop_ply_script()

        output = script.resolve_output_path(
            output_path=None,
            input_path=Path("outputs/ply/merged_cloud_1.ply"),
        )

        self.assertTrue(output.is_absolute())
        self.assertEqual(output.name, "merged_cloud_1_cropped.ply")


if __name__ == "__main__":
    unittest.main()
