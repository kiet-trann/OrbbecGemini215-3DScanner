"""Reconstruct a triangle mesh from a cropped PLY point cloud."""

import _bootstrap  # noqa: F401

import argparse
from pathlib import Path

import open3d as o3d

from scanner_app.processing.mesh_reconstruction import describe_mesh, reconstruct_mesh
from scanner_app.visualization.ply_viewer import describe_point_cloud, read_point_cloud


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ply"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconstruct and export a mesh from a PLY cloud.")
    parser.add_argument("path", type=Path, help="Input cropped .PLY point cloud.")
    parser.add_argument("--output", type=Path, default=None, help="Output mesh path: .ply, .obj, .stl.")
    parser.add_argument(
        "--method",
        choices=("ball-pivoting", "poisson", "alpha"),
        default="ball-pivoting",
    )
    parser.add_argument("--normal-radius-m", type=float, default=0.02)
    parser.add_argument("--normal-max-nn", type=int, default=30)
    parser.add_argument("--orient-k", type=int, default=20)
    parser.add_argument("--ball-radius-m", type=float, default=0.0)
    parser.add_argument("--ball-radius-scales", type=float, nargs="+", default=[1.5, 2.5, 4.0])
    parser.add_argument("--poisson-depth", type=int, default=8)
    parser.add_argument("--poisson-density-quantile", type=float, default=0.02)
    parser.add_argument("--alpha", type=float, default=0.03)
    return parser


def build_output_path(input_path: Path) -> Path:
    return OUTPUT_DIR / f"{input_path.stem}_mesh.ply"


def resolve_output_path(*, output_path: Path | None, input_path: Path) -> Path:
    return (output_path or build_output_path(input_path)).resolve()


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    output_path = resolve_output_path(output_path=args.output, input_path=args.path)

    cloud = read_point_cloud(args.path)
    print(f"Input cloud: {describe_point_cloud(cloud)}")

    mesh = reconstruct_mesh(
        cloud,
        method=args.method,
        normal_radius_m=args.normal_radius_m,
        normal_max_nn=args.normal_max_nn,
        orient_k=args.orient_k,
        ball_radius_m=args.ball_radius_m,
        ball_radius_scales=args.ball_radius_scales,
        poisson_depth=args.poisson_depth,
        poisson_density_quantile=args.poisson_density_quantile,
        alpha=args.alpha,
    )
    print(f"Mesh: {describe_mesh(mesh)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(output_path), mesh):
        raise OSError(f"Failed to write mesh: {output_path}")
    print(f"Saved mesh to: {output_path}")


if __name__ == "__main__":
    main()
