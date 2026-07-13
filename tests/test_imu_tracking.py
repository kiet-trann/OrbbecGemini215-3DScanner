import numpy as np
import pytest

from scanner_app.camera.models import ImuSample
from scanner_app.tracking.imu import ImuEstimator
from scanner_app.tracking.models import TrackingMetrics, TrackingResult, TrackingState


def test_calibration_removes_constant_gyro_bias() -> None:
    estimator = ImuEstimator()
    samples = tuple(
        ImuSample("gyro", index * 5_000, np.array([0.0, 0.0, 0.01]))
        for index in range(400)
    ) + tuple(
        ImuSample("accel", index * 5_000, np.array([0.0, -9.81, 0.0]))
        for index in range(400)
    )

    estimator.calibrate(samples)
    rotation = estimator.predict_rotation(
        (
            ImuSample("gyro", 2_000_000, np.array([0.0, 0.0, 0.01])),
            ImuSample("gyro", 2_005_000, np.array([0.0, 0.0, 0.01])),
        )
    )

    np.testing.assert_allclose(rotation, np.eye(3), atol=1e-6)


def test_calibration_estimates_normalized_gravity_direction() -> None:
    estimator = ImuEstimator()
    samples = tuple(
        ImuSample("accel", index * 5_000, np.array([0.0, -9.81, 0.0]))
        for index in range(100)
    ) + tuple(
        ImuSample("gyro", index * 5_000, np.zeros(3))
        for index in range(100)
    )

    estimator.calibrate(samples)

    np.testing.assert_allclose(estimator.gravity_direction, [0.0, -1.0, 0.0])


def test_calibration_requires_stationary_gyro_and_accel_samples() -> None:
    estimator = ImuEstimator()
    samples = tuple(ImuSample("gyro", index, np.zeros(3)) for index in range(99))

    with pytest.raises(ValueError, match="100 stationary gyro"):
        estimator.calibrate(samples)


def test_prediction_returns_identity_for_insufficient_or_invalid_gyro_slice() -> None:
    estimator = ImuEstimator()

    np.testing.assert_allclose(
        estimator.predict_rotation((ImuSample("gyro", 1, np.ones(3)),)),
        np.eye(3),
    )
    np.testing.assert_allclose(
        estimator.predict_rotation(
            (
                ImuSample("gyro", 2_000, np.zeros(3)),
                ImuSample("gyro", 1_000, np.zeros(3)),
            )
        ),
        np.eye(3),
    )


def test_tracking_contracts_expose_accepted_result() -> None:
    metrics = TrackingMetrics(0.8, 0.001, 0.01, 2.0, 0.9)
    result = TrackingResult(
        state=TrackingState.TRACKING,
        camera_to_world=np.eye(4),
        metrics=metrics,
        accepted=True,
        keyframe=True,
    )

    assert result.accepted
    assert result.reason is None
