import numpy as np

from scanner_app.camera.models import SynchronizedFramePacket
from scanner_app.tracking.keyframes import KeyframeStore
from scanner_app.tracking.models import TrackingMetrics


def packet(timestamp_us: int) -> SynchronizedFramePacket:
    return SynchronizedFramePacket(
        color_bgr=np.arange(12, dtype=np.uint8).reshape(2, 2, 3),
        depth_raw=np.array([[1, 2], [3, 4]], dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=timestamp_us,
        color_timestamp_us=timestamp_us,
        imu_samples=tuple(),
        sequence=timestamp_us,
    )


def tracking_metrics() -> TrackingMetrics:
    return TrackingMetrics(0.8, 0.001, 0.01, 2.0, 0.8)


def pose(x: float = 0.0) -> np.ndarray:
    transform = np.eye(4, dtype=np.float64)
    transform[0, 3] = x
    return transform


def test_keyframe_store_keeps_first_and_motion_keyframes_only_for_accepted_frames() -> None:
    store = KeyframeStore()

    assert store.add(packet(100_000), pose(), tracking_metrics(), accepted=True)
    assert not store.add(packet(133_000), pose(0.001), tracking_metrics(), accepted=True)
    assert not store.add(packet(166_000), pose(0.1), tracking_metrics(), accepted=False)
    assert store.add(packet(200_000), pose(0.006), tracking_metrics(), accepted=True)

    assert len(store) == 2
    assert store.keyframes[1].packet.depth_timestamp_us == 200_000


def test_keyframe_store_creates_keyframe_for_rotation_or_age_and_copies_pose() -> None:
    store = KeyframeStore(rotation_threshold_deg=3.0, age_threshold_us=200_000)
    first_pose = pose()
    store.add(packet(100_000), first_pose, tracking_metrics(), accepted=True)
    first_pose[0, 3] = 99.0

    rotated = np.eye(4, dtype=np.float64)
    angle = np.deg2rad(4.0)
    rotated[:2, :2] = [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    assert store.add(packet(133_000), rotated, tracking_metrics(), accepted=True)
    assert store.add(packet(300_000), pose(0.001), tracking_metrics(), accepted=True)
    assert store.keyframes[0].camera_to_world[0, 3] == 0.0
