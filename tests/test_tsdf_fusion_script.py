import importlib.util
from pathlib import Path
import sys
import unittest


def load_tsdf_script_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "06_tsdf_fusion.py"
    spec = importlib.util.spec_from_file_location("tsdf_fusion_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TsdfFusionScriptTests(unittest.TestCase):
    def test_build_argument_parser_accepts_tsdf_and_roi_options(self) -> None:
        script = load_tsdf_script_module()

        args = script.build_argument_parser().parse_args(
            [
                "--marker-size-m",
                "0.06",
                "--capture-seconds",
                "20",
                "--tracked-frame-stride",
                "4",
                "--voxel-length-m",
                "0.002",
                "--sdf-trunc-m",
                "0.008",
                "--roi-min-x",
                "-0.20",
                "--roi-max-z",
                "0.12",
            ]
        )

        self.assertEqual(args.marker_size_m, 0.06)
        self.assertEqual(args.capture_seconds, 20.0)
        self.assertEqual(args.tracked_frame_stride, 4)
        self.assertEqual(args.voxel_length_m, 0.002)
        self.assertEqual(args.sdf_trunc_m, 0.008)
        self.assertEqual(args.roi_min_x, -0.20)
        self.assertEqual(args.roi_max_z, 0.12)

    def test_build_output_path_uses_tsdf_mesh_name(self) -> None:
        script = load_tsdf_script_module()

        output = script.build_output_path(now=script.datetime(2026, 7, 7, 13, 45, 0))

        self.assertEqual(output.name, "tsdf_mesh_20260707_134500.ply")
        self.assertEqual(output.parent.name, "ply")
        self.assertEqual(output.parent.parent.name, "outputs")


if __name__ == "__main__":
    unittest.main()
