from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


@dataclass(frozen=True)
class RgbdFrame:
    color: np.ndarray | None
    depth: np.ndarray
    depth_scale: float
    timestamp_ms: float

    @property
    def depth_mm(self) -> np.ndarray:
        return self.depth.astype(np.float32) * float(self.depth_scale)


@dataclass(frozen=True)
class ImuSample:
    sensor: Literal["gyro", "accel"]
    timestamp_us: int
    xyz: np.ndarray


@dataclass(frozen=True)
class SynchronizedFramePacket:
    color_bgr: np.ndarray
    depth_raw: np.ndarray
    depth_scale_mm: float
    depth_timestamp_us: int
    color_timestamp_us: int
    imu_samples: tuple[ImuSample, ...]
    sequence: int

    @property
    def depth_m(self) -> np.ndarray:
        return self.depth_raw.astype(np.float32) * float(self.depth_scale_mm) * 0.001


@dataclass(frozen=True)
class CaptureConfig:
    depth_width: int = 1280
    depth_height: int = 800
    depth_fps: int = 30
    color_width: int = 1280
    color_height: int = 720
    color_fps: int = 30
    imu_hz: int = 200
