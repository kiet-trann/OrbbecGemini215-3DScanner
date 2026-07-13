"""Gyroscope rotation prior for markerless tracking."""

import numpy as np
from scipy.spatial.transform import Rotation

from scanner_app.camera.models import ImuSample


class ImuEstimator:
    """Estimate relative camera rotation from calibrated gyro samples."""

    def __init__(self) -> None:
        self.gyro_bias = np.zeros(3, dtype=np.float64)
        self.gravity_direction = np.array([0.0, -1.0, 0.0], dtype=np.float64)

    def calibrate(self, samples: tuple[ImuSample, ...]) -> None:
        gyro = [sample.xyz for sample in samples if sample.sensor == "gyro"]
        accel = [sample.xyz for sample in samples if sample.sensor == "accel"]
        if len(gyro) < 100:
            raise ValueError("At least 100 stationary gyro samples are required.")
        if len(accel) < 100:
            raise ValueError("At least 100 stationary accelerometer samples are required.")

        self.gyro_bias = np.mean(np.asarray(gyro, dtype=np.float64), axis=0)
        gravity = np.mean(np.asarray(accel, dtype=np.float64), axis=0)
        gravity_norm = np.linalg.norm(gravity)
        if not np.isfinite(gravity_norm) or gravity_norm == 0.0:
            raise ValueError("Stationary accelerometer samples must define non-zero gravity.")
        self.gravity_direction = gravity / gravity_norm

    def predict_rotation(self, samples: tuple[ImuSample, ...]) -> np.ndarray:
        gyro = [sample for sample in samples if sample.sensor == "gyro"]
        if len(gyro) < 2:
            return np.eye(3, dtype=np.float64)

        if any(second.timestamp_us <= first.timestamp_us for first, second in zip(gyro, gyro[1:])):
            return np.eye(3, dtype=np.float64)

        rotation = Rotation.identity()
        for first, second in zip(gyro, gyro[1:]):
            dt = (second.timestamp_us - first.timestamp_us) * 1e-6
            omega = 0.5 * (
                np.asarray(first.xyz, dtype=np.float64) + np.asarray(second.xyz, dtype=np.float64)
            ) - self.gyro_bias
            rotation = rotation * Rotation.from_rotvec(omega * dt)
        return rotation.as_matrix()
