from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from scanner_app.camera.models import (
    CameraIntrinsics,
    CameraProfile,
    CaptureConfig,
    ImuSample,
    SynchronizedFramePacket,
)


def test_camera_profiles_have_operator_labels_ranges_and_mode_matchers() -> None:
    assert CameraProfile.NEAR.display_name == "Near — Close-up Precision"
    assert CameraProfile.NEAR.distance_range_m == (0.15, 0.32)
    assert CameraProfile.NEAR.mode_name_matches("Close_Up Precision Mode")
    assert CameraProfile.FAR.display_name == "Far — Long-distance"
    assert CameraProfile.FAR.distance_range_m == (0.20, 0.70)
    assert CameraProfile.FAR.mode_name_matches("Long-distance Mode")
    assert CameraProfile.FAR.mode_name_matches("Extended Distance Mode")


def test_packet_exposes_metric_depth_and_immutable_imu_tuple() -> None:
    gyro_sample = ImuSample("gyro", 19_995, np.array([1.0, 2.0, 3.0]))
    accel_sample = ImuSample("accel", 19_997, np.array([0.1, 0.2, 0.3]))
    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.array([[100, 0], [250, 300]], dtype=np.uint16),
        depth_scale_mm=0.5,
        depth_timestamp_us=20_000,
        color_timestamp_us=19_990,
        imu_samples=(gyro_sample, accel_sample),
        sequence=7,
    )

    np.testing.assert_array_equal(
        packet.depth_m,
        np.array([[0.05, 0.0], [0.125, 0.15]], dtype=np.float32),
    )
    assert isinstance(packet.imu_samples, tuple)
    assert packet.imu_samples == (gyro_sample, accel_sample)
    np.testing.assert_array_equal(packet.imu_samples[1].xyz, np.array([0.1, 0.2, 0.3]))
    with pytest.raises(FrozenInstanceError):
        packet.imu_samples = ()
    assert packet.sequence == 7
    assert CaptureConfig().depth_fps == 30
    assert CameraIntrinsics(1, 1, 0, 0, 2, 2).width == 2


def test_capture_config_defaults_encode_gemini_215_capture_constraints() -> None:
    config = CaptureConfig()

    assert config.depth_precision_mode == "Close_Up"
    assert config.depth_min_m == 0.15
    assert config.depth_max_m == 0.50
    assert config.normal_scan_min_m == 0.20
    assert config.normal_scan_max_m == 0.40
    assert config.object_min_cm == 5.0
    assert config.object_max_cm == 30.0
    assert config.depth_format == "Y16"
    assert config.color_format == "RGB"
