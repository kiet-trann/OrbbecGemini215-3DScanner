"""Convert an existing triangle mesh to another 3D file format."""

import _bootstrap  # noqa: F401

import argparse
from pathlib import Path
import struct

import numpy as np
import open3d as o3d

from scanner_app.processing.mesh_reconstruction import cleanup_mesh, describe_mesh


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
SUPPORTED_OUTPUTS = (".ply", ".obj", ".stl")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a triangle mesh between PLY/OBJ/STL.")
    parser.add_argument("path", type=Path, help="Input triangle mesh path.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output mesh path. Defaults to outputs/<ext>/<input-stem>.obj.",
    )
    parser.add_argument(
        "--format",
        choices=("ply", "obj", "stl"),
        default="obj",
        help="Output format used when --output is omitted.",
    )
    return parser


def build_output_path(input_path: Path, suffix: str) -> Path:
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    if suffix not in SUPPORTED_OUTPUTS:
        raise ValueError(f"Unsupported mesh output suffix: {suffix}")
    return OUTPUT_ROOT / suffix.lstrip(".") / f"{input_path.stem}{suffix}"


def resolve_output_path(*, input_path: Path, output_path: Path | None, output_format: str) -> Path:
    if output_path is not None:
        suffix = output_path.suffix.lower()
        if suffix not in SUPPORTED_OUTPUTS:
            raise ValueError(f"Unsupported mesh output suffix: {suffix}")
        return output_path
    return build_output_path(input_path, f".{output_format}").resolve()


def read_triangle_mesh(path: Path) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(open3d_path(path))
    if len(mesh.vertices) == 0:
        raise ValueError(f"Input mesh has 0 vertices: {path}")
    if len(mesh.triangles) == 0:
        raise ValueError(f"Input mesh has 0 triangles: {path}")
    cleanup_mesh(mesh)
    mesh.compute_triangle_normals()
    mesh.compute_vertex_normals()
    return mesh


def should_write_ascii(output_path: Path) -> bool:
    return output_path.suffix.lower() == ".ply"


def open3d_path(path: Path) -> str:
    return path.as_posix()


def temporary_write_path(output_path: Path) -> Path:
    return output_path.parent / f"_convert_tmp{output_path.suffix.lower()}"


def write_triangle_mesh_with_fallback(
    output_path: Path,
    mesh: o3d.geometry.TriangleMesh,
) -> bool:
    suffix = output_path.suffix.lower()
    if suffix == ".obj":
        write_obj_mesh(output_path, mesh)
        return True
    if suffix == ".stl":
        write_binary_stl_mesh(output_path, mesh)
        return True

    write_ascii = should_write_ascii(output_path)
    if o3d.io.write_triangle_mesh(open3d_path(output_path), mesh, write_ascii=write_ascii):
        return True

    temp_path = temporary_write_path(output_path)
    if temp_path.exists():
        temp_path.unlink()
    if not o3d.io.write_triangle_mesh(open3d_path(temp_path), mesh, write_ascii=write_ascii):
        return False
    temp_path.replace(output_path)
    return True


def write_obj_mesh(output_path: Path, mesh: o3d.geometry.TriangleMesh) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    colors = np.asarray(mesh.vertex_colors, dtype=np.float64) if mesh.has_vertex_colors() else None

    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write("# Converted by OrbbecGemini215-3DScanner\n")
        for index, vertex in enumerate(vertices):
            if colors is not None and index < len(colors):
                color = np.clip(colors[index], 0.0, 1.0)
                file.write(
                    "v "
                    f"{vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f} "
                    f"{color[0]:.6f} {color[1]:.6f} {color[2]:.6f}\n"
                )
            else:
                file.write(f"v {vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}\n")
        for triangle in triangles:
            file.write(f"f {triangle[0] + 1} {triangle[1] + 1} {triangle[2] + 1}\n")


def write_binary_stl_mesh(output_path: Path, mesh: o3d.geometry.TriangleMesh) -> None:
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    triangle_normals = np.asarray(mesh.triangle_normals, dtype=np.float32)
    if len(triangle_normals) != len(triangles):
        mesh.compute_triangle_normals()
        triangle_normals = np.asarray(mesh.triangle_normals, dtype=np.float32)

    with output_path.open("wb") as file:
        file.write(b"OrbbecGemini215-3DScanner binary STL".ljust(80, b" "))
        file.write(struct.pack("<I", len(triangles)))
        for index, triangle in enumerate(triangles):
            normal = triangle_normals[index] if index < len(triangle_normals) else np.zeros(3)
            file.write(struct.pack("<3f", *normal))
            for vertex_index in triangle:
                file.write(struct.pack("<3f", *vertices[int(vertex_index)]))
            file.write(struct.pack("<H", 0))


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    output_path = resolve_output_path(
        input_path=args.path,
        output_path=args.output,
        output_format=args.format,
    )

    mesh = read_triangle_mesh(args.path)
    print(f"Input mesh: {describe_mesh(mesh)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not write_triangle_mesh_with_fallback(output_path, mesh):
        raise OSError(f"Failed to write mesh: {output_path}")
    print(f"Saved converted mesh to: {output_path}")


if __name__ == "__main__":
    main()
