import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.session.models import ScannerSnapshot, ScanSessionState
from scanner_app.tracking.models import TrackingMetrics, TrackingResult, TrackingState
from scanner_app.visualization.scanner_window import status_from_snapshot


def _snapshot_with_tracking(state: TrackingState) -> ScannerSnapshot:
    tracking = TrackingResult(
        state=state,
        camera_to_world=np.eye(4),
        metrics=TrackingMetrics(0.0, float("inf"), 0.0, 0.0, 1.0),
        accepted=state is TrackingState.TRACKING,
        keyframe=False,
        reason=state.value,
    )
    return ScannerSnapshot(
        state=ScanSessionState.TRACKING,
        color_bgr=None,
        tracking=tracking,
        preview_geometry=None,
        capture_fps=25.0,
        tracking_fps=15.0,
        preview_fps=2.0,
        depth_valid_ratio=0.8,
        coverage_ratio=0.5,
        trajectory_points=tuple(),
        message=None,
    )


def test_lost_tracking_status_is_red_and_blocks_fusion() -> None:
    snapshot = _snapshot_with_tracking(TrackingState.LOST)
    status = status_from_snapshot(snapshot)

    assert status.tracking_text == "LOST"
    assert status.tracking_color == (1.0, 0.2, 0.2)
    assert status.guidance == "Return to the last accepted view"
    assert not status.integrating


def test_status_line_includes_rejection_reason_and_quality_metrics() -> None:
    from scanner_app.visualization.scanner_window import format_status_line

    snapshot = _snapshot_with_tracking(TrackingState.LOST)
    line = format_status_line(snapshot)

    assert "reason=lost" in line
    assert "fit=0.00" in line
    assert "rmse=inf" in line


def test_tracking_status_is_green_and_allows_fusion() -> None:
    status = status_from_snapshot(_snapshot_with_tracking(TrackingState.TRACKING))

    assert status.tracking_text == "TRACKING"
    assert status.tracking_color == (0.2, 0.85, 0.35)
    assert status.integrating


def test_idle_status_asks_operator_to_hold_still() -> None:
    status = status_from_snapshot(ScannerSnapshot.idle())

    assert status.tracking_text == "READY"
    assert status.guidance == "Hold the camera still"
