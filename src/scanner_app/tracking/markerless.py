"""Markerless RGB-D tracking orchestration."""

import numpy as np

from scanner_app.camera.models import CameraIntrinsics, SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import DepthProcessor, ProcessedDepth
from scanner_app.tracking.imu import ImuEstimator
from scanner_app.tracking.keyframes import KeyframeStore
from scanner_app.tracking.models import TrackingMetrics, TrackingResult, TrackingState
from scanner_app.tracking.quality import QualityGate
from scanner_app.tracking.rgbd_odometry import RgbdOdometryAdapter


class MarkerlessTracker:
    def __init__(
        self,
        intrinsics: CameraIntrinsics,
        depth_processor: DepthProcessor | None = None,
        imu_estimator: ImuEstimator | None = None,
        odometry: RgbdOdometryAdapter | None = None,
        quality_gate: QualityGate | None = None,
        keyframes: KeyframeStore | None = None,
    ) -> None:
        self.intrinsics = intrinsics
        self.depth_processor = depth_processor if depth_processor is not None else DepthProcessor(0.20, 0.30)
        self.imu_estimator = imu_estimator if imu_estimator is not None else ImuEstimator()
        self.odometry = odometry if odometry is not None else RgbdOdometryAdapter(intrinsics)
        self.quality_gate = quality_gate if quality_gate is not None else QualityGate()
        self.keyframes = keyframes if keyframes is not None else KeyframeStore()

        self._previous_packet: SynchronizedFramePacket | None = None
        self._previous_depth: ProcessedDepth | None = None
        self._camera_to_world: np.ndarray | None = None

    def process(self, packet: SynchronizedFramePacket) -> TrackingResult:
        current_depth = self.depth_processor.process(packet)
        if self._previous_packet is None:
            return self._initialize(packet, current_depth)

        assert self._previous_depth is not None
        assert self._camera_to_world is not None

        imu_rotation = self.imu_estimator.predict_rotation(packet.imu_samples)
        estimate = self.odometry.estimate(
            self._previous_packet,
            self._previous_depth,
            packet,
            current_depth,
            imu_rotation,
        )
        metrics = _metrics_from_estimate(estimate.relative_transform, estimate)
        decision = self.quality_gate.evaluate(metrics, packet.depth_timestamp_us)

        if not decision.accepted:
            return TrackingResult(
                state=decision.state,
                camera_to_world=self._camera_to_world.copy(),
                metrics=metrics,
                accepted=False,
                keyframe=False,
                reason=decision.reason,
            )

        camera_to_world = self._camera_to_world @ np.linalg.inv(
            np.asarray(estimate.relative_transform, dtype=np.float64)
        )
        self._previous_packet = packet
        self._previous_depth = current_depth
        self._camera_to_world = camera_to_world
        keyframe = self.keyframes.add(packet, camera_to_world, metrics, accepted=True)
        return TrackingResult(
            state=decision.state,
            camera_to_world=camera_to_world.copy(),
            metrics=metrics,
            accepted=True,
            keyframe=keyframe,
            reason=decision.reason,
        )

    def _initialize(
        self,
        packet: SynchronizedFramePacket,
        processed_depth: ProcessedDepth,
    ) -> TrackingResult:
        metrics = TrackingMetrics(
            fitness=1.0 if processed_depth.valid_ratio > 0.0 else 0.0,
            rmse_m=0.0,
            translation_m=0.0,
            rotation_deg=0.0,
            depth_valid_ratio=processed_depth.valid_ratio,
        )
        if processed_depth.valid_ratio == 0.0:
            return TrackingResult(
                state=TrackingState.INITIALIZING,
                camera_to_world=np.eye(4, dtype=np.float64),
                metrics=metrics,
                accepted=False,
                keyframe=False,
                reason="depth_valid_ratio_zero",
            )
        min_depth_valid_ratio = getattr(self.quality_gate, "min_depth_valid_ratio", 0.5)
        if processed_depth.valid_ratio < min_depth_valid_ratio:
            return TrackingResult(
                state=TrackingState.INITIALIZING,
                camera_to_world=np.eye(4, dtype=np.float64),
                metrics=metrics,
                accepted=False,
                keyframe=False,
                reason="depth_valid_ratio_below_minimum",
            )

        camera_to_world = np.eye(4, dtype=np.float64)
        self._previous_packet = packet
        self._previous_depth = processed_depth
        self._camera_to_world = camera_to_world
        keyframe = self.keyframes.add(packet, camera_to_world, metrics, accepted=True)
        return TrackingResult(
            state=TrackingState.TRACKING,
            camera_to_world=camera_to_world.copy(),
            metrics=metrics,
            accepted=True,
            keyframe=keyframe,
            reason=None,
        )


def _metrics_from_estimate(relative_transform: np.ndarray, estimate) -> TrackingMetrics:
    transform = np.asarray(relative_transform, dtype=np.float64)
    rotation = transform[:3, :3]
    trace_value = np.clip((np.trace(rotation) - 1.0) * 0.5, -1.0, 1.0)
    rotation_deg = float(np.degrees(np.arccos(trace_value)))
    translation_m = float(np.linalg.norm(transform[:3, 3]))
    return TrackingMetrics(
        fitness=float(estimate.fitness),
        rmse_m=float(estimate.rmse_m),
        translation_m=translation_m,
        rotation_deg=rotation_deg,
        depth_valid_ratio=float(estimate.depth_valid_ratio),
    )
