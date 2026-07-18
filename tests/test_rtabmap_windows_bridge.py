import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.windows_bridge import BridgeResult, WindowsRtabmapBridge


def test_pause_refuses_to_send_when_no_matching_window() -> None:
    bridge = WindowsRtabmapBridge(
        find_windows=lambda: [(101, "Untitled - Notepad")],
        send_space=lambda hwnd: pytest.fail("must not send a key"),
    )

    result = bridge.pause()

    assert result == BridgeResult(False, "RTAB-Map window was not found")


def test_pause_refuses_to_send_when_multiple_rtabmap_windows_match() -> None:
    bridge = WindowsRtabmapBridge(
        find_windows=lambda: [(42, "RTAB-Map*"), (43, "RTAB-Map")],
        send_space=lambda hwnd: pytest.fail("must not send a key"),
    )

    result = bridge.pause()

    assert result == BridgeResult(False, "RTAB-Map window is ambiguous")


def test_pause_sends_space_once_to_single_rtabmap_window() -> None:
    sent: list[int] = []
    bridge = WindowsRtabmapBridge(
        find_windows=lambda: [(42, "RTAB-Map*")],
        send_space=sent.append,
    )

    assert bridge.pause() == BridgeResult(True, "Pause sent")
    assert sent == [42]


def test_pause_reports_windows_input_failure_without_raising() -> None:
    def reject_input(_hwnd: int) -> None:
        raise OSError("access denied")

    bridge = WindowsRtabmapBridge(
        find_windows=lambda: [(42, "RTAB-Map")],
        send_space=reject_input,
    )

    assert bridge.pause() == BridgeResult(False, "Pause failed: access denied")
