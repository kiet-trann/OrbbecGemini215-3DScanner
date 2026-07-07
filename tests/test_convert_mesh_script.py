import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import open3d as o3d


def load_convert_mesh_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "11_convert_mesh.py"
    spec = importlib.util.spec_from_file_location("convert_mesh_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ConvertMeshScriptTests(unittest.TestCase):
    def test_build_argument_parser_accepts_input_and_output(self) -> None:
        script = load_convert_mesh_script()

        args = script.build_argument_parser().parse_args(
            ["outputs/ply/mesh.ply", "--output", "outputs/obj/mesh.obj"]
        )

        self.assertEqual(args.path, Path("outputs/ply/mesh.ply"))
        self.assertEqual(args.output, Path("outputs/obj/mesh.obj"))

    def test_build_output_path_uses_matching_output_directory(self) -> None:
        script = load_convert_mesh_script()

        obj_output = script.build_output_path(Path("outputs/ply/tsdf_mesh.ply"), ".obj")
        stl_output = script.build_output_path(Path("outputs/ply/tsdf_mesh.ply"), ".stl")

        self.assertEqual(obj_output.name, "tsdf_mesh.obj")
        self.assertEqual(obj_output.parent.name, "obj")
        self.assertEqual(stl_output.name, "tsdf_mesh.stl")
        self.assertEqual(stl_output.parent.name, "stl")

    def test_should_write_ascii_disables_ascii_for_obj_and_stl(self) -> None:
        script = load_convert_mesh_script()

        self.assertFalse(script.should_write_ascii(Path("mesh.obj")))
        self.assertFalse(script.should_write_ascii(Path("mesh.stl")))
        self.assertTrue(script.should_write_ascii(Path("mesh.ply")))

    def test_resolve_output_path_preserves_explicit_relative_path(self) -> None:
        script = load_convert_mesh_script()

        output = script.resolve_output_path(
            input_path=Path("outputs/ply/mesh.ply"),
            output_path=Path("outputs/obj/mesh.obj"),
            output_format="obj",
        )

        self.assertEqual(output, Path("outputs/obj/mesh.obj"))

    def test_open3d_path_uses_forward_slashes(self) -> None:
        script = load_convert_mesh_script()

        self.assertEqual(script.open3d_path(Path("outputs") / "obj" / "mesh.obj"), "outputs/obj/mesh.obj")

    def test_temporary_write_path_uses_short_name_in_output_directory(self) -> None:
        script = load_convert_mesh_script()

        temporary = script.temporary_write_path(Path("outputs/obj/long_mesh_name.obj"))

        self.assertEqual(temporary, Path("outputs/obj/_convert_tmp.obj"))

    def test_write_obj_mesh_writes_vertices_and_faces(self) -> None:
        script = load_convert_mesh_script()
        mesh = make_triangle_mesh()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "triangle.obj"
            script.write_obj_mesh(output, mesh)

            content = output.read_text(encoding="utf-8")

        self.assertIn("v 0.00000000 0.00000000 0.00000000", content)
        self.assertIn("f 1 2 3", content)

    def test_write_binary_stl_mesh_writes_triangle_count(self) -> None:
        script = load_convert_mesh_script()
        mesh = make_triangle_mesh()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "triangle.stl"
            script.write_binary_stl_mesh(output, mesh)
            data = output.read_bytes()

        self.assertEqual(len(data), 84 + 50)
        self.assertEqual(int.from_bytes(data[80:84], byteorder="little"), 1)


def make_triangle_mesh() -> o3d.geometry.TriangleMesh:
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    )
    mesh.triangles = o3d.utility.Vector3iVector([[0, 1, 2]])
    mesh.compute_triangle_normals()
    return mesh


if __name__ == "__main__":
    unittest.main()
