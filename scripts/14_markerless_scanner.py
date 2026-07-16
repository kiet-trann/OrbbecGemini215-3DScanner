"""Live markerless handheld scanner with RGB preview and TSDF model preview."""

import _bootstrap  # noqa: F401

import argparse
from collections import Counter
from dataclasses import dataclass, field
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
from scanner_app.fusion.preview_worker import LivePreviewWorker
from scanner_app.processing.depth_pipeline import DepthProcessor
from scanner_app.processing.mesh_orientation import orient_camera_y_down_mesh_y_up
from scanner_app.processing.mesh_reconstruction import cleanup_mesh, describe_mesh
from scanner_app.session.coverage import ViewCoverage
from scanner_app.session.models import ScannerSnapshot, ScanSessionState
from scanner_app.tracking.markerless import MarkerlessTracker
from scanner_app.tracking.quality import QualityGate
from scanner_app.tracking.rgbd_odometry import (
    BackgroundAssistedRgbdOdometryBackend,
    OpenCvRgbdOdometryBackend,
    RgbdOdometryAdapter,
)
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
    parser.add_argument("--tracking-min-depth-m", type=float, default=0.20)
    parser.add_argument("--tracking-max-depth-m", type=float, default=0.50)
    parser.add_argument("--min-depth-valid-ratio", type=float, default=0.01)
    parser.add_argument("--max-rmse-m", type=float, default=0.006)
    parser.add_argument("--max-timestamp-gap-ms", type=int, default=500)
    parser.add_argument("--lost-after-rejections", type=int, default=10)
    parser.add_argument(
        "--backend", choices=("opencv", "open3d", "background-assisted"), default="opencv"
    )
    parser.add_argument("--opencv-max-features", type=int, default=1200)
    parser.add_argument("--opencv-min-matches", type=int, default=6)
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
    parser.add_argument("--print-every", type=int, default=0)
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
    backend = (
        BackgroundAssistedRgbdOdometryBackend(
            max_features=args.opencv_max_features,
            min_matches=max(24, args.opencv_min_matches),
        )
        if args.backend == "background-assisted"
        else OpenCvRgbdOdometryBackend(
            max_features=args.opencv_max_features,
            min_matches=args.opencv_min_matches,
        )
        if args.backend == "opencv"
        else None
    )
    return tracker_factory(
        intrinsics,
        depth_processor=DepthProcessor(args.tracking_min_depth_m, args.tracking_max_depth_m),
        quality_gate=QualityGate(
            min_depth_valid_ratio=(
                0.0 if args.backend == "background-assisted" else args.min_depth_valid_ratio
            ),
            max_rmse_m=args.max_rmse_m,
            max_timestamp_gap_us=args.max_timestamp_gap_ms * 1000,
            lost_after_rejections=args.lost_after_rejections,
        ),
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
    rejection_reasons: Counter[str] = field(default_factory=Counter)
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

    def record(self, result) -> None:
        self.frames += 1
        self.accepted += int(result.accepted)
        self.rejected += int(not result.accepted)
        self.keyframes += int(result.keyframe)
        self.lost += int(result.state.value == "lost")
        if not result.accepted:
            self.rejection_reasons[result.reason or "unspecified"] += 1


def format_summary(summary: LiveScanSummary) -> str:
    reason_text = ",".join(
        f"{reason}:{count}" for reason, count in summary.rejection_reasons.most_common()
    ) or "none"
    return (
        "markerless_scan "
        f"frames={summary.frames} accepted={summary.accepted} "
        f"keyframes={summary.keyframes} integrated={summary.integrated_keyframes} "
        f"lost={summary.lost} tracking_fps={summary.tracking_fps:.2f} "
        f"rejected_reasons={reason_text} output={summary.output_path}"
    )


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
    preview_worker_factory=LivePreviewWorker,
) -> LiveScanSummary:
    capture = capture_factory(
        capture_config=CaptureConfig(
            depth_min_m=args.min_depth_m,
            depth_max_m=args.tracking_max_depth_m,
        ),
        alignment_target="color" if args.backend == "background-assisted" else "depth",
    )
    preview = preview_factory(headless=args.headless)
    summary = LiveScanSummary()
    preview_worker = None
    coverage = ViewCoverage(object_center=_object_center_from_depth(args))
    roi_min, roi_max = build_object_roi(args)

    try:
        capture.start()
        for _ in range(max(0, args.warmup_frames)):
            capture.read_packet()

        intrinsics = capture.intrinsics()
        tracker = build_tracker(intrinsics, args, tracker_factory=tracker_factory)
        preview_fusion_kwargs = dict(
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
        if getattr(preview, "wants_mesh_preview", True):
            preview_worker = preview_worker_factory(
                fusion_factory,
                preview_fusion_kwargs,
                integration_interval_s=args.live_integrate_interval_s,
            )
            preview_worker.start()
        final_keyframes = []
        summary.started_at = time.monotonic()

        while True:
            now = time.monotonic()
            packet = capture.read_packet()
            result = tracker.process(packet)
            summary.record(result)
            if result.accepted:
                coverage.add_camera_position(result.camera_to_world[:3, 3])

            if result.accepted and result.keyframe and hasattr(tracker, "keyframes"):
                keyframes = tracker.keyframes.keyframes
                final_keyframes = keyframes
                if preview_worker is not None:
                    preview_worker.submit(keyframes[-1])

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
            if args.print_every > 0 and summary.frames % args.print_every == 0:
                print(format_status_line(snapshot), flush=True)

            preview_mesh = (
                preview_worker.drain_latest_mesh() if preview_worker is not None else None
            )
            if preview_mesh is not None:
                preview.update_mesh(orient_camera_y_down_mesh_y_up(preview_mesh))
                summary.preview_updates += 1

            if preview.poll():
                break
            if args.max_frames > 0 and summary.frames >= args.max_frames:
                break
            if args.capture_seconds > 0 and now - summary.started_at >= args.capture_seconds:
                break

        summary.stopped_at = time.monotonic()
        if not args.no_export and final_keyframes:
            final_fusion = fusion_factory(**(preview_fusion_kwargs | {
                "integration_width": None,
                "integration_height": None,
            }))
            summary.output_path = export_mesh(final_fusion.rebuild(final_keyframes), args.output)
    finally:
        if summary.stopped_at == 0.0:
            summary.stopped_at = time.monotonic()
        if preview_worker is not None:
            preview_worker.close()
            summary.integrated_keyframes = getattr(
                preview_worker,
                "integrated_keyframes",
                summary.integrated_keyframes,
            )
        preview.close()
        capture.stop()
    return summary


def export_mesh(mesh: Any, output_path: Path | None = None) -> Path | None:
    if not hasattr(mesh, "triangles"):
        return None
    if len(mesh.triangles) == 0:
        return None

    import open3d as o3d

    orient_camera_y_down_mesh_y_up(mesh)
    cleanup_mesh(mesh)
    validate_export_mesh(mesh)
    output = (output_path or build_output_path()).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(output), mesh):
        raise OrbbecFrameError(f"Failed to write markerless scan mesh: {output}")
    print(f"Saved markerless mesh {describe_mesh(mesh)} to: {output}")
    return output


def validate_export_mesh(
    mesh: Any,
    *,
    max_component_count: int = 3,
    max_extent_m: float = 0.36,
    min_component_area_ratio: float = 0.03,
) -> None:
    _labels, counts, areas = mesh.cluster_connected_triangles()
    area_values = np.asarray(areas, dtype=np.float64)
    largest_area = float(np.max(area_values)) if len(area_values) else 0.0
    component_count = int(
        np.count_nonzero(area_values >= largest_area * float(min_component_area_ratio))
    )
    if component_count > max_component_count:
        raise ValueError(
            f"Refusing to export mesh: too many disconnected components ({component_count})."
        )

    extent = np.asarray(mesh.get_axis_aligned_bounding_box().get_extent(), dtype=np.float64)
    if np.any(extent > max_extent_m):
        raise ValueError(
            "Refusing to export mesh: bounding box exceeds object envelope "
            f"({tuple(float(value) for value in extent)} m)."
        )


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

    print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
