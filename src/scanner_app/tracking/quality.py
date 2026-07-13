"""Acceptance limits for markerless pose estimates."""

from scanner_app.tracking.models import TrackingMetrics, TrackingState


class QualityGate:
    def __init__(
        self,
        min_depth_valid_ratio: float = 0.5,
        lost_after_rejections: int = 3,
        max_timestamp_gap_us: int = 200_000,
        min_fitness: float = 0.35,
        max_rmse_m: float = 0.004,
        max_translation_m: float = 0.050,
        max_rotation_deg: float = 15.0,
    ) -> None:
        self.min_depth_valid_ratio = min_depth_valid_ratio
        self.lost_after_rejections = lost_after_rejections
        self.max_timestamp_gap_us = max_timestamp_gap_us
        self.min_fitness = min_fitness
        self.max_rmse_m = max_rmse_m
        self.max_translation_m = max_translation_m
        self.max_rotation_deg = max_rotation_deg
        self.rejected_count = 0
        self._last_timestamp_us: int | None = None

    def evaluate(self, metrics: TrackingMetrics, timestamp_us: int):
        reason = self._rejection_reason(metrics, timestamp_us)
        if reason is None:
            self._last_timestamp_us = timestamp_us
            self.rejected_count = 0
            return GateDecision(True, TrackingState.TRACKING, None)
        if reason == "timestamp_gap_above_maximum":
            self._last_timestamp_us = timestamp_us
        self.rejected_count += 1
        state = TrackingState.LOST if self.rejected_count >= self.lost_after_rejections else TrackingState.DEGRADED
        return GateDecision(False, state, reason)

    def metrics_rejection_reason(self, metrics: TrackingMetrics) -> str | None:
        return self._metrics_rejection_reason(metrics)

    def _rejection_reason(self, metrics: TrackingMetrics, timestamp_us: int) -> str | None:
        if self._last_timestamp_us is not None and timestamp_us <= self._last_timestamp_us:
            return "timestamp_not_increasing"
        if self._last_timestamp_us is not None and timestamp_us - self._last_timestamp_us > self.max_timestamp_gap_us:
            return "timestamp_gap_above_maximum"
        return self._metrics_rejection_reason(metrics)

    def _metrics_rejection_reason(self, metrics: TrackingMetrics) -> str | None:
        if metrics.fitness < self.min_fitness:
            return "fitness_below_minimum"
        if metrics.rmse_m > self.max_rmse_m:
            return "rmse_above_maximum"
        if metrics.translation_m > self.max_translation_m:
            return "translation_above_maximum"
        if metrics.rotation_deg > self.max_rotation_deg:
            return "rotation_above_maximum"
        if metrics.depth_valid_ratio < self.min_depth_valid_ratio:
            return "depth_valid_ratio_below_minimum"
        return None


class GateDecision:
    def __init__(self, accepted: bool, state: TrackingState, reason: str | None) -> None:
        self.accepted = accepted
        self.state = state
        self.reason = reason
