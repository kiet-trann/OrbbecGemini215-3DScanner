"""Acceptance limits for markerless pose estimates."""

from scanner_app.tracking.models import TrackingMetrics, TrackingState


class QualityGate:
    def __init__(self, min_depth_valid_ratio: float = 0.5, lost_after_rejections: int = 3) -> None:
        self.min_depth_valid_ratio = min_depth_valid_ratio
        self.lost_after_rejections = lost_after_rejections
        self.rejected_count = 0
        self._last_timestamp_us: int | None = None

    def evaluate(self, metrics: TrackingMetrics, timestamp_us: int):
        reason = self._rejection_reason(metrics, timestamp_us)
        if reason is None:
            self._last_timestamp_us = timestamp_us
            self.rejected_count = 0
            return GateDecision(True, TrackingState.TRACKING, None)
        self.rejected_count += 1
        state = TrackingState.LOST if self.rejected_count >= self.lost_after_rejections else TrackingState.DEGRADED
        return GateDecision(False, state, reason)

    def _rejection_reason(self, metrics: TrackingMetrics, timestamp_us: int) -> str | None:
        if self._last_timestamp_us is not None and timestamp_us <= self._last_timestamp_us:
            return "timestamp_not_increasing"
        if metrics.fitness < 0.35:
            return "fitness_below_minimum"
        if metrics.rmse_m > 0.004:
            return "rmse_above_maximum"
        if metrics.translation_m > 0.050:
            return "translation_above_maximum"
        if metrics.rotation_deg > 15.0:
            return "rotation_above_maximum"
        if metrics.depth_valid_ratio < self.min_depth_valid_ratio:
            return "depth_valid_ratio_below_minimum"
        return None


class GateDecision:
    def __init__(self, accepted: bool, state: TrackingState, reason: str | None) -> None:
        self.accepted = accepted
        self.state = state
        self.reason = reason
