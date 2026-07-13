"""Retention policy for accepted markerless tracking views."""

from dataclasses import dataclass
import numpy as np
from scipy.spatial.transform import Rotation

from scanner_app.camera.models import SynchronizedFramePacket
from scanner_app.tracking.models import TrackingMetrics


@dataclass(frozen=True)
class Keyframe:
    packet: SynchronizedFramePacket
    camera_to_world: np.ndarray
    metrics: TrackingMetrics


class KeyframeStore:
    def __init__(self, translation_threshold_m: float = 0.005, rotation_threshold_deg: float = 3.0, age_threshold_us: int = 200_000) -> None:
        self.translation_threshold_m = translation_threshold_m
        self.rotation_threshold_deg = rotation_threshold_deg
        self.age_threshold_us = age_threshold_us
        self.keyframes: list[Keyframe] = []

    def __len__(self) -> int:
        return len(self.keyframes)

    def add(self, packet: SynchronizedFramePacket, camera_to_world: np.ndarray, metrics: TrackingMetrics, *, accepted: bool) -> bool:
        if not accepted:
            return False
        if self.keyframes and not self._should_add(packet, camera_to_world):
            return False
        self.keyframes.append(Keyframe(packet, np.asarray(camera_to_world, dtype=np.float64).copy(), metrics))
        return True

    def _should_add(self, packet: SynchronizedFramePacket, pose: np.ndarray) -> bool:
        previous = self.keyframes[-1]
        delta = np.asarray(pose)[:3, 3] - previous.camera_to_world[:3, 3]
        rotation = Rotation.from_matrix(previous.camera_to_world[:3, :3].T @ np.asarray(pose)[:3, :3]).magnitude()
        return bool(np.linalg.norm(delta) >= self.translation_threshold_m or np.degrees(rotation) >= self.rotation_threshold_deg or packet.depth_timestamp_us - previous.packet.depth_timestamp_us >= self.age_threshold_us)
