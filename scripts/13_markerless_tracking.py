"""Run markerless RGB-D tracking from replayed sessions or Gemini 215 live capture."""

import _bootstrap  # noqa: F401

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from scanner_app.camera.models import CameraIntrinsics, CaptureConfig
from scanner_app.camera.orbbec_capture import OrbbecCapture
from scanner_app.processing.depth_pipeline import DepthProcessor
from scanner_app.recording.session import SessionReplay
from scanner_app.tracking.markerless import MarkerlessTracker
from scanner_app.tracking.models import TrackingResult
from scanner_app.tracking.quality import QualityGate
from scanner_app.tracking.rgbd_odometry import OpenCvRgbdOdometryBackend, RgbdOdometryAdapter


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run markerless RGB-D tracking.")
    parser.add_argument("--replay", type=Path, help="Replay a recorded session directory.")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames; 0 means unlimited.")
    parser.add_argument("--min-depth-m", type=float, default=0.20)
    parser.add_argument("--max-depth-m", type=float, default=0.30)
    parser.add_argument("--min-depth-valid-ratio", type=float, default=0.01)
    parser.add_argument("--warmup-frames", type=int, default=30)
    parser.add_argument("--tracking-width", type=int, default=640)
    parser.add_argument("--tracking-height", type=int, default=400)
    parser.add_argument("--disable-icp", action="store_true")
    parser.add_argument("--print-every", type=int, default=1)
    parser.add_argument("--backend", choices=("open3d", "opencv"), default="open3d")
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


@dataclass
class TrackingSummary:
    frames: int = 0
    accepted: int = 0
    rejected: int = 0
    keyframes: int = 0
    lost: int = 0
    first_timestamp_us: int | None = None
    last_timestamp_us: int | None = None

    def update(self, timestamp_us: int, result: TrackingResult) -> None:
        self.frames += 1
        if result.accepted:
            self.accepted += 1
        else:
            self.rejected += 1
        if result.keyframe:
            self.keyframes += 1
        if result.state.value == "lost":
            self.lost += 1
        if self.first_timestamp_us is None:
            self.first_timestamp_us = int(timestamp_us)
        self.last_timestamp_us = int(timestamp_us)

    def to_json(self) -> dict[str, object]:
        elapsed_s = 0.0
        if self.first_timestamp_us is not None and self.last_timestamp_us is not None:
            elapsed_s = max(0.0, (self.last_timestamp_us - self.first_timestamp_us) / 1_000_000.0)
        accepted_updates = max(0, self.accepted - 1)
        rate = accepted_updates / elapsed_s if elapsed_s > 0.0 else 0.0
        return {
            "summary": True,
            "frames": self.frames,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "keyframes": self.keyframes,
            "lost": self.lost,
            "elapsed_s": elapsed_s,
            "accepted_updates_per_s": rate,
        }


def build_tracker(
    intrinsics: CameraIntrinsics,
    args: argparse.Namespace,
    tracker_factory=MarkerlessTracker,
) -> MarkerlessTracker:
    backend = OpenCvRgbdOdometryBackend() if args.backend == "opencv" else None
    return tracker_factory(
        intrinsics,
        depth_processor=DepthProcessor(args.min_depth_m, args.max_depth_m),
        quality_gate=QualityGate(min_depth_valid_ratio=args.min_depth_valid_ratio),
        odometry=RgbdOdometryAdapter(
            intrinsics,
            backend=backend,
            tracking_width=args.tracking_width,
            tracking_height=args.tracking_height,
            enable_icp=not args.disable_icp,
        ),
    )


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


def should_print_frame(index: int, print_every: int) -> bool:
    return print_every > 0 and index % print_every == 0


def run_replay(
    args: argparse.Namespace,
    replay_factory=SessionReplay,
    tracker_factory=MarkerlessTracker,
) -> None:
    intrinsics = intrinsics_from_args(args)
    tracker = build_tracker(intrinsics, args, tracker_factory=tracker_factory)
    summary = TrackingSummary()
    replay = replay_factory(args.replay)
    for index, packet in enumerate(replay.packets(), start=1):
        result = tracker.process(packet)
        summary.update(packet.depth_timestamp_us, result)
        if should_print_frame(index, args.print_every):
            print_result(packet, result)
        if args.max_frames > 0 and index >= args.max_frames:
            break
    print(json.dumps(summary.to_json(), separators=(",", ":"), sort_keys=True))


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
        for _ in range(max(0, args.warmup_frames)):
            capture.read_packet()
        tracker = build_tracker(capture.intrinsics(), args, tracker_factory=tracker_factory)
        frame_count = 0
        summary = TrackingSummary()
        while True:
            packet = capture.read_packet()
            frame_count += 1
            result = tracker.process(packet)
            summary.update(packet.depth_timestamp_us, result)
            if should_print_frame(frame_count, args.print_every):
                print_result(packet, result)
            if args.max_frames > 0 and frame_count >= args.max_frames:
                break
        print(json.dumps(summary.to_json(), separators=(",", ":"), sort_keys=True))
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
