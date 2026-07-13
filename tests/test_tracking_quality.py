import numpy as np

from scanner_app.tracking.models import TrackingMetrics, TrackingState
from scanner_app.tracking.quality import QualityGate


def metrics(**overrides: float) -> TrackingMetrics:
    values = {
        "fitness": 0.8,
        "rmse_m": 0.001,
        "translation_m": 0.01,
        "rotation_deg": 4.0,
        "depth_valid_ratio": 0.6,
    }
    values.update(overrides)
    return TrackingMetrics(**values)


def test_quality_gate_accepts_valid_metrics_and_requires_increasing_timestamps() -> None:
    gate = QualityGate(min_depth_valid_ratio=0.5)

    accepted = gate.evaluate(metrics(), timestamp_us=100_000)
    repeated = gate.evaluate(metrics(), timestamp_us=100_000)

    assert accepted.accepted
    assert accepted.state is TrackingState.TRACKING
    assert not repeated.accepted
    assert repeated.state is TrackingState.DEGRADED
    assert repeated.reason == "timestamp_not_increasing"


def test_quality_gate_rejects_timestamp_gap_above_200ms() -> None:
    gate = QualityGate()

    assert gate.evaluate(metrics(), timestamp_us=100_000).accepted
    result = gate.evaluate(metrics(), timestamp_us=301_000)
    recovered = gate.evaluate(metrics(), timestamp_us=401_000)

    assert not result.accepted
    assert result.state is TrackingState.DEGRADED
    assert result.reason == "timestamp_gap_above_maximum"
    assert recovered.accepted
    assert recovered.state is TrackingState.TRACKING


def test_quality_gate_rejects_each_threshold_with_a_specific_reason() -> None:
    cases = {
        "fitness": "fitness_below_minimum",
        "rmse_m": "rmse_above_maximum",
        "translation_m": "translation_above_maximum",
        "rotation_deg": "rotation_above_maximum",
        "depth_valid_ratio": "depth_valid_ratio_below_minimum",
    }
    for field, reason in cases.items():
        gate = QualityGate(min_depth_valid_ratio=0.5)
        values = {field: 0.0}
        if field in {"rmse_m", "translation_m"}:
            values[field] = 1.0
        elif field == "rotation_deg":
            values[field] = 16.0
        result = gate.evaluate(metrics(**values), timestamp_us=100_000)
        assert not result.accepted
        assert result.reason == reason


def test_quality_gate_marks_three_rejections_lost_and_recovers() -> None:
    gate = QualityGate(min_depth_valid_ratio=0.5, lost_after_rejections=3)
    bad = metrics(fitness=0.1)

    assert gate.evaluate(bad, timestamp_us=100_000).state is TrackingState.DEGRADED
    assert gate.evaluate(bad, timestamp_us=200_000).state is TrackingState.DEGRADED
    assert gate.evaluate(bad, timestamp_us=300_000).state is TrackingState.LOST
    recovered = gate.evaluate(metrics(), timestamp_us=400_000)

    assert recovered.accepted
    assert recovered.state is TrackingState.TRACKING
    assert gate.rejected_count == 0
