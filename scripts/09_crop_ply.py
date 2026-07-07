"""Crop a saved PLY point cloud to make the scanned object easier to inspect."""

import _bootstrap  # noqa: F401

import argparse
from pathlib import Path

import numpy as np

from scanner_app.export.ply import write_point_cloud_ply
from scanner_app.processing.pointcloud_crop import (
    crop_axis_aligned,
    keep_largest_cluster,
    remove_dominant_plane,
    voxel_downsample,
)
from scanner_app.visualization.ply_viewer import describe_point_cloud, read_point_cloud


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crop table/background from a saved PLY point cloud.")
    parser.add_argument("path", type=Path, help="Input .PLY point cloud.")
    parser.add_argument("--output", type=Path, default=None, help="Output .PLY path.")
    parser.add_argument(
        "--no-remove-plane",
        action="store_true",
        help="Do not remove the dominant plane before clustering.",
    )
    parser.add_argument(
        "--plane-distance-threshold-m",
        type=float,
        default=0.01,
        help="RANSAC plane inlier distance in meters.",
    )
    parser.add_argument("--plane-ransac-n", type=int, default=3)
    parser.add_argument("--plane-iterations", type=int, default=1000)
    parser.add_argument(
        "--keep-largest-cluster",
        action="store_true",
        help="After plane removal, keep only the largest DBSCAN cluster.",
    )
    parser.add_argument("--cluster-eps-m", type=float, default=0.03)
    parser.add_argument("--cluster-min-points", type=int, default=30)
    parser.add_argument("--voxel-size-m", type=float, default=0.0)
    parser.add_argument("--min-x", type=float, default=None)
    parser.add_argument("--max-x", type=float, default=None)
    parser.add_argument("--min-y", type=float, default=None)
    parser.add_argument("--max-y", type=float, default=None)
    parser.add_argument("--min-z", type=float, default=None)
    parser.add_argument("--max-z", type=float, default=None)
    return parser


def build_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_cropped{input_path.suffix}")


def resolve_output_path(*, output_path: Path | None, input_path: Path) -> Path:
    return (output_path or build_output_path(input_path)).resolve()


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    output_path = resolve_output_path(output_path=args.output, input_path=args.path)

    cloud = read_point_cloud(args.path)
    print(f"Input:  {describe_point_cloud(cloud)}")

    if has_manual_bounds(args):
        cloud = crop_axis_aligned(
            cloud,
            min_bound=np.array(
                [
                    -np.inf if args.min_x is None else args.min_x,
                    -np.inf if args.min_y is None else args.min_y,
                    -np.inf if args.min_z is None else args.min_z,
                ],
                dtype=np.float64,
            ),
            max_bound=np.array(
                [
                    np.inf if args.max_x is None else args.max_x,
                    np.inf if args.max_y is None else args.max_y,
                    np.inf if args.max_z is None else args.max_z,
                ],
                dtype=np.float64,
            ),
        )
        print(f"After manual bounds: {describe_point_cloud(cloud)}")

    if not args.no_remove_plane:
        plane_result = remove_dominant_plane(
            cloud,
            distance_threshold_m=args.plane_distance_threshold_m,
            ransac_n=args.plane_ransac_n,
            num_iterations=args.plane_iterations,
        )
        cloud = plane_result.cloud
        print(
            f"Removed dominant plane: {plane_result.removed_points} points | "
            f"{describe_point_cloud(cloud)}"
        )

    if args.keep_largest_cluster:
        cloud, cluster_count = keep_largest_cluster(
            cloud,
            eps=args.cluster_eps_m,
            min_points=args.cluster_min_points,
        )
        print(f"Kept largest cluster from {cluster_count} clusters: {describe_point_cloud(cloud)}")

    cloud = voxel_downsample(cloud, args.voxel_size_m)
    if args.voxel_size_m > 0:
        print(f"After voxel downsample: {describe_point_cloud(cloud)}")

    if len(cloud.points) == 0:
        raise ValueError("Crop result is empty. Relax crop or clustering parameters.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_point_cloud_ply(
        output_path,
        np.asarray(cloud.points, dtype=np.float32),
        colors_rgb=np.asarray(cloud.colors, dtype=np.float32) if cloud.has_colors() else None,
        prefer_ascii=True,
    )
    print(f"Saved cropped point cloud to: {output_path}")


def has_manual_bounds(args: argparse.Namespace) -> bool:
    return any(
        value is not None
        for value in (args.min_x, args.max_x, args.min_y, args.max_y, args.min_z, args.max_z)
    )


if __name__ == "__main__":
    main()
