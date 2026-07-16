import os
from pathlib import Path
import sys
import subprocess

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import ProcessedDepth
from scanner_app.tracking.rgbd_odometry import (
    BackgroundAssistedRgbdOdometryBackend,
    OdometryEstimate,
    OpenCvRgbdOdometryBackend,
    RgbdOdometryAdapter,
    VisualPnpOdometryBackend,
    estimate_rigid_transform_3d,
    scale_tracking_intrinsics,
)


def test_background_assisted_backend_uses_stricter_geometric_match_limits() -> None:
    backend = BackgroundAssistedRgbdOdometryBackend()

    assert backend.max_features == 1600
    assert backend.min_matches == 24
    assert backend.min_inliers == 16
    assert backend.ransac_threshold_m == 0.008
    assert backend.requires_current_depth is False


def test_visual_pnp_recovers_motion_without_current_depth() -> None:
    intrinsics = CameraIntrinsics(500, 500, 320, 240, 640, 480)
    source_points = np.array(
        [
            [-0.03, -0.02, 0.25],
            [0.03, -0.02, 0.25],
            [-0.03, 0.02, 0.28],
            [0.03, 0.02, 0.28],
            [0.00, 0.00, 0.32],
            [0.02, -0.01, 0.30],
        ],
        dtype=np.float64,
    )
    expected = np.eye(4)
    expected[:3, 3] = [0.005, -0.002, 0.001]
    transformed = source_points + expected[:3, 3]
    image_points = np.column_stack(
        (
            intrinsics.fx * transformed[:, 0] / transformed[:, 2] + intrinsics.cx,
            intrinsics.fy * transformed[:, 1] / transformed[:, 2] + intrinsics.cy,
        )
    )

    result = VisualPnpOdometryBackend(min_matches=4, min_inliers=4).estimate_pnp(
        source_points,
        image_points,
        intrinsics,
        np.eye(4),
        current_depth_m=np.zeros((4, 4), dtype=np.float32),
    )

    assert result.fitness == 1.0
    assert result.depth_valid_ratio == 0.0
    assert result.rmse_m < 0.001
    np.testing.assert_allclose(result.relative_transform[:3, 3], expected[:3, 3], atol=0.001)


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


def test_adapter_rejects_sparse_depth_before_backend_call() -> None:
    backend = FakeBackend()
    adapter = RgbdOdometryAdapter(
        CameraIntrinsics(800, 600, 640, 400, 1280, 800),
        backend=backend,
    )
    color = np.zeros((20, 20, 3), dtype=np.uint8)
    sparse_depth = np.zeros((20, 20), dtype=np.float32)
    sparse_depth[0, 0] = 0.25

    estimate = adapter.estimate(
        packet(color),
        processed(sparse_depth),
        packet(color),
        processed(sparse_depth),
        np.eye(3),
    )

    assert backend.calls == []
    assert estimate.fitness == 0.0
    assert np.isinf(estimate.rmse_m)
    assert estimate.depth_valid_ratio == 0.0025


def test_adapter_allows_visual_backend_when_only_current_depth_is_missing() -> None:
    class VisualBackend(FakeBackend):
        requires_current_depth = False

    backend = VisualBackend()
    adapter = RgbdOdometryAdapter(
        CameraIntrinsics(800, 600, 640, 400, 1280, 800),
        backend=backend,
    )
    color = np.zeros((40, 40, 3), dtype=np.uint8)
    previous_depth = np.full((40, 40), 0.25, dtype=np.float32)
    current_depth = np.zeros((40, 40), dtype=np.float32)

    estimate = adapter.estimate(
        packet(color),
        processed(previous_depth),
        packet(color),
        processed(current_depth),
        np.eye(3),
    )

    assert len(backend.calls) == 1
    assert estimate.fitness == 0.7


def test_estimate_rigid_transform_3d_recovers_translation_and_rmse() -> None:
    source = np.array(
        [
            [0.0, 0.0, 0.25],
            [0.02, 0.0, 0.25],
            [0.0, 0.02, 0.25],
            [0.02, 0.02, 0.25],
        ],
        dtype=np.float64,
    )
    target = source + np.array([0.01, -0.005, 0.002])

    transform, rmse = estimate_rigid_transform_3d(source, target)

    np.testing.assert_allclose(transform[:3, :3], np.eye(3), atol=1e-9)
    np.testing.assert_allclose(transform[:3, 3], [0.01, -0.005, 0.002], atol=1e-9)
    assert rmse < 1e-12


def test_opencv_backend_returns_failed_estimate_when_features_are_missing() -> None:
    backend = OpenCvRgbdOdometryBackend(min_matches=6)
    color = np.zeros((40, 60, 3), dtype=np.uint8)
    depth = np.full((40, 60), 0.25, dtype=np.float32)
    initial = np.eye(4)

    estimate = backend.estimate(
        color,
        depth,
        color,
        depth,
        CameraIntrinsics(50, 50, 30, 20, 60, 40),
        initial,
    )

    assert estimate.fitness == 0.0
    assert np.isinf(estimate.rmse_m)
    np.testing.assert_allclose(estimate.relative_transform, initial)


def test_importing_adapter_does_not_import_open3d_until_production_backend_is_used() -> None:
    code = (
        "import sys; "
        "import scanner_app.tracking.rgbd_odometry; "
        "raise SystemExit(1 if 'open3d' in sys.modules else 0)"
    )
    src_path = Path(__file__).resolve().parents[1] / "src"
    env = {**os.environ, "PYTHONPATH": str(src_path)}
    result = subprocess.run([sys.executable, "-c", code], check=False, env=env)
    assert result.returncode == 0
