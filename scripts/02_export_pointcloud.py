"""Milestone 2: export a single-frame point cloud to PLY."""

import _bootstrap  # noqa: F401

from datetime import datetime
from pathlib import Path

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.export.ply import write_point_cloud_ply
from scanner_app.pointcloud.generate import rgbd_frame_to_point_cloud


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ply"
MIN_DEPTH_M = 0.15
MAX_DEPTH_M = 1.50


def build_output_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"single_frame_{timestamp}.ply"


def main() -> None:
    camera = OrbbecCapture()
    try:
        camera.start()
        print("Capturing one RGB-D frame from Gemini 215...")
        frame = camera.read()
        intrinsics = camera.intrinsics()

        point_cloud = rgbd_frame_to_point_cloud(
            frame,
            intrinsics,
            min_depth_m=MIN_DEPTH_M,
            max_depth_m=MAX_DEPTH_M,
        )
        if point_cloud.points_xyz.size == 0:
            raise OrbbecFrameError(
                f"No valid depth points in range {MIN_DEPTH_M:.2f}m-{MAX_DEPTH_M:.2f}m."
            )

        output_path = build_output_path()
        write_point_cloud_ply(
            output_path,
            point_cloud.points_xyz,
            colors_rgb=point_cloud.colors_rgb,
        )

        color_status = "with color" if point_cloud.colors_rgb is not None else "depth-only"
        print(
            f"Saved {len(point_cloud.points_xyz)} {color_status} points "
            f"({MIN_DEPTH_M:.2f}m-{MAX_DEPTH_M:.2f}m) to: {output_path}"
        )
    except OrbbecSdkNotAvailable as error:
        print(error)
    except (OrbbecCameraError, OrbbecFrameError) as error:
        print(error)
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
