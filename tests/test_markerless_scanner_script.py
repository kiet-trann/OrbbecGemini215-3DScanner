import importlib.util
from pathlib import Path
import sys

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.tracking.keyframes import Keyframe
from scanner_app.tracking.models import TrackingMetrics, TrackingResult, TrackingState


def load_markerless_scanner_module():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = project_root / "scripts" / "14_markerless_scanner.py"
    spec = importlib.util.spec_from_file_location("markerless_scanner", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parser_uses_validated_25cm_live_scan_defaults() -> None:
    module = load_markerless_scanner_module()

    args = module.build_argument_parser().parse_args(["--headless", "--no-export"])

    assert args.backend == "opencv"
    assert args.tracking_width == 240
    assert args.tracking_height == 150
    assert args.min_depth_m == 0.20
    assert args.max_depth_m == 0.30
    assert args.voxel_length_m == 0.0015
    assert args.sdf_trunc_m == 0.006
    assert args.live_fusion_width == 320
    assert args.live_fusion_height == 200
    assert args.live_integrate_interval_s == 0.5
    assert args.headless


def test_live_scan_integrates_only_new_accepted_keyframes_and_stops_camera() -> None:
    module = load_markerless_scanner_module()
    stopped = []
    packets = [
        SynchronizedFramePacket(
            color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
            depth_raw=np.full((2, 2), 250, dtype=np.uint16),
            depth_scale_mm=1.0,
            depth_timestamp_us=100_000 + index * 33_000,
            color_timestamp_us=100_000 + index * 33_000,
            imu_samples=(),
            sequence=index,
        )
        for index in range(3)
    ]

    class FakeCapture:
        def __init__(self, **_kwargs) -> None:
            self.index = 0

        def start(self) -> None:
            return None

        def intrinsics(self) -> CameraIntrinsics:
            return CameraIntrinsics(500, 500, 1, 1, 2, 2)

        def read_packet(self) -> SynchronizedFramePacket:
            packet = packets[self.index]
            self.index += 1
            return packet

        def stop(self) -> None:
            stopped.append(True)

    class FakeTracker:
        def __init__(self, _intrinsics, **_kwargs) -> None:
            self.keyframes = type("Keyframes", (), {"keyframes": []})()

        def process(self, packet: SynchronizedFramePacket) -> TrackingResult:
            metrics = TrackingMetrics(1.0, 0.0, 0.0, 0.0, 1.0)
            is_keyframe = packet.sequence in (0, 2)
            if is_keyframe:
                self.keyframes.keyframes.append(Keyframe(packet, np.eye(4), metrics))
            return TrackingResult(
                state=TrackingState.TRACKING,
                camera_to_world=np.eye(4),
                metrics=metrics,
                accepted=True,
                keyframe=is_keyframe,
            )

    class FakeFusion:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.integrated = []

        def integrate(self, keyframe: Keyframe) -> int:
            self.integrated.append(keyframe)
            return 4

        def extract_preview(self):
            return {"integrated": len(self.integrated)}

    created_fusions = []

    def fusion_factory(**kwargs):
        fusion = FakeFusion(**kwargs)
        created_fusions.append(fusion)
        return fusion

    args = module.build_argument_parser().parse_args(
        [
            "--headless",
            "--no-export",
            "--max-frames",
            "3",
            "--warmup-frames",
            "0",
            "--live-integrate-interval-s",
            "0",
        ]
    )

    summary = module.run_live_scan(
        args,
        capture_factory=FakeCapture,
        tracker_factory=FakeTracker,
        fusion_factory=fusion_factory,
        preview_factory=module.NullLivePreview,
    )

    assert stopped == [True]
    assert summary.frames == 3
    assert summary.integrated_keyframes == 2
    assert len(created_fusions[0].integrated) == 2
    assert created_fusions[0].kwargs["voxel_length_m"] == 0.0015
    assert created_fusions[0].kwargs["integration_width"] == 320
    assert created_fusions[0].kwargs["integration_height"] == 200
    np.testing.assert_allclose(created_fusions[0].kwargs["roi_min"], [-0.175, -0.175, 0.075])
    np.testing.assert_allclose(created_fusions[0].kwargs["roi_max"], [0.175, 0.175, 0.425])


def test_headless_live_scan_does_not_extract_preview_mesh() -> None:
    module = load_markerless_scanner_module()
    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.full((2, 2), 250, dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=100_000,
        color_timestamp_us=100_000,
        imu_samples=(),
        sequence=0,
    )

    class FakeCapture:
        def __init__(self, **_kwargs) -> None:
            return None

        def start(self) -> None:
            return None

        def intrinsics(self) -> CameraIntrinsics:
            return CameraIntrinsics(500, 500, 1, 1, 2, 2)

        def read_packet(self) -> SynchronizedFramePacket:
            return packet

        def stop(self) -> None:
            return None

    class FakeTracker:
        def __init__(self, _intrinsics, **_kwargs) -> None:
            metrics = TrackingMetrics(1.0, 0.0, 0.0, 0.0, 1.0)
            self.keyframes = type(
                "Keyframes",
                (),
                {"keyframes": [Keyframe(packet, np.eye(4), metrics)]},
            )()

        def process(self, _packet: SynchronizedFramePacket) -> TrackingResult:
            return TrackingResult(
                state=TrackingState.TRACKING,
                camera_to_world=np.eye(4),
                metrics=TrackingMetrics(1.0, 0.0, 0.0, 0.0, 1.0),
                accepted=True,
                keyframe=True,
            )

    class FakeFusion:
        def __init__(self, **_kwargs) -> None:
            return None

        def integrate(self, _keyframe: Keyframe) -> int:
            return 4

        def extract_preview(self):
            raise AssertionError("headless scans should not extract preview geometry")

    args = module.build_argument_parser().parse_args(
        [
            "--headless",
            "--no-export",
            "--max-frames",
            "1",
            "--warmup-frames",
            "0",
            "--preview-interval-s",
            "0",
        ]
    )

    summary = module.run_live_scan(
        args,
        capture_factory=FakeCapture,
        tracker_factory=FakeTracker,
        fusion_factory=FakeFusion,
        preview_factory=module.NullLivePreview,
    )

    assert summary.integrated_keyframes == 1
