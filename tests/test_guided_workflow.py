# ruff: noqa: E402

from dataclasses import dataclass

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.guided_workflow import GuidedMode, guided_workflow


@dataclass(frozen=True)
class Dashboard:
    runtime_message: str
    camera_controls_locked: bool
    camera_snapshot: object | None


def test_workflow_requests_camera_inspection_before_a_snapshot_exists() -> None:
    state = guided_workflow(Dashboard("RTAB-Map is not running", False, None), has_sessions=False)

    assert state.mode is GuidedMode.CHECK_CAMERA
    assert state.primary_label == "Kiểm tra camera"
    assert state.camera_ready is False
    assert state.results_ready is False


def test_workflow_starts_scan_after_camera_inspection() -> None:
    state = guided_workflow(Dashboard("RTAB-Map is not running", False, object()), has_sessions=False)

    assert state.mode is GuidedMode.START_SCAN
    assert state.primary_label == "Bắt đầu quét"
    assert state.camera_ready is True


def test_workflow_uses_live_controls_while_camera_is_locked() -> None:
    state = guided_workflow(Dashboard("RTAB-Map is running", True, object()), has_sessions=True)

    assert state.mode is GuidedMode.LIVE_CONTROL
    assert state.primary_label == "Tạm dừng"
    assert state.camera_locked is True
    assert state.results_ready is True
