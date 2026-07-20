# ruff: noqa: E402

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.dashboard_theme import dashboard_status


def test_dashboard_status_marks_running_runtime_as_ready() -> None:
    status = dashboard_status("RTAB-Map is running")

    assert status.label == "Đang quét"
    assert status.tone == "ready"


def test_dashboard_status_marks_camera_errors_as_destructive() -> None:
    status = dashboard_status("No Orbbec camera found")

    assert status.label == "No Orbbec camera found"
    assert status.tone == "error"


def test_dashboard_status_uses_neutral_copy_when_runtime_is_idle() -> None:
    status = dashboard_status("RTAB-Map is not running")

    assert status.label == "Sẵn sàng chuẩn bị"
    assert status.tone == "neutral"
