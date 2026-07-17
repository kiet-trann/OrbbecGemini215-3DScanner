from dataclasses import dataclass
from pathlib import Path

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.activity import AutoPauseState
from scanner_app.rtabmap.models import RuntimeStatus, SavedSession
from scanner_app.rtabmap.windows_bridge import BridgeResult
from scanner_app.visualization.scanner_3d_window import (
    scanner_3dController,
    crop_preview_layout,
)


@dataclass
class FakeRuntime:
    status_value: RuntimeStatus = RuntimeStatus(True, "RTAB-Map is running")

    def status(self) -> RuntimeStatus:
        return self.status_value


@dataclass
class FakeMonitor:
    state: AutoPauseState


class FakeBridge:
    def __init__(self) -> None:
        self.pause_calls = 0
        self.resume_calls = 0

    def pause(self) -> BridgeResult:
        self.pause_calls += 1
        return BridgeResult(True, "Pause sent")

    def resume(self) -> BridgeResult:
        self.resume_calls += 1
        return BridgeResult(True, "Resume sent")


class FakeCatalog:
    def refresh(self) -> list[SavedSession]:
        return [SavedSession(Path("C:/sessions/scan.db"), 1024, modified_at=None)]  # type: ignore[arg-type]


def test_dashboard_marks_auto_pause_unavailable_when_activity_is_uncertain() -> None:
    controller = scanner_3dController(
        runtime=FakeRuntime(),
        bridge=FakeBridge(),
        monitor=FakeMonitor(AutoPauseState.UNCERTAIN),
        catalog=FakeCatalog(),
    )

    state = controller.refresh()

    assert not state.auto_pause_available
    assert state.auto_pause_message == "Auto-pause unavailable: activity signal is uncertain"
    assert [session.path.name for session in state.sessions] == ["scan.db"]


def test_manual_pause_and_resume_are_available_independently_of_auto_pause() -> None:
    bridge = FakeBridge()
    controller = scanner_3dController(
        runtime=FakeRuntime(),
        bridge=bridge,
        monitor=FakeMonitor(AutoPauseState.UNCERTAIN),
        catalog=FakeCatalog(),
    )

    assert controller.request_pause() == BridgeResult(True, "Pause sent")
    assert controller.request_resume() == BridgeResult(True, "Resume sent")
    assert (bridge.pause_calls, bridge.resume_calls) == (1, 1)


def test_crop_preview_separates_3d_navigation_from_rectangle_selection() -> None:
    layout = crop_preview_layout()

    assert layout.view_title == "3D model view"
    assert layout.crop_title == "Crop here"
    assert "Right-drag" in layout.view_instructions
    assert "wheel" in layout.view_instructions
    assert "Left-drag" in layout.crop_instructions
