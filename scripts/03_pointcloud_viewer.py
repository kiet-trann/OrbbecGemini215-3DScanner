"""Display a real-time point cloud from Gemini 215 depth frames."""

import _bootstrap  # noqa: F401

import argparse
import time

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.pointcloud.generate import rgbd_frame_to_point_cloud
from scanner_app.visualization.open3d_pointcloud import (
    Open3DPointCloudViewer,
    format_pointcloud_status,
)


STATUS_INTERVAL_SECONDS = 2.0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Real-time Orbbec Gemini 215 point cloud viewer.")
    parser.add_argument("--min-depth-m", type=float, default=0.15)
    parser.add_argument("--max-depth-m", type=float, default=1.50)
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames; 0 means unlimited.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Read and process frames without opening the Open3D window.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    camera = OrbbecCapture(align_to_depth=True)
    viewer = None

    try:
        camera.start()
        intrinsics = camera.intrinsics()

        if not args.headless:
            viewer = Open3DPointCloudViewer()
            print("Open3D point cloud viewer started. Press Q or close the window to exit.")
        else:
            print("Headless point cloud capture started.")

        frame_count = 0
        started_at = time.monotonic()
        last_status_at = started_at

        while True:
            frame = camera.read()
            point_cloud = rgbd_frame_to_point_cloud(
                frame,
                intrinsics,
                min_depth_m=args.min_depth_m,
                max_depth_m=args.max_depth_m,
            )
            frame_count += 1

            if viewer is not None and not viewer.update(point_cloud):
                break

            now = time.monotonic()
            if now - last_status_at >= STATUS_INTERVAL_SECONDS or args.headless:
                print(
                    format_pointcloud_status(
                        frame_count,
                        now - started_at,
                        len(point_cloud.points_xyz),
                        has_color=point_cloud.colors_rgb is not None,
                    )
                )
                last_status_at = now

            if args.max_frames > 0 and frame_count >= args.max_frames:
                break

    except OrbbecSdkNotAvailable as error:
        print(error)
    except (OrbbecCameraError, OrbbecFrameError) as error:
        print(error)
    finally:
        if viewer is not None:
            viewer.close()
        camera.stop()


if __name__ == "__main__":
    main()
