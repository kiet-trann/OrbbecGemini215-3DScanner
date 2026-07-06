"""Milestone 5: merge multiple point clouds by camera pose."""

import _bootstrap  # noqa: F401

import argparse
from datetime import datetime
from pathlib import Path
import time

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.export.ply import write_point_cloud_ply
from scanner_app.fusion.merge import merge_point_clouds, transform_point_cloud
from scanner_app.pointcloud.generate import PointCloudData, rgbd_frame_to_point_cloud
from scanner_app.tracking.aruco import detect_markers_with_rejected
from scanner_app.tracking.pose import camera_pose_from_detection, load_marker_world_transforms


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ply"
DEFAULT_MARKER_LAYOUT = PROJECT_ROOT / "data" / "calibration" / "marker_layout.example.json"
STATUS_INTERVAL_SECONDS = 2.0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge Gemini 215 point clouds using marker poses.")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--marker-size-m", type=float, default=0.06)
    parser.add_argument("--marker-layout", type=Path, default=DEFAULT_MARKER_LAYOUT)
    parser.add_argument("--min-depth-m", type=float, default=0.15)
    parser.add_argument("--max-depth-m", type=float, default=1.50)
    parser.add_argument("--max-frames", type=int, default=120)
    parser.add_argument(
        "--target-tracked-frames",
        type=int,
        default=0,
        help="Stop after N frames with valid marker pose; 0 disables this target.",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser


def build_output_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"merged_cloud_{timestamp}.ply"


def format_merge_status(
    frame_count: int,
    elapsed_seconds: float,
    tracked_frames: int,
    skipped_frames: int,
    marker_frames: int,
    no_marker_frames: int,
    empty_cloud_frames: int,
    rejected_count: int,
    merged_points: int,
) -> str:
    fps = frame_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    return (
        f"Merge frames: {frame_count} | {fps:.1f} FPS | tracked={tracked_frames} | "
        f"skipped={skipped_frames} | markers={marker_frames} | "
        f"no_marker={no_marker_frames} | empty_cloud={empty_cloud_frames} | "
        f"rejected={rejected_count} | merged_points={merged_points}"
    )


def should_stop_capture(
    *,
    frame_count: int,
    tracked_frames: int,
    max_frames: int,
    target_tracked_frames: int,
) -> bool:
    if target_tracked_frames > 0 and tracked_frames >= target_tracked_frames:
        return True
    return max_frames > 0 and frame_count >= max_frames


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    output_path = args.output or build_output_path()
    marker_world_transforms = load_marker_world_transforms(args.marker_layout)
    camera = OrbbecCapture(align_to_depth=True)
    transformed_clouds: list[PointCloudData] = []

    try:
        camera.start()
        intrinsics = camera.intrinsics()
        print(f"Point cloud merge started. Writing merged PLY to: {output_path}")

        frame_count = 0
        tracked_frames = 0
        skipped_frames = 0
        marker_frames = 0
        no_marker_frames = 0
        empty_cloud_frames = 0
        rejected_count = 0
        merged_points = 0
        started_at = time.monotonic()
        last_status_at = started_at

        while True:
            frame = camera.read()
            frame_count += 1
            if frame.color is None:
                skipped_frames += 1
                no_marker_frames += 1
            else:
                detections, frame_rejected_count = detect_markers_with_rejected(
                    frame.color,
                    intrinsics=intrinsics,
                    marker_size_m=args.marker_size_m,
                    dictionary_name=args.dictionary,
                )
                rejected_count = frame_rejected_count
                if detections:
                    marker_frames += 1
                    detection = detections[0]
                    marker_to_world = marker_world_transforms.get(detection.marker_id)
                    pose_sample = camera_pose_from_detection(
                        detection,
                        timestamp_ms=frame.timestamp_ms,
                        marker_to_world=marker_to_world,
                    )
                    point_cloud = rgbd_frame_to_point_cloud(
                        frame,
                        intrinsics,
                        min_depth_m=args.min_depth_m,
                        max_depth_m=args.max_depth_m,
                    )
                    if len(point_cloud.points_xyz) > 0:
                        world_cloud = transform_point_cloud(
                            point_cloud,
                            pose_sample.camera_to_world,
                        )
                        transformed_clouds.append(world_cloud)
                        merged_points += len(world_cloud.points_xyz)
                        tracked_frames += 1
                    else:
                        skipped_frames += 1
                        empty_cloud_frames += 1
                else:
                    skipped_frames += 1
                    no_marker_frames += 1

            now = time.monotonic()
            if now - last_status_at >= STATUS_INTERVAL_SECONDS:
                print(
                    format_merge_status(
                        frame_count,
                        now - started_at,
                        tracked_frames,
                        skipped_frames,
                        marker_frames,
                        no_marker_frames,
                        empty_cloud_frames,
                        rejected_count,
                        merged_points,
                    )
                )
                last_status_at = now

            if should_stop_capture(
                frame_count=frame_count,
                tracked_frames=tracked_frames,
                max_frames=args.max_frames,
                target_tracked_frames=args.target_tracked_frames,
            ):
                break

        print(
            format_merge_status(
                frame_count,
                time.monotonic() - started_at,
                tracked_frames,
                skipped_frames,
                marker_frames,
                no_marker_frames,
                empty_cloud_frames,
                rejected_count,
                merged_points,
            )
        )

        merged_cloud = merge_point_clouds(transformed_clouds)
        if len(merged_cloud.points_xyz) == 0:
            raise OrbbecFrameError("No tracked point cloud frames were captured.")

        write_point_cloud_ply(
            output_path,
            merged_cloud.points_xyz,
            colors_rgb=merged_cloud.colors_rgb,
        )
        print(
            f"Saved merged point cloud with {len(merged_cloud.points_xyz)} points "
            f"from {tracked_frames} tracked frames to: {output_path}"
        )

    except OrbbecSdkNotAvailable as error:
        print(error)
    except (OrbbecCameraError, OrbbecFrameError, ValueError) as error:
        print(error)
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
