import sys

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import ProcessedDepth
from scanner_app.tracking.rgbd_odometry import (
    OdometryEstimate,
    RgbdOdometryAdapter,
    scale_tracking_intrinsics,
)


class FakeBackend:
    def __init__(self) -> None:
        self.calls = []

    def estimate(
        self,
        previous_color_rgb: np.ndarray,
        previous_depth_m: np.ndarray,
        current_color_rgb: np.ndarray,
        current_depth_m: np.ndarray,
        intrinsics: CameraIntrinsics,
        initial_transform: np.ndarray,
    ) -> OdometryEstimate:
        self.calls.append(
            {
                "previous_color_rgb": previous_color_rgb,
                "previous_depth_m": previous_depth_m,
                "current_color_rgb": current_color_rgb,
                "current_depth_m": current_depth_m,
                "intrinsics": intrinsics,
                "initial_transform": initial_transform,
            }
        )
        transform = np.eye(4)
        transform[0, 3] = 0.01
        return OdometryEstimate(transform, fitness=0.7, rmse_m=0.002, depth_valid_ratio=0.0)


def packet(color_bgr: np.ndarray) -> SynchronizedFramePacket:
    return SynchronizedFramePacket(
        color_bgr=color_bgr,
        depth_raw=np.ones(color_bgr.shape[:2], dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=1_000,
        color_timestamp_us=1_000,
        imu_samples=(),
        sequence=1,
    )


def processed(depth_m: np.ndarray) -> ProcessedDepth:
    return ProcessedDepth(
        depth_m=depth_m.astype(np.float32),
        valid_mask=depth_m > 0,
        valid_ratio=float(np.mean(depth_m > 0)),
        median_depth_m=None,
    )


def test_scale_tracking_intrinsics_scales_camera_model_to_tracking_size() -> None:
    source = CameraIntrinsics(800, 600, 640, 400, 1280, 800)

    scaled = scale_tracking_intrinsics(source)

    assert scaled == CameraIntrinsics(400, 300, 320, 200, 640, 400)


def test_adapter_resizes_rgbd_inputs_converts_bgr_to_rgb_and_uses_imu_initial_transform() -> None:
    backend = FakeBackend()
    adapter = RgbdOdometryAdapter(
        CameraIntrinsics(800, 600, 640, 400, 1280, 800),
        backend=backend,
    )
    previous_color = np.array(
        [
            [[10, 20, 30], [40, 50, 60]],
            [[70, 80, 90], [100, 110, 120]],
        ],
        dtype=np.uint8,
    )
    current_color = previous_color + 1
    previous_depth = np.array([[0.20, 0.21], [0.22, 0.23]], dtype=np.float32)
    current_depth = np.array([[0.30, 0.0], [0.31, 0.0]], dtype=np.float32)
    imu_rotation = np.array(
        [
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )

    estimate = adapter.estimate(
        packet(previous_color),
        processed(previous_depth),
        packet(current_color),
        processed(current_depth),
        imu_rotation,
    )

    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call["previous_color_rgb"].shape == (400, 640, 3)
    assert call["previous_depth_m"].shape == (400, 640)
    assert call["current_color_rgb"].shape == (400, 640, 3)
    assert call["current_depth_m"].shape == (400, 640)
    np.testing.assert_array_equal(call["previous_color_rgb"][0, 0], [30, 20, 10])
    np.testing.assert_array_equal(call["current_color_rgb"][0, 0], [31, 21, 11])
    assert call["intrinsics"] == CameraIntrinsics(400, 300, 320, 200, 640, 400)
    expected_initial = np.eye(4)
    expected_initial[:3, :3] = imu_rotation
    np.testing.assert_allclose(call["initial_transform"], expected_initial)
    assert estimate.fitness == 0.7
    assert estimate.rmse_m == 0.002
    assert estimate.depth_valid_ratio == 0.5


def test_importing_adapter_does_not_import_open3d_until_production_backend_is_used() -> None:
    assert "open3d" not in sys.modules
