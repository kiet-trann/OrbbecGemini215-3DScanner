"""Open a saved PLY point cloud with Open3D."""

import _bootstrap  # noqa: F401

import argparse
from pathlib import Path

from scanner_app.visualization.ply_viewer import (
    describe_point_cloud,
    read_point_cloud,
    show_point_cloud,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and view a saved PLY point cloud.")
    parser.add_argument("path", type=Path, help="Path to a .PLY point cloud file.")
    parser.add_argument(
        "--info-only",
        action="store_true",
        help="Only print point cloud information; do not open the Open3D window.",
    )
    parser.add_argument("--point-size", type=float, default=2.0, help="Open3D point size.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)

    cloud = read_point_cloud(args.path)
    print(describe_point_cloud(cloud))

    if args.info_only:
        return

    print("Open3D PLY viewer started. Press Q or close the window to exit.")
    show_point_cloud(
        cloud,
        window_name=f"PLY Viewer - {args.path.name}",
        point_size=args.point_size,
    )


if __name__ == "__main__":
    main()
