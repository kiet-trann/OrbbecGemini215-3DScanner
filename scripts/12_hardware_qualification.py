"""Gemini 215 hardware qualification gate for markerless tracking."""

import _bootstrap  # noqa: F401

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
import time

import numpy as np

from scanner_app.camera.models import CaptureConfig, ImuSample
from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.processing.depth_pipeline import DepthProcessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "sessions"
TARGET_DISTANCES_M = (0.20, 0.30, 0.40)
CENTRAL_MASK_FRACTION = 0.50

RGBD_FPS_MIN = 24.0
IMU_HZ_MIN = 190.0
IMU_HZ_MAX = 210.0
OBJECT_VALID_RATIO_MIN = 0.70
MEDIAN_NOISE_MM_MAX = 1.0
P90_NOISE_MM_MAX = 2.0


@dataclass(frozen=True)
class QualificationReport:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, float]


@dataclass(frozen=True)
class CaptureSummary:
    distance_m: float
    frames: int
    valid_ratio: float
    median_noise_mm: float | None
    p90_noise_mm: float | None


def evaluate_metrics(
    rgbd_fps: float,
    imu_hz: float,
    object_valid_ratio: float,
    median_noise_mm: float,
    p90_noise_mm: float,
) -> QualificationReport:
    metrics = {
        "rgbd_fps": float(rgbd_fps),
        "imu_hz": float(imu_hz),
        "object_valid_ratio": float(object_valid_ratio),
        "median_noise_mm": float(median_noise_mm),
        "p90_noise_mm": float(p90_noise_mm),
    }
    limits = {
        "rgbd_fps": metrics["rgbd_fps"] >= RGBD_FPS_MIN,
        "imu_hz": IMU_HZ_MIN <= metrics["imu_hz"] <= IMU_HZ_MAX,
        "object_valid_ratio": metrics["object_valid_ratio"] >= OBJECT_VALID_RATIO_MIN,
        "median_noise_mm": metrics["median_noise_mm"] <= MEDIAN_NOISE_MM_MAX,
        "p90_noise_mm": metrics["p90_noise_mm"] <= P90_NOISE_MM_MAX,
    }
    failures = tuple(name for name, passed in limits.items() if not passed)
    return QualificationReport(passed=not failures, failures=failures, metrics=metrics)


def build_output_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"qualification_{timestamp}.json"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Gemini 215 hardware qualification gate.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Seconds to capture at each target distance. Default: 3.0.",
    )
    parser.add_argument(
        "--warmup",
        type=float,
        default=10.0,
        help="Seconds of live synchronized RGB-D + IMU warm-up. Default: 10.0.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Qualification JSON output path. Default: data/sessions/qualification_<timestamp>.json.",
    )
    parser.add_argument(
        "--distance",
        dest="distances",
        action="append",
        type=float,
        default=None,
        help="Target distance in meters. Repeat to override the default 0.20/0.30/0.40 m set.",
    )
    parser.add_argument(
        "--noninteractive",
        action="store_true",
        help="Do not wait for Enter before each distance capture.",
    )
    return parser


def warm_up(camera: OrbbecCapture, seconds: float) -> int:
    print(f"Warm-up: keep the camera pointed at the matte target for {seconds:.1f}s.")
    deadline = time.perf_counter() + max(0.0, seconds)
    frames = 0
    while time.perf_counter() < deadline:
        camera.read_packet()
        frames += 1
    return frames


def collect_static_samples(
    camera: OrbbecCapture,
    processor: DepthProcessor,
    distances_m: tuple[float, ...],
    duration_s: float,
    interactive: bool,
) -> tuple[list[CaptureSummary], dict[str, float]]:
    frame_count = 0
    capture_seconds = 0.0
    valid_pixels = 0
    total_roi_pixels = 0
    noise_mm: list[np.ndarray] = []
    imu_samples: list[ImuSample] = []
    summaries: list[CaptureSummary] = []

    for distance_m in distances_m:
        print(
            f"Place a flat matte target centered at {distance_m:.2f} m, square to the camera."
        )
        if interactive:
            input("Press Enter when the target is static...")

        distance_frames = 0
        distance_valid_pixels = 0
        distance_total_pixels = 0
        distance_depths: list[np.ndarray] = []
        started = time.perf_counter()
        deadline = started + max(0.0, duration_s)
        while time.perf_counter() < deadline:
            packet = camera.read_packet()
            processed = processor.process(packet)
            roi_mask = central_mask(processed.valid_mask.shape, CENTRAL_MASK_FRACTION)
            valid_roi_mask = processed.valid_mask & roi_mask
            valid_depth = processed.depth_m[valid_roi_mask]

            roi_pixels = int(np.count_nonzero(roi_mask))
            valid_count = int(valid_depth.size)
            total_roi_pixels += roi_pixels
            valid_pixels += valid_count
            distance_total_pixels += roi_pixels
            distance_valid_pixels += valid_count
            frame_count += 1
            distance_frames += 1
            imu_samples.extend(packet.imu_samples)

            temporal_depth = np.where(valid_roi_mask, processed.depth_m, np.nan).astype(
                np.float32,
                copy=False,
            )
            distance_depths.append(temporal_depth)

        capture_seconds += time.perf_counter() - started
        distance_noise = temporal_noise_mm(distance_depths)
        if distance_noise.size:
            noise_mm.append(distance_noise)
        summaries.append(
            CaptureSummary(
                distance_m=distance_m,
                frames=distance_frames,
                valid_ratio=safe_ratio(distance_valid_pixels, distance_total_pixels),
                median_noise_mm=percentile_or_none(distance_noise, 50.0),
                p90_noise_mm=percentile_or_none(distance_noise, 90.0),
            )
        )

    combined_noise = concatenate_noise(noise_mm)
    measurements = {
        "rgbd_fps": safe_ratio(frame_count, capture_seconds),
        "imu_hz": estimate_imu_hz(imu_samples),
        "object_valid_ratio": safe_ratio(valid_pixels, total_roi_pixels),
        "median_noise_mm": percentile_or_inf(combined_noise, 50.0),
        "p90_noise_mm": percentile_or_inf(combined_noise, 90.0),
    }
    return summaries, measurements


