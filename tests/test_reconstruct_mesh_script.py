import importlib.util
from pathlib import Path
import sys
import unittest


def load_reconstruct_mesh_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "10_reconstruct_mesh.py"
    spec = importlib.util.spec_from_file_location("reconstruct_mesh_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ReconstructMeshScriptTests(unittest.TestCase):
    def test_build_argument_parser_accepts_mesh_options(self) -> None:
        script = load_reconstruct_mesh_script()

        args = script.build_argument_parser().parse_args(
            [
                "outputs/ply/crop.ply",
                "--output",
                "outputs/obj/crop.obj",
                "--method",
                "poisson",
                "--normal-radius-m",
                "0.02",
                "--poisson-depth",
                "7",
            ]
        )

        self.assertEqual(args.path, Path("outputs/ply/crop.ply"))
        self.assertEqual(args.output, Path("outputs/obj/crop.obj"))
        self.assertEqual(args.method, "poisson")
        self.assertEqual(args.normal_radius_m, 0.02)
        self.assertEqual(args.poisson_depth, 7)

    def test_build_output_path_defaults_to_outputs_ply_mesh_suffix(self) -> None:
        script = load_reconstruct_mesh_script()

        output = script.build_output_path(Path("outputs/ply/crop.ply"))

        self.assertEqual(output.name, "crop_mesh.ply")
        self.assertEqual(output.parent.name, "ply")


if __name__ == "__main__":
    unittest.main()
