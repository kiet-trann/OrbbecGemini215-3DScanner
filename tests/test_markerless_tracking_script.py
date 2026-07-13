import importlib.util
from pathlib import Path
import sys

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.tracking.models import TrackingMetrics, TrackingResult, TrackingState


def load_markerless_tracking_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "13_markerless_tracking.py"
    spec = importlib.util.spec_from_file_location("markerless_tracking", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parser_accepts_replay_intrinsics_and_close_up_depth_range() -> None:
    module = load_markerless_tracking_module()

    args = module.build_argument_parser().parse_args(
        [
            "--replay",
            "data/sessions/demo",
            "--max-frames",
            "5",
            "--min-depth-m",
            "0.20",
            "--max-depth-m",
            "0.30",
            "--intrinsics-fx",
            "500",
            "--intrinsics-fy",
            "501",
            "--intrinsics-cx",
            "320",
            "--intrinsics-cy",
            "200",
            "--intrinsics-width",
            "640",
            "--intrinsics-height",
            "400",
            "--record-accepted",
        ]
    )

    assert args.replay == Path("data/sessions/demo")
    assert args.max_frames == 5
    assert args.min_depth_m == 0.20
    assert args.max_depth_m == 0.30
    assert module.intrinsics_from_args(args) == CameraIntrinsics(500, 501, 320, 200, 640, 400)
    assert args.record_accepted


def test_result_to_json_emits_tracking_metrics_keyframe_and_pose() -> None:
    module = load_markerless_tracking_module()
    pose = np.eye(4)
    pose[0, 3] = -0.02
    result = TrackingResult(
        state=TrackingState.TRACKING,
        camera_to_world=pose,
        metrics=TrackingMetrics(
            fitness=0.8,
            rmse_m=0.001,
            translation_m=0.02,
            rotation_deg=3.0,
            depth_valid_ratio=0.75,
        ),
        accepted=True,
        keyframe=True,
        reason=None,
    )

    payload = module.result_to_json(sequence=7, timestamp_us=123_000, result=result)

    assert payload["sequence"] == 7
    assert payload["timestamp_us"] == 123_000
    assert payload["state"] == "tracking"
    assert payload["accepted"] is True
    assert payload["keyframe"] is True
    assert payload["reason"] is None
    assert payload["fitness"] == 0.8
    assert payload["rmse_m"] == 0.001
    assert payload["translation_m"] == 0.02
    assert payload["rotation_deg"] == 3.0
    assert payload["depth_valid_ratio"] == 0.75
    assert payload["pose"][0][3] == -0.02


def test_tracking_summary_reports_accepted_update_rate() -> None:
    module = load_markerless_tracking_module()
    summary = module.TrackingSummary()
    pose = np.eye(4)
    result = TrackingResult(
        state=TrackingState.TRACKING,
        camera_to_world=pose,
        metrics=TrackingMetrics(1.0, 0.0, 0.0, 0.0, 0.7),
        accepted=True,
        keyframe=False,
    )

    summary.update(100_000, result)
    summary.update(300_000, result)

    payload = summary.to_json()

    assert payload["frames"] == 2
    assert payload["accepted"] == 2
    assert payload["accepted_updates_per_s"] == 5.0


def test_build_tracker_uses_cli_depth_range() -> None:
    module = load_markerless_tracking_module()
    args = module.build_argument_parser().parse_args(
        [
            "--min-depth-m",
            "0.15",
            "--max-depth-m",
            "0.50",
            "--tracking-width",
            "320",
            "--tracking-height",
            "200",
            "--disable-icp",
            "--print-every",
            "0",
            "--backend",
            "opencv",
        ]
    )

    tracker = module.build_tracker(CameraIntrinsics(500, 500, 1, 1, 2, 2), args)

    assert tracker.depth_processor.min_depth_m == 0.15
    assert tracker.depth_processor.max_depth_m == 0.50
    assert tracker.quality_gate.min_depth_valid_ratio == 0.01
    assert tracker.odometry.tracking_width == 320
    assert tracker.odometry.tracking_height == 200
    assert not tracker.odometry.enable_icp
    assert tracker.odometry._backend.__class__.__name__ == "OpenCvRgbdOdometryBackend"
    assert args.print_every == 0


def test_live_run_stops_camera_when_frame_limit_is_reached(capsys) -> None:
    module = load_markerless_tracking_module()
    stopped = []
    reads = []

    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.full((2, 2), 250, dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=123_000,
        color_timestamp_us=123_000,
        imu_samples=(),
        sequence=7,
    )

    class FakeCapture:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            return None

        def intrinsics(self) -> CameraIntrinsics:
            return CameraIntrinsics(500, 500, 1, 1, 2, 2)

        def read_packet(self) -> SynchronizedFramePacket:
            reads.append(True)
            return packet

        def stop(self) -> None:
            stopped.append(True)

    class FakeTracker:
        def __init__(self, _intrinsics, **_kwargs) -> None:
            return None

        def process(self, _packet) -> TrackingResult:
            return TrackingResult(
                state=TrackingState.TRACKING,
                camera_to_world=np.eye(4),
                metrics=TrackingMetrics(
                    fitness=1.0,
                    rmse_m=0.0,
                    translation_m=0.0,
                    rotation_deg=0.0,
                    depth_valid_ratio=1.0,
                ),
                accepted=True,
                keyframe=True,
            )

    module.run_live(
        module.build_argument_parser().parse_args(["--max-frames", "1", "--warmup-frames", "2"]),
        capture_factory=FakeCapture,
        tracker_factory=FakeTracker,
    )

    assert stopped == [True]
    assert len(reads) == 3
    assert '"sequence":7' in capsys.readouterr().out