def central_mask(shape: tuple[int, int], fraction: float) -> np.ndarray:
    height, width = shape
    roi_height = max(1, int(round(height * fraction)))
    roi_width = max(1, int(round(width * fraction)))
    y0 = (height - roi_height) // 2
    x0 = (width - roi_width) // 2
    mask = np.zeros(shape, dtype=bool)
    mask[y0 : y0 + roi_height, x0 : x0 + roi_width] = True
    return mask


def concatenate_noise(values: list[np.ndarray]) -> np.ndarray:
    if not values:
        return np.array([], dtype=np.float32)
    return np.concatenate(values).astype(np.float32, copy=False)


def temporal_noise_mm(depth_frames_m: list[np.ndarray]) -> np.ndarray:
    if len(depth_frames_m) < 2:
        return np.array([], dtype=np.float32)

    stack = np.stack(depth_frames_m).astype(np.float32, copy=False)
    samples_by_pixel = stack.reshape(stack.shape[0], -1)
    finite = np.isfinite(samples_by_pixel)
    enough_samples = np.count_nonzero(finite, axis=0) >= 2
    if not np.any(enough_samples):
        return np.array([], dtype=np.float32)

    selected = samples_by_pixel[:, enough_samples]
    medians_m = np.nanmedian(selected, axis=0)
    deviations_mm = np.abs(selected - medians_m) * 1000.0
    return deviations_mm[np.isfinite(deviations_mm)].astype(np.float32, copy=False)


def percentile_or_inf(values: np.ndarray, percentile: float) -> float:
    if values.size == 0:
        return float("inf")
    return float(np.percentile(values, percentile))


def percentile_or_none(values: np.ndarray, percentile: float) -> float | None:
    if values.size == 0:
        return None
    return float(np.percentile(values, percentile))


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def estimate_imu_hz(samples: list[ImuSample]) -> float:
    rates: list[float] = []
    for sensor_name in ("gyro", "accel"):
        timestamps = sorted(
            sample.timestamp_us for sample in samples if sample.sensor == sensor_name
        )
        if len(timestamps) < 2:
            rates.append(0.0)
            continue
        elapsed_s = (timestamps[-1] - timestamps[0]) / 1_000_000.0
        rates.append(safe_ratio(len(timestamps) - 1, elapsed_s))
    return min(rates) if rates else 0.0


def write_report(
    output_path: Path,
    report: QualificationReport,
    capture_config: CaptureConfig,
    summaries: list[CaptureSummary],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "passed": report.passed,
        "failures": list(report.failures),
        "metrics": report.metrics,
        "thresholds": {
            "rgbd_fps_min": RGBD_FPS_MIN,
            "imu_hz_min": IMU_HZ_MIN,
            "imu_hz_max": IMU_HZ_MAX,
            "object_valid_ratio_min": OBJECT_VALID_RATIO_MIN,
            "median_noise_mm_max": MEDIAN_NOISE_MM_MAX,
            "p90_noise_mm_max": P90_NOISE_MM_MAX,
        },
        "capture_config": asdict(capture_config),
        "static_captures": [asdict(summary) for summary in summaries],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_report(report: QualificationReport, output_path: Path) -> None:
    print("Hardware qualification metrics:")
    for name, value in report.metrics.items():
        print(f"  {name}: {value:.3f}")
    print(f"Report: {output_path}")
    if report.passed:
        print("PASS: Gemini 215 hardware is qualified for markerless tracking.")
    else:
        print("FAIL: Gemini 215 hardware is not qualified for markerless tracking.")
        print(f"Failures: {', '.join(report.failures)}")


def run(args: argparse.Namespace) -> int:
    if args.duration <= 0:
        raise ValueError("--duration must be greater than 0.")
    if args.warmup < 0:
        raise ValueError("--warmup cannot be negative.")

    capture_config = CaptureConfig()
    processor = DepthProcessor(
        min_depth_m=capture_config.depth_min_m,
        max_depth_m=capture_config.depth_max_m,
    )
    output_path = args.output or build_output_path()
    distances_m = tuple(args.distances or TARGET_DISTANCES_M)
    interactive = not args.noninteractive and sys.stdin.isatty()

    print("Gemini 215 hardware qualification gate")
    print("Use a flat, non-glossy matte target that fills the central half of the depth frame.")
    print("Keep the camera and target static during each capture.")

    camera = OrbbecCapture(capture_config=capture_config, align_to_depth=True)
    try:
        camera.start()
        warm_up(camera, args.warmup)
        summaries, measurements = collect_static_samples(
            camera=camera,
            processor=processor,
            distances_m=distances_m,
            duration_s=args.duration,
            interactive=interactive,
        )
        report = evaluate_metrics(**measurements)
        write_report(output_path, report, capture_config, summaries)
        print_report(report, output_path)
        return 0 if report.passed else 1
    finally:
        camera.stop()


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ValueError as error:
        print(error)
        return 1
    except OrbbecSdkNotAvailable as error:
        print(error)
        return 1
    except (OrbbecCameraError, OrbbecFrameError) as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
