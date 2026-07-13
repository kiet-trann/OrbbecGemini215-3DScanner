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


def test_live_run_stops_camera_when_frame_limit_is_reached(capsys) -> None:
    module = load_markerless_tracking_module()
    stopped = []

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
        module.build_argument_parser().parse_args(["--max-frames", "1"]),
        capture_factory=FakeCapture,
        tracker_factory=FakeTracker,
    )

    assert stopped == [True]
    assert '"sequence":7' in capsys.readouterr().out
