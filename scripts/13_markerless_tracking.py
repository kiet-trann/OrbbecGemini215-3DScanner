"""Run markerless RGB-D tracking from replayed sessions or Gemini 215 live capture."""

import _bootstrap  # noqa: F401

import argparse
import json
from pathlib import Path

from scanner_app.camera.models import CameraIntrinsics, CaptureConfig
from scanner_app.camera.orbbec_capture import OrbbecCapture
from scanner_app.processing.depth_pipeline import DepthProcessor
from scanner_app.recording.session import SessionReplay
from scanner_app.tracking.markerless import MarkerlessTracker
from scanner_app.tracking.models import TrackingResult


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run markerless RGB-D tracking.")
    parser.add_argument("--replay", type=Path, help="Replay a recorded session directory.")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames; 0 means unlimited.")
    parser.add_argument("--min-depth-m", type=float, default=0.20)
    parser.add_argument("--max-depth-m", type=float, default=0.30)
    parser.add_argument("--record-accepted", action="store_true", help="Keep accepted keyframes in tracker state.")
    parser.add_argument("--no-live", action="store_true", help="Require --replay instead of opening live capture.")
    parser.add_argument("--intrinsics-fx", type=float)
    parser.add_argument("--intrinsics-fy", type=float)
    parser.add_argument("--intrinsics-cx", type=float)
    parser.add_argument("--intrinsics-cy", type=float)
    parser.add_argument("--intrinsics-width", type=int)
    parser.add_argument("--intrinsics-height", type=int)
    return parser


def intrinsics_from_args(args: argparse.Namespace) -> CameraIntrinsics:
    values = {
        "fx": args.intrinsics_fx,
        "fy": args.intrinsics_fy,
        "cx": args.intrinsics_cx,
        "cy": args.intrinsics_cy,
        "width": args.intrinsics_width,
        "height": args.intrinsics_height,
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        raise ValueError("Replay mode requires intrinsics: " + ", ".join(missing))
    return CameraIntrinsics(**values)


def result_to_json(
    *,
    sequence: int,
    timestamp_us: int,
    result: TrackingResult,
) -> dict[str, object]:
    metrics = result.metrics
    return {
        "sequence": int(sequence),
        "timestamp_us": int(timestamp_us),
        "state": result.state.value,
        "accepted": bool(result.accepted),
        "keyframe": bool(result.keyframe),
        "reason": result.reason,
        "fitness": metrics.fitness,
        "rmse_m": metrics.rmse_m,
        "translation_m": metrics.translation_m,
        "rotation_deg": metrics.rotation_deg,
        "depth_valid_ratio": metrics.depth_valid_ratio,
        "pose": result.camera_to_world.tolist(),
    }


def print_result(packet, result: TrackingResult) -> None:
    print(
        json.dumps(
            result_to_json(
                sequence=packet.sequence,
                timestamp_us=packet.depth_timestamp_us,
            result=result,
            ),
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def run_replay(
    args: argparse.Namespace,
    replay_factory=SessionReplay,
    tracker_factory=MarkerlessTracker,
) -> None:
    intrinsics = intrinsics_from_args(args)
    tracker = tracker_factory(
        intrinsics,
        depth_processor=DepthProcessor(args.min_depth_m, args.max_depth_m),
    )
    replay = replay_factory(args.replay)
    for index, packet in enumerate(replay.packets(), start=1):
        print_result(packet, tracker.process(packet))
        if args.max_frames > 0 and index >= args.max_frames:
            break


def run_live(
    args: argparse.Namespace,
    capture_factory=OrbbecCapture,
    tracker_factory=MarkerlessTracker,
) -> None:
    capture = capture_factory(
        capture_config=CaptureConfig(
            depth_min_m=args.min_depth_m,
            depth_max_m=args.max_depth_m,
        ),
        align_to_depth=True,
    )
    try:
        capture.start()
        tracker = tracker_factory(
            capture.intrinsics(),
            depth_processor=DepthProcessor(args.min_depth_m, args.max_depth_m),
        )
        frame_count = 0
        while True:
            packet = capture.read_packet()
            print_result(packet, tracker.process(packet))
            frame_count += 1
            if args.max_frames > 0 and frame_count >= args.max_frames:
                break
    finally:
        capture.stop()


def main(argv: list[str] | None = None) -> None:
    args = build_argument_parser().parse_args(argv)
    if args.replay is not None:
        run_replay(args)
        return
    if args.no_live:
        raise SystemExit("--no-live requires --replay")
    run_live(args)


if __name__ == "__main__":
    main()
