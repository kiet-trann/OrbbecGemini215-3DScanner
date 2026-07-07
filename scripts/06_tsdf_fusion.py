"""Milestone 6: integrate RGB-D frames into a TSDF mesh."""

import _bootstrap  # noqa: F401

import argparse
from datetime import datetime
from pathlib import Path
import sys
import time

import numpy as np
import open3d as o3d

from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.fusion.tsdf import create_tsdf_volume, integrate_rgbd_frame
from scanner_app.processing.mesh_reconstruction import cleanup_mesh, describe_mesh
from scanner_app.tracking.aruco import detect_markers_with_rejected, draw_marker_detections
from scanner_app.tracking.pose import camera_pose_from_detection, load_marker_world_transforms


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ply"
DEFAULT_MARKER_LAYOUT = PROJECT_ROOT / "data" / "calibration" / "marker_layout.example.json"
STATUS_INTERVAL_SECONDS = 2.0
PREVIEW_WINDOW_NAME = "Gemini 215 TSDF Fusion Preview"
ESC_KEY = 27


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fuse Gemini 215 RGB-D frames into a TSDF mesh.")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--marker-size-m", type=float, default=0.06)
    parser.add_argument("--marker-layout", type=Path, default=DEFAULT_MARKER_LAYOUT)
    parser.add_argument("--min-depth-m", type=float, default=0.15)
    parser.add_argument("--max-depth-m", type=float, default=0.70)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--capture-seconds", type=float, default=30.0)
    parser.add_argument("--target-tracked-frames", type=int, default=0)
    parser.add_argument(
        "--tracked-frame-stride",
        type=int,
        default=4,
        help="Integrate one out of every N marker-tracked frames.",
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--voxel-length-m", type=float, default=0.002)
    parser.add_argument("--sdf-trunc-m", type=float, default=0.010)
    parser.add_argument("--roi-min-x", type=float, default=None)
    parser.add_argument("--roi-max-x", type=float, default=None)
    parser.add_argument("--roi-min-y", type=float, default=None)
    parser.add_argument("--roi-max-y", type=float, default=None)
    parser.add_argument("--roi-min-z", type=float, default=None)
    parser.add_argument("--roi-max-z", type=float, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--pointcloud-output",
        type=Path,
        default=None,
        help="Optional PLY path for the TSDF-extracted point cloud.",
    )
    return parser


def build_output_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"tsdf_mesh_{timestamp}.ply"


def build_pointcloud_output_path(mesh_output_path: Path) -> Path:
    return mesh_output_path.with_name(f"{mesh_output_path.stem}_cloud.ply")


def build_roi_bounds(args: argparse.Namespace) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.array(
            [
                -np.inf if args.roi_min_x is None else args.roi_min_x,
                -np.inf if args.roi_min_y is None else args.roi_min_y,
                -np.inf if args.roi_min_z is None else args.roi_min_z,
            ],
            dtype=np.float32,
        ),
        np.array(
            [
                np.inf if args.roi_max_x is None else args.roi_max_x,
                np.inf if args.roi_max_y is None else args.roi_max_y,
                np.inf if args.roi_max_z is None else args.roi_max_z,
            ],
            dtype=np.float32,
        ),
    )


def validate_roi_bounds(min_bound: np.ndarray, max_bound: np.ndarray) -> None:
    for axis_name, min_value, max_value in zip(("x", "y", "z"), min_bound, max_bound):
        if np.isfinite(min_value) and np.isfinite(max_value) and min_value >= max_value:
            raise ValueError(f"ROI min {axis_name} must be smaller than ROI max {axis_name}.")


def should_process_tracked_frame(*, marker_frame_count: int, stride: int) -> bool:
    if stride <= 1:
        return True
    return (marker_frame_count - 1) % stride == 0


def should_stop_capture(
    *,
    frame_count: int,
    integrated_frames: int,
    max_frames: int,
    target_tracked_frames: int,
    elapsed_seconds: float,
    capture_seconds: float,
) -> bool:
    if target_tracked_frames > 0 and integrated_frames >= target_tracked_frames:
        return True
    if capture_seconds > 0 and elapsed_seconds >= capture_seconds:
        return True
    return max_frames > 0 and frame_count >= max_frames


def format_tsdf_status(
    *,
    frame_count: int,
    elapsed_seconds: float,
    marker_frames: int,
    integrated_frames: int,
    skipped_frames: int,
    no_marker_frames: int,
    empty_roi_frames: int,
    rejected_count: int,
    integrated_pixels: int,
) -> str:
    fps = frame_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    return (
        f"TSDF frames: {frame_count} | {fps:.1f} FPS | markers={marker_frames} | "
        f"integrated={integrated_frames} | skipped={skipped_frames} | "
        f"no_marker={no_marker_frames} | empty_roi={empty_roi_frames} | "
        f"rejected={rejected_count} | pixels={integrated_pixels}"
    )


