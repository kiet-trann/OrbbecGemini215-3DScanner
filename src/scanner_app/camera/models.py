from dataclasses import dataclass
from enum import Enum
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
    host_timestamp_us: int = 0

    @property
    def depth_m(self) -> np.ndarray:
        return self.depth_raw.astype(np.float32) * float(self.depth_scale_mm) * 0.001

    @property
    def tracking_timestamp_us(self) -> int:
        """Use the host's monotonic clock for tracking when capture provides it."""
        return self.host_timestamp_us if self.host_timestamp_us > 0 else self.depth_timestamp_us


@dataclass(frozen=True)
class CaptureConfig:
    depth_width: int = 1280
    depth_height: int = 800
    depth_fps: int = 30
    depth_format: Literal["Y16"] = "Y16"
    color_width: int = 1280
    color_height: int = 720
    color_fps: int = 30
    color_format: Literal["RGB"] = "RGB"
    imu_hz: int = 200
    depth_precision_mode: Literal["Close_Up"] = "Close_Up"
    depth_min_m: float = 0.15
    depth_max_m: float = 0.50
    normal_scan_min_m: float = 0.20
    normal_scan_max_m: float = 0.40
    object_min_cm: float = 5.0
    object_max_cm: float = 30.0


class CameraProfile(str, Enum):
    NEAR = "near"
    FAR = "far"

    @property
    def display_name(self) -> str:
        return "Near — Close-up Precision" if self is self.NEAR else "Far — Long-distance"

    @property
    def distance_range_m(self) -> tuple[float, float]:
        return (0.15, 0.32) if self is self.NEAR else (0.20, 0.70)

    def mode_name_matches(self, name: str) -> bool:
        normalized = name.casefold()
        return "close" in normalized if self is self.NEAR else "long" in normalized


@dataclass(frozen=True)
class CameraSettingsSnapshot:
    profile: CameraProfile
    preflight_state: str
    confirmed_mode: str | None
    supported_modes: tuple[str, ...]
    device_name: str | None
    serial_number: str | None
    firmware_version: str | None
    capture_config: CaptureConfig
    alignment_target: str
    enabled_depth_filters: tuple[str, ...]
