import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import ProcessedDepth
from scanner_app.tracking.keyframes import KeyframeStore
from scanner_app.tracking.markerless import MarkerlessTracker
from scanner_app.tracking.models import TrackingMetrics, TrackingState
from scanner_app.tracking.quality import GateDecision, QualityGate
from scanner_app.tracking.rgbd_odometry import OdometryEstimate


def packet(
    sequence: int,
    timestamp_us: int,
    *,
    host_timestamp_us: int = 0,
) -> SynchronizedFramePacket:
    return SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.full((2, 2), 250, dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=timestamp_us,
        color_timestamp_us=timestamp_us,
        imu_samples=(),
        sequence=sequence,
        host_timestamp_us=host_timestamp_us,
    )


def processed(valid_ratio: float = 1.0) -> ProcessedDepth:
    depth_m = np.full((2, 2), 0.25, dtype=np.float32)
    valid_mask = np.ones((2, 2), dtype=bool)
    if valid_ratio == 0.0:
        depth_m[:] = 0.0
        valid_mask[:] = False
    return ProcessedDepth(
        depth_m=depth_m,
        valid_mask=valid_mask,
        valid_ratio=valid_ratio,
        median_depth_m=0.25 if valid_ratio > 0 else None,
    )


class FakeDepthProcessor:
    def __init__(self, depths: list[ProcessedDepth]) -> None:
        self.depths = depths

    def process(self, _packet: SynchronizedFramePacket) -> ProcessedDepth:
        return self.depths.pop(0)


class FakeImuEstimator:
    def __init__(self) -> None:
        self.calls = 0

    def predict_rotation(self, _samples) -> np.ndarray:
        self.calls += 1
        return np.eye(3)


class FakeOdometry:
    def __init__(self, transforms: list[np.ndarray]) -> None:
        self.transforms = transforms
        self.calls = []

    def estimate(
        self,
        previous_packet,
        previous_depth,
        current_packet,
        current_depth,
        imu_rotation,
    ) -> OdometryEstimate:
        self.calls.append((previous_packet, previous_depth, current_packet, current_depth, imu_rotation))
        return OdometryEstimate(
            relative_transform=self.transforms.pop(0),
            fitness=0.8,
            rmse_m=0.001,
            depth_valid_ratio=current_depth.valid_ratio,
        )


class FlexibleOdometry:
    def __init__(self, estimates: list[OdometryEstimate]) -> None:
        self.estimates = estimates
        self.calls = []

    def estimate(
        self,
        previous_packet,
        previous_depth,
        current_packet,
        current_depth,
        imu_rotation,
    ) -> OdometryEstimate:
        self.calls.append((previous_packet, previous_depth, current_packet, current_depth, imu_rotation))
        return self.estimates.pop(0)


class ScriptedGate:
    def __init__(self, decisions: list[GateDecision]) -> None:
        self.decisions = decisions
        self.metrics = []

    def evaluate(self, metrics, timestamp_us: int) -> GateDecision:
        self.metrics.append((metrics, timestamp_us))
        return self.decisions.pop(0)

    def metrics_rejection_reason(self, _metrics) -> None:
        return None


class RecordingQualityGate(QualityGate):
    def __init__(self) -> None:
        super().__init__(min_depth_valid_ratio=0.01)
        self.evaluate_timestamps = []

    def evaluate(self, metrics, timestamp_us: int):
        self.evaluate_timestamps.append(timestamp_us)
        return super().evaluate(metrics, timestamp_us)


class RecordingKeyframes:
    def __init__(self) -> None:
        self.calls = []

    def add(self, packet, pose, metrics, *, accepted: bool) -> bool:
        self.calls.append((packet, pose.copy(), metrics, accepted))
        return accepted


def intrinsics() -> CameraIntrinsics:
    return CameraIntrinsics(fx=500.0, fy=500.0, cx=1.0, cy=1.0, width=2, height=2)


def relative_translation(x_m: float) -> np.ndarray:
    transform = np.eye(4)
    transform[0, 3] = x_m
    return transform


def estimate(
    *,
    x_m: float,
    fitness: float = 0.8,
    rmse_m: float = 0.001,
    depth_valid_ratio: float = 1.0,
) -> OdometryEstimate:
    return OdometryEstimate(
        relative_transform=relative_translation(x_m),
        fitness=fitness,
        rmse_m=rmse_m,
        depth_valid_ratio=depth_valid_ratio,
    )


def test_first_valid_frame_initializes_identity_pose_and_keyframe() -> None:
    keyframes = RecordingKeyframes()
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed()]),
        odometry=FakeOdometry([]),
        keyframes=keyframes,
    )

    result = tracker.process(packet(1, 100_000))

    assert result.state is TrackingState.TRACKING
    assert result.accepted
    assert result.keyframe
    np.testing.assert_allclose(result.camera_to_world, np.eye(4))
    assert len(keyframes.calls) == 1
    assert keyframes.calls[0][3] is True


def test_tracker_uses_host_clock_when_camera_depth_timestamp_regresses() -> None:
    gate = ScriptedGate([GateDecision(True, TrackingState.TRACKING, None)])
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed(), processed()]),
        imu_estimator=FakeImuEstimator(),
        odometry=FakeOdometry([relative_translation(0.01)]),
        quality_gate=gate,
    )

    tracker.process(packet(1, 100_000, host_timestamp_us=1_000_000))
    result = tracker.process(packet(2, 1, host_timestamp_us=1_100_000))

    assert result.accepted
    assert gate.metrics[0][1] == 1_100_000


