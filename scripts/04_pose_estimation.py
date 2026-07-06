"""Milestone 4: estimate camera pose from marker observations."""

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
from scanner_app.tracking.aruco import detect_markers
from scanner_app.tracking.pose import (
    camera_pose_from_detection,
    load_marker_world_transforms,
    save_pose_samples_jsonl,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "sessions"
DEFAULT_MARKER_LAYOUT = PROJECT_ROOT / "data" / "calibration" / "marker_layout.example.json"
STATUS_INTERVAL_SECONDS = 2.0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Estimate Gemini 215 camera pose from ArUco markers.")
    parser.add_argument("--dictionary", default="DICT_4X4_50")
    parser.add_argument("--marker-size-m", type=float, default=0.06)
    parser.add_argument("--marker-layout", type=Path, default=DEFAULT_MARKER_LAYOUT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames; 0 means unlimited.")
    return parser


def build_output_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"poses_{timestamp}.jsonl"


def format_pose_status(frame_count: int, elapsed_seconds: float, sample) -> str:
    fps = frame_count / elapsed_seconds if elapsed_seconds > 0 else 0.0
    if sample is None:
        return f"Pose frames: {frame_count} | {fps:.1f} FPS | tracking=LOST"

    x, y, z = sample.camera_to_world[:3, 3]
    return (
        f"Pose frames: {frame_count} | {fps:.1f} FPS | tracking=OK | "
        f"id={sample.marker_id} camera_t=({x:.3f}, {y:.3f}, {z:.3f})m"
    )


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    output_path = args.output or build_output_path()
    marker_world_transforms = load_marker_world_transforms(args.marker_layout)
    camera = OrbbecCapture(align_to_depth=True)

    try:
        camera.start()
        intrinsics = camera.intrinsics()
        print(f"Camera pose estimation started. Writing poses to: {output_path}")

        frame_count = 0
        started_at = time.monotonic()
        last_status_at = started_at

        while True:
            frame = camera.read()
            if frame.color is None:
                raise OrbbecFrameError("Color frame missing; pose estimation requires RGB.")

            detections = detect_markers(
                frame.color,
                intrinsics=intrinsics,
                marker_size_m=args.marker_size_m,
                dictionary_name=args.dictionary,
            )
            sample = None
            for detection in detections:
                marker_to_world = marker_world_transforms.get(detection.marker_id)
                sample = camera_pose_from_detection(
                    detection,
                    timestamp_ms=frame.timestamp_ms,
                    marker_to_world=marker_to_world,
                )
                break

            frame_count += 1
            if sample is not None:
                save_pose_samples_jsonl(output_path, [sample])

            now = time.monotonic()
            if now - last_status_at >= STATUS_INTERVAL_SECONDS:
                print(format_pose_status(frame_count, now - started_at, sample))
                last_status_at = now

            if args.max_frames > 0 and frame_count >= args.max_frames:
                print(format_pose_status(frame_count, time.monotonic() - started_at, sample))
                break

    except OrbbecSdkNotAvailable as error:
        print(error)
    except (OrbbecCameraError, OrbbecFrameError, ValueError) as error:
        print(error)
    finally:
        camera.stop()


if __name__ == "__main__":
    main()
