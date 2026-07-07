"""Milestone 5: merge multiple point clouds by camera pose."""

import _bootstrap  # noqa: F401

import argparse
from datetime import datetime
from pathlib import Path
import sys
import time

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.export.ply import write_point_cloud_ply
from scanner_app.fusion.merge import (
    merge_point_clouds,
    transform_point_cloud,
    voxel_downsample_point_cloud,
)
from scanner_app.pointcloud.generate import PointCloudData, rgbd_frame_to_point_cloud
from scanner_app.tracking.aruco import detect_markers_with_rejected, draw_marker_detections
from scanner_app.tracking.pose import camera_pose_from_detection, load_marker_world_transforms


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ply"
DEFAULT_MARKER_LAYOUT = PROJECT_ROOT / "data" / "calibration" / "marker_layout.example.json"
STATUS_INTERVAL_SECONDS = 2.0
PREVIEW_WINDOW_NAME = "Gemini 215 Merge Preview"
ESC_KEY = 27


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge Gemini 215 point clouds using marker poses.")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--marker-size-m", type=float, default=0.06)
    parser.add_argument("--marker-layout", type=Path, default=DEFAULT_MARKER_LAYOUT)
    parser.add_argument("--min-depth-m", type=float, default=0.15)
    parser.add_argument("--max-depth-m", type=float, default=1.50)
    parser.add_argument(
        "--max-frames",
        type=int,
        default=120,
        help="Stop after N total camera frames; ignored with --capture-seconds unless set explicitly.",
    )
    parser.add_argument(
        "--capture-seconds",
        type=float,
        default=0.0,
        help="Stop after this many seconds; 0 disables time-based capture.",
    )
    parser.add_argument(
        "--target-tracked-frames",
        type=int,
        default=0,
        help="Stop after N frames with valid marker pose; 0 disables this target.",
    )
    parser.add_argument(
        "--tracked-frame-stride",
        type=int,
        default=1,
        help="Merge one out of every N marker-tracked frames; 1 keeps every tracked frame.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show the RGB camera preview with marker overlay while merging.",
    )
    parser.add_argument(
        "--voxel-size-m",
        type=float,
        default=0.0,
        help="Downsample merged cloud with this voxel size in meters; 0 disables downsampling.",
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


def format_preview_overlay(
    *,
    elapsed_seconds: float,
    capture_seconds: float,
    marker_count: int,
    rejected_count: int,
    tracked_frames: int,
    skipped_frames: int,
    merged_points: int,
) -> str:
    time_status = f"{elapsed_seconds:.1f}s"
    if capture_seconds > 0:
        time_status = f"{elapsed_seconds:.1f}/{capture_seconds:.1f}s"
    return (
        f"{time_status} | markers={marker_count} rejected={rejected_count} | "
        f"merged={tracked_frames} skipped={skipped_frames} | points={merged_points}"
    )


def should_stop_capture(
    *,
    frame_count: int,
    tracked_frames: int,
    max_frames: int,
    target_tracked_frames: int,
    elapsed_seconds: float,
    capture_seconds: float,
) -> bool:
    if target_tracked_frames > 0 and tracked_frames >= target_tracked_frames:
        return True
    if capture_seconds > 0 and elapsed_seconds >= capture_seconds:
        return True
    return max_frames > 0 and frame_count >= max_frames


def should_merge_tracked_frame(*, marker_frame_count: int, stride: int) -> bool:
    if stride <= 1:
        return True
    return (marker_frame_count - 1) % stride == 0


def resolve_effective_max_frames(
    *,
    max_frames: int,
    capture_seconds: float,
    max_frames_supplied: bool,
) -> int:
    if capture_seconds > 0 and not max_frames_supplied:
        return 0
    return max_frames


def main(argv: list[str] | None = None) -> None:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = build_argument_parser().parse_args(raw_argv)
    if args.tracked_frame_stride < 1:
        raise ValueError("--tracked-frame-stride must be 1 or greater.")
    effective_max_frames = resolve_effective_max_frames(
        max_frames=args.max_frames,
        capture_seconds=args.capture_seconds,
        max_frames_supplied="--max-frames" in raw_argv,
    )
    output_path = args.output or build_output_path()
    marker_world_transforms = load_marker_world_transforms(args.marker_layout)
    camera = OrbbecCapture(align_to_depth=True)
    transformed_clouds: list[PointCloudData] = []
    cv2 = None

    try:
        if args.preview:
            import cv2 as cv2_module

            cv2 = cv2_module
            cv2.namedWindow(PREVIEW_WINDOW_NAME, cv2.WINDOW_NORMAL)

        camera.start()
        intrinsics = camera.intrinsics()
        print(f"Point cloud merge started. Writing merged PLY to: {output_path}")
        if args.preview:
            print("Merge preview started. Keep marker and object in view. Press Q or ESC to stop.")

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
            detections = []
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
                    if should_merge_tracked_frame(
                        marker_frame_count=marker_frames,
                        stride=args.tracked_frame_stride,
                    ):
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
                else:
                    skipped_frames += 1
                    no_marker_frames += 1

            now = time.monotonic()
            if args.preview and cv2 is not None and frame.color is not None:
                display = draw_marker_detections(
                    frame.color,
                    detections,
                    intrinsics,
                    marker_size_m=args.marker_size_m,
                )
                overlay = format_preview_overlay(
                    elapsed_seconds=now - started_at,
                    capture_seconds=args.capture_seconds,
                    marker_count=len(detections),
                    rejected_count=rejected_count,
                    tracked_frames=tracked_frames,
                    skipped_frames=skipped_frames,
                    merged_points=merged_points,
                )
                cv2.putText(
                    display,
                    overlay,
                    (16, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0) if detections else (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow(PREVIEW_WINDOW_NAME, display)
                key = cv2.waitKey(1)
                if key in (ord("q"), ord("Q"), ESC_KEY):
                    break

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
                max_frames=effective_max_frames,
                target_tracked_frames=args.target_tracked_frames,
                elapsed_seconds=now - started_at,
                capture_seconds=args.capture_seconds,
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

        raw_point_count = len(merged_cloud.points_xyz)
        merged_cloud = voxel_downsample_point_cloud(merged_cloud, args.voxel_size_m)
        if args.voxel_size_m > 0:
            print(
                f"Voxel downsampled merged cloud from {raw_point_count} to "
                f"{len(merged_cloud.points_xyz)} points at {args.voxel_size_m:.4f}m."
            )

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
        if cv2 is not None:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