def format_preview_overlay(
    *,
    elapsed_seconds: float,
    capture_seconds: float,
    marker_count: int,
    integrated_frames: int,
    empty_roi_frames: int,
    integrated_pixels: int,
) -> str:
    time_status = f"{elapsed_seconds:.1f}s"
    if capture_seconds > 0:
        time_status = f"{elapsed_seconds:.1f}/{capture_seconds:.1f}s"
    return (
        f"{time_status} | markers={marker_count} | integrated={integrated_frames} "
        f"empty={empty_roi_frames} | pixels={integrated_pixels}"
    )


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.tracked_frame_stride < 1:
        raise ValueError("--tracked-frame-stride must be 1 or greater.")
    if args.voxel_length_m <= 0:
        raise ValueError("--voxel-length-m must be greater than 0.")
    if args.sdf_trunc_m <= 0:
        raise ValueError("--sdf-trunc-m must be greater than 0.")

    roi_min_bound, roi_max_bound = build_roi_bounds(args)
    validate_roi_bounds(roi_min_bound, roi_max_bound)
    output_path = (args.output or build_output_path()).resolve()
    pointcloud_output_path = (
        args.pointcloud_output.resolve()
        if args.pointcloud_output is not None
        else build_pointcloud_output_path(output_path)
    )

    marker_world_transforms = load_marker_world_transforms(args.marker_layout)
    camera = OrbbecCapture(align_to_depth=True)
    volume = create_tsdf_volume(
        voxel_length_m=args.voxel_length_m,
        sdf_trunc_m=args.sdf_trunc_m,
        with_color=True,
    )
    cv2 = None

    try:
        if args.preview:
            import cv2 as cv2_module

            cv2 = cv2_module
            cv2.namedWindow(PREVIEW_WINDOW_NAME, cv2.WINDOW_NORMAL)

        camera.start()
        intrinsics = camera.intrinsics()
        print(f"TSDF fusion started. Writing mesh PLY to: {output_path}")
        print(
            "Marker/world ROI: "
            f"min={tuple(float(value) for value in roi_min_bound)} "
            f"max={tuple(float(value) for value in roi_max_bound)}"
        )
        if args.preview:
            print("TSDF preview started. Keep marker and object in view. Press Q or ESC to stop.")

        frame_count = 0
        marker_frames = 0
        integrated_frames = 0
        skipped_frames = 0
        no_marker_frames = 0
        empty_roi_frames = 0
        rejected_count = 0
        integrated_pixels = 0
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
                    if should_process_tracked_frame(
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
                        valid_pixels = integrate_rgbd_frame(
                            volume,
                            frame=frame,
                            intrinsics=intrinsics,
                            camera_to_world=pose_sample.camera_to_world,
                            min_depth_m=args.min_depth_m,
                            max_depth_m=args.max_depth_m,
                            min_bound=roi_min_bound,
                            max_bound=roi_max_bound,
                        )
                        if valid_pixels > 0:
                            integrated_frames += 1
                            integrated_pixels += valid_pixels
                        else:
                            skipped_frames += 1
                            empty_roi_frames += 1
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
                    integrated_frames=integrated_frames,
                    empty_roi_frames=empty_roi_frames,
                    integrated_pixels=integrated_pixels,
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
                    format_tsdf_status(
                        frame_count=frame_count,
                        elapsed_seconds=now - started_at,
                        marker_frames=marker_frames,
                        integrated_frames=integrated_frames,
                        skipped_frames=skipped_frames,
                        no_marker_frames=no_marker_frames,
                        empty_roi_frames=empty_roi_frames,
                        rejected_count=rejected_count,
                        integrated_pixels=integrated_pixels,
                    )
                )
                last_status_at = now

            if should_stop_capture(
                frame_count=frame_count,
                integrated_frames=integrated_frames,
                max_frames=args.max_frames,
                target_tracked_frames=args.target_tracked_frames,
                elapsed_seconds=now - started_at,
                capture_seconds=args.capture_seconds,
            ):
                break

        print(
            format_tsdf_status(
                frame_count=frame_count,
                elapsed_seconds=time.monotonic() - started_at,
                marker_frames=marker_frames,
                integrated_frames=integrated_frames,
                skipped_frames=skipped_frames,
                no_marker_frames=no_marker_frames,
                empty_roi_frames=empty_roi_frames,
                rejected_count=rejected_count,
                integrated_pixels=integrated_pixels,
            )
        )
        if integrated_frames == 0:
            raise OrbbecFrameError("No TSDF frames were integrated. Relax ROI or improve tracking.")

        mesh = volume.extract_triangle_mesh()
        cleanup_mesh(mesh)
        if len(mesh.triangles) == 0:
            raise OrbbecFrameError("TSDF produced 0 triangles. Try smaller voxel or wider ROI.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not o3d.io.write_triangle_mesh(str(output_path), mesh):
            raise OrbbecFrameError(f"Failed to write TSDF mesh: {output_path}")

        cloud = volume.extract_point_cloud()
        pointcloud_output_path.parent.mkdir(parents=True, exist_ok=True)
        o3d.io.write_point_cloud(str(pointcloud_output_path), cloud, write_ascii=True)
        print(f"Saved TSDF mesh {describe_mesh(mesh)} to: {output_path}")
        print(f"Saved TSDF point cloud with {len(cloud.points)} points to: {pointcloud_output_path}")

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
