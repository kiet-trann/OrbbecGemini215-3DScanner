"""Report whether color remains visible while depth is aligned to color."""

import _bootstrap  # noqa: F401

import argparse
import json
import time

from scanner_app.camera.diagnostics import summarize_capture_visibility
from scanner_app.camera.models import CaptureConfig
from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Gemini RGB/depth alignment at object edges.")
    parser.add_argument("--alignment-target", choices=("color", "depth", "none"), default="color")
    parser.add_argument("--min-depth-m", type=float, default=0.20)
    parser.add_argument("--max-depth-m", type=float, default=0.40)
    parser.add_argument("--capture-seconds", type=float, default=10.0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--headless", action="store_true")
    return parser


def diagnostic_payload(packet, args: argparse.Namespace) -> dict[str, object]:
    diagnostic = summarize_capture_visibility(
        packet.color_bgr,
        args.alignment_target,
        packet.depth_raw,
        depth_scale_mm=packet.depth_scale_mm,
        min_depth_m=args.min_depth_m,
        max_depth_m=args.max_depth_m,
    )
    return {
        "sequence": packet.sequence,
        "color_visible": diagnostic.color_visible,
        "alignment_target": diagnostic.alignment_target,
        "depth_valid_ratio": diagnostic.depth_valid_ratio,
        "color_shape": list(packet.color_bgr.shape),
        "depth_shape": list(packet.depth_raw.shape),
    }


def run(args: argparse.Namespace, capture_factory=OrbbecCapture) -> dict[str, object]:
    capture = capture_factory(
        capture_config=CaptureConfig(depth_min_m=args.min_depth_m, depth_max_m=args.max_depth_m),
        alignment_target=args.alignment_target,
    )
    started = time.monotonic()
    latest: dict[str, object] = {}
    frames = 0
    try:
        capture.start()
        while True:
            latest = diagnostic_payload(capture.read_packet(), args)
            frames += 1
            if args.max_frames > 0 and frames >= args.max_frames:
                break
            if args.capture_seconds > 0 and time.monotonic() - started >= args.capture_seconds:
                break
    finally:
        capture.stop()
    latest["frames"] = frames
    return latest


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        print(json.dumps(run(args), sort_keys=True))
    except OrbbecSdkNotAvailable as error:
        print(error)
        return 2
    except (OrbbecCameraError, OrbbecFrameError, ValueError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
