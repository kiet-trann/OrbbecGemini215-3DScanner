import numpy as np

from scanner_app.camera.models import (
    CameraIntrinsics,
    CaptureConfig,
    ImuSample,
    SynchronizedFramePacket,
)


def test_packet_exposes_metric_depth_and_immutable_imu_tuple() -> None:
    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.array([[100, 0], [250, 300]], dtype=np.uint16),
        depth_scale_mm=0.5,
        depth_timestamp_us=20_000,
        color_timestamp_us=19_990,
        imu_samples=(ImuSample("gyro", 19_995, np.array([1.0, 2.0, 3.0])),),
        sequence=7,
    )

    np.testing.assert_array_equal(
        packet.depth_m,
        np.array([[0.05, 0.0], [0.125, 0.15]], dtype=np.float32),
    )
    assert packet.sequence == 7
    assert CaptureConfig().depth_fps == 30
    assert CameraIntrinsics(1, 1, 0, 0, 2, 2).width == 2
