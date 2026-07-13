"""Live markerless handheld scanner with RGB preview and TSDF model preview."""

import _bootstrap  # noqa: F401

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, CaptureConfig
from scanner_app.camera.orbbec_capture import (
    OrbbecCameraError,
    OrbbecCapture,
    OrbbecFrameError,
    OrbbecSdkNotAvailable,
)
from scanner_app.fusion.live import LiveFusionEngine
from scanner_app.processing.depth_pipeline import DepthProcessor
from scanner_app.processing.mesh_reconstruction import cleanup_mesh, describe_mesh
from scanner_app.session.coverage import ViewCoverage
from scanner_app.session.models import ScannerSnapshot, ScanSessionState
from scanner_app.tracking.markerless import MarkerlessTracker
from scanner_app.tracking.quality import QualityGate
from scanner_app.tracking.rgbd_odometry import OpenCvRgbdOdometryBackend, RgbdOdometryAdapter
from scanner_app.visualization.scanner_window import format_status_line


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ply"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a live markerless 3D scan with RGB and TSDF model previews."
    )
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N tracking frames.")
    parser.add_argument("--capture-seconds", type=float, default=0.0)
    parser.add_argument("--warmup-frames", type=int, default=30)
    parser.add_argument("--min-depth-m", type=float, default=0.20)
    parser.add_argument("--max-depth-m", type=float, default=0.30)
    parser.add_argument("--min-depth-valid-ratio", type=float, default=0.01)
    parser.add_argument("--backend", choices=("opencv", "open3d"), default="opencv")
    parser.add_argument("--tracking-width", type=int, default=240)
    parser.add_argument("--tracking-height", type=int, default=150)
    parser.add_argument("--disable-icp", action="store_true")
    parser.add_argument("--voxel-length-m", type=float, default=0.0015)
    parser.add_argument("--sdf-trunc-m", type=float, default=0.006)
    parser.add_argument("--live-fusion-width", type=int, default=320)
    parser.add_argument("--live-fusion-height", type=int, default=200)
    parser.add_argument(
        "--live-integrate-interval-s",
        type=float,
        default=0.5,
        help="Minimum spacing between TSDF integrations for the live preview.",
    )
    parser.add_argument("--preview-interval-s", type=float, default=0.5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def build_output_path(now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"markerless_scan_{timestamp}.ply"


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


@dataclass
class LiveScanSummary:
    frames: int = 0
    accepted: int = 0
    rejected: int = 0
    keyframes: int = 0
    integrated_keyframes: int = 0
    lost: int = 0
    preview_updates: int = 0
    started_at: float = 0.0
    stopped_at: float = 0.0
    output_path: Path | None = None

    @property
    def elapsed_s(self) -> float:
        if self.started_at == 0.0 or self.stopped_at == 0.0:
            return 0.0
        return max(0.0, self.stopped_at - self.started_at)

    @property
    def tracking_fps(self) -> float:
        return self.frames / self.elapsed_s if self.elapsed_s > 0.0 else 0.0


class NullLivePreview:
    wants_mesh_preview = False

    def __init__(self, **_kwargs) -> None:
        self.closed = False

    def update_color(self, _color_bgr, _status_line: str) -> None:
        return None

    def update_mesh(self, _mesh) -> None:
        return None

    def poll(self) -> bool:
        return False

    def close(self) -> None:
        self.closed = True


class LivePreview:
    wants_mesh_preview = True

    def __init__(self, *, headless: bool = False) -> None:
        if headless:
            self._delegate = NullLivePreview()
            self.wants_mesh_preview = False
            return

        import cv2
        import open3d as o3d

        self.cv2 = cv2
        self.o3d = o3d
        self._delegate = None
        self._mesh_added = False
        cv2.namedWindow("Gemini 215 RGB", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Gemini 215 RGB", 720, 540)
        cv2.moveWindow("Gemini 215 RGB", 20, 80)
        self.visualizer = o3d.visualization.Visualizer()
        self.visualizer.create_window(
            "Gemini 215 Markerless Model",
            width=720,
            height=540,
            left=760,
            top=80,
        )

    def update_color(self, color_bgr, status_line: str) -> None:
        if self._delegate is not None:
            self._delegate.update_color(color_bgr, status_line)
            return
        frame = color_bgr.copy()
        self.cv2.putText(
            frame,
            status_line,
            (16, 32),
            self.cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
            self.cv2.LINE_AA,
        )
        self.cv2.imshow("Gemini 215 RGB", frame)

    def update_mesh(self, mesh) -> None:
        if self._delegate is not None:
            self._delegate.update_mesh(mesh)
            return
        self.visualizer.clear_geometries()
        self.visualizer.add_geometry(mesh)
        self._mesh_added = True

    def poll(self) -> bool:
        if self._delegate is not None:
            return self._delegate.poll()
        key = self.cv2.waitKey(1)
        self.visualizer.poll_events()
        self.visualizer.update_renderer()
        return key in (ord("q"), ord("Q"), 27)

    def close(self) -> None:
        if self._delegate is not None:
            self._delegate.close()
            return
        self.visualizer.destroy_window()
        self.cv2.destroyWindow("Gemini 215 RGB")


def run_live_scan(
    args: argparse.Namespace,
    *,
    capture_factory=OrbbecCapture,
    tracker_factory=MarkerlessTracker,
    fusion_factory=LiveFusionEngine,
    preview_factory=LivePreview,
) -> LiveScanSummary:
    capture = capture_factory(
        capture_config=CaptureConfig(
            depth_min_m=args.min_depth_m,
            depth_max_m=args.max_depth_m,
        ),
        align_to_depth=True,
    )
    preview = preview_factory(headless=args.headless)
    summary = LiveScanSummary()
    last_preview_at = 0.0
    last_live_integrate_at = float("-inf")
    integrated_keyframe_count = 0
    coverage = ViewCoverage(object_center=_object_center_from_depth(args))
    roi_min, roi_max = build_object_roi(args)

    try:
        capture.start()
        for _ in range(max(0, args.warmup_frames)):
            capture.read_packet()

        intrinsics = capture.intrinsics()
        tracker = build_tracker(intrinsics, args, tracker_factory=tracker_factory)
        fusion = fusion_factory(
            intrinsics=intrinsics,
            voxel_length_m=args.voxel_length_m,
            sdf_trunc_m=args.sdf_trunc_m,
            min_depth_m=args.min_depth_m,
            max_depth_m=args.max_depth_m,
            roi_min=roi_min,
            roi_max=roi_max,
            integration_width=args.live_fusion_width,
            integration_height=args.live_fusion_height,
        )
        final_keyframes = []
        summary.started_at = time.monotonic()

        while True:
            now = time.monotonic()
            packet = capture.read_packet()
            result = tracker.process(packet)
            summary.frames += 1
            summary.accepted += int(result.accepted)
            summary.rejected += int(not result.accepted)
            summary.keyframes += int(result.keyframe)
            summary.lost += int(result.state.value == "lost")
            if result.accepted:
                coverage.add_camera_position(result.camera_to_world[:3, 3])

            if result.accepted and result.keyframe and hasattr(tracker, "keyframes"):
                keyframes = tracker.keyframes.keyframes
                final_keyframes = keyframes
                if (
                    len(keyframes) > integrated_keyframe_count
                    and now - last_live_integrate_at >= max(0.0, args.live_integrate_interval_s)
                ):
                    fusion.integrate(keyframes[-1])
                    integrated_keyframe_count = len(keyframes)
                    last_live_integrate_at = now
                    summary.integrated_keyframes += 1

            tracking_fps = summary.frames / max(0.001, now - summary.started_at)
            snapshot = ScannerSnapshot(
                state=ScanSessionState.TRACKING,
                color_bgr=packet.color_bgr,
                tracking=result,
                preview_geometry=None,
                capture_fps=tracking_fps,
                tracking_fps=tracking_fps,
                preview_fps=summary.preview_updates / max(0.001, now - summary.started_at),
                depth_valid_ratio=result.metrics.depth_valid_ratio,
                coverage_ratio=coverage.ratio,
                trajectory_points=coverage.trajectory,
                message=None,
            )
            preview.update_color(packet.color_bgr, format_status_line(snapshot))

            if (
                getattr(preview, "wants_mesh_preview", True)
                and
                summary.integrated_keyframes > 0
                and now - last_preview_at >= max(0.05, args.preview_interval_s)
            ):
                preview.update_mesh(fusion.extract_preview())
                summary.preview_updates += 1
                last_preview_at = now

            if preview.poll():
                break
            if args.max_frames > 0 and summary.frames >= args.max_frames:
                break
            if args.capture_seconds > 0 and now - summary.started_at >= args.capture_seconds:
                break

        summary.stopped_at = time.monotonic()
        if not args.no_export and final_keyframes:
            final_fusion = fusion_factory(
                intrinsics=intrinsics,
                voxel_length_m=args.voxel_length_m,
                sdf_trunc_m=args.sdf_trunc_m,
                min_depth_m=args.min_depth_m,
                max_depth_m=args.max_depth_m,
                roi_min=roi_min,
                roi_max=roi_max,
                integration_width=None,
                integration_height=None,
            )
            summary.output_path = export_mesh(final_fusion.rebuild(final_keyframes), args.output)
    finally:
        if summary.stopped_at == 0.0:
            summary.stopped_at = time.monotonic()
        preview.close()
        capture.stop()
    return summary


def export_mesh(mesh: Any, output_path: Path | None = None) -> Path | None:
    if not hasattr(mesh, "triangles"):
        return None
    if len(mesh.triangles) == 0:
        return None

    import open3d as o3d

    cleanup_mesh(mesh)
    output = (output_path or build_output_path()).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(output), mesh):
        raise OrbbecFrameError(f"Failed to write markerless scan mesh: {output}")
    print(f"Saved markerless mesh {describe_mesh(mesh)} to: {output}")
    return output


def _object_center_from_depth(args: argparse.Namespace):
    return [0.0, 0.0, (args.min_depth_m + args.max_depth_m) * 0.5]


def build_object_roi(args: argparse.Namespace) -> tuple[np.ndarray, np.ndarray]:
    center_z = (args.min_depth_m + args.max_depth_m) * 0.5
    half_extent = 0.175
    return (
        np.array([-half_extent, -half_extent, center_z - half_extent], dtype=np.float64),
        np.array([half_extent, half_extent, center_z + half_extent], dtype=np.float64),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        summary = run_live_scan(args)
    except OrbbecSdkNotAvailable as error:
        print(error)
        return 2
    except (OrbbecCameraError, OrbbecFrameError, ValueError) as error:
        print(error)
        return 1

    print(
        "markerless_scan "
        f"frames={summary.frames} accepted={summary.accepted} "
        f"keyframes={summary.keyframes} integrated={summary.integrated_keyframes} "
        f"lost={summary.lost} tracking_fps={summary.tracking_fps:.2f} "
        f"output={summary.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