def test_first_invalid_depth_frame_stays_initializing_without_previous_state() -> None:
    keyframes = RecordingKeyframes()
    odometry = FakeOdometry([relative_translation(0.01)])
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed(0.0), processed()]),
        odometry=odometry,
        keyframes=keyframes,
    )

    first = tracker.process(packet(1, 100_000))
    second = tracker.process(packet(2, 200_000))

    assert first.state is TrackingState.INITIALIZING
    assert not first.accepted
    assert not first.keyframe
    assert second.accepted
    np.testing.assert_allclose(second.camera_to_world, np.eye(4))
    assert odometry.calls == []
    assert len(keyframes.calls) == 1


def test_first_low_coverage_depth_frame_stays_initializing_without_previous_state() -> None:
    keyframes = RecordingKeyframes()
    odometry = FakeOdometry([relative_translation(0.01)])
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed(0.1), processed()]),
        odometry=odometry,
        quality_gate=QualityGate(min_depth_valid_ratio=0.5),
        keyframes=keyframes,
    )

    first = tracker.process(packet(1, 100_000))
    second = tracker.process(packet(2, 200_000))

    assert first.state is TrackingState.INITIALIZING
    assert not first.accepted
    assert first.reason == "depth_valid_ratio_below_minimum"
    assert second.accepted
    assert odometry.calls == []
    assert len(keyframes.calls) == 1


def test_tracker_composes_only_accepted_motion_and_leaves_pose_unchanged_on_rejection() -> None:
    accepted_relative = relative_translation(0.02)
    rejected_relative = relative_translation(0.03)
    keyframes = RecordingKeyframes()
    gate = ScriptedGate(
        [
            GateDecision(True, TrackingState.TRACKING, None),
            GateDecision(False, TrackingState.DEGRADED, "fitness_below_minimum"),
        ]
    )
    odometry = FakeOdometry([accepted_relative, rejected_relative])
    imu = FakeImuEstimator()
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed(), processed(), processed()]),
        imu_estimator=imu,
        odometry=odometry,
        quality_gate=gate,
        keyframes=keyframes,
    )

    initial = tracker.process(packet(1, 100_000))
    accepted = tracker.process(packet(2, 200_000))
    rejected = tracker.process(packet(3, 300_000))

    expected_pose = np.eye(4)
    expected_pose[0, 3] = -0.02
    np.testing.assert_allclose(initial.camera_to_world, np.eye(4))
    np.testing.assert_allclose(accepted.camera_to_world, expected_pose)
    np.testing.assert_allclose(rejected.camera_to_world, expected_pose)
    assert accepted.metrics.translation_m == 0.02
    assert rejected.reason == "fitness_below_minimum"
    assert not rejected.accepted
    assert not rejected.keyframe
    assert len(keyframes.calls) == 2
    assert odometry.calls[1][0].sequence == 2
    assert imu.calls == 2


def test_tracker_relocalizes_against_older_keyframe_when_previous_frame_fails() -> None:
    keyframes = KeyframeStore(translation_threshold_m=0.001)
    odometry = FlexibleOdometry(
        [
            estimate(x_m=0.02),
            estimate(x_m=0.03, fitness=0.0, rmse_m=float("inf")),
            estimate(x_m=0.04),
        ]
    )
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed(), processed(), processed()]),
        imu_estimator=FakeImuEstimator(),
        odometry=odometry,
        quality_gate=QualityGate(min_depth_valid_ratio=0.01),
        keyframes=keyframes,
    )

    tracker.process(packet(1, 100_000))
    tracker.process(packet(2, 200_000))
    recovered = tracker.process(packet(3, 300_000))

    assert recovered.accepted
    assert recovered.state is TrackingState.TRACKING
    assert recovered.reason == "relocalized"
    np.testing.assert_allclose(recovered.camera_to_world[:3, 3], [-0.04, 0.0, 0.0])
    assert [call[0].sequence for call in odometry.calls] == [1, 2, 1]


def test_tracker_relocalization_commits_timestamp_once_for_a_packet() -> None:
    gate = RecordingQualityGate()
    tracker = MarkerlessTracker(
        intrinsics(),
        depth_processor=FakeDepthProcessor([processed(), processed(), processed()]),
        imu_estimator=FakeImuEstimator(),
        odometry=FlexibleOdometry(
            [
                estimate(x_m=0.02),
                estimate(x_m=0.03, fitness=0.0, rmse_m=float("inf")),
                estimate(x_m=0.04),
            ]
        ),
        quality_gate=gate,
        keyframes=KeyframeStore(translation_threshold_m=0.001),
    )

    tracker.process(packet(1, 100_000, host_timestamp_us=1_000_000))
    tracker.process(packet(2, 200_000, host_timestamp_us=1_100_000))
    recovered = tracker.process(packet(3, 300_000, host_timestamp_us=1_200_000))

    assert recovered.accepted
    assert gate.evaluate_timestamps == [1_100_000, 1_200_000]
