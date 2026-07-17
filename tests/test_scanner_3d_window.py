from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.activity import AutoPauseState
from scanner_app.rtabmap.models import RuntimeStatus, SavedSession
from scanner_app.rtabmap.windows_bridge import BridgeResult
from scanner_app.visualization.crop_catalog import CroppedObjOutput
from scanner_app.visualization.scanner_3d_window import (
    Scanner3DController,
    crop_preview_limits,
    crop_preview_layout,
    crop_view_preset,
    selected_crop_path,
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
    controller = Scanner3DController(
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
    controller = Scanner3DController(
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


def test_selected_crop_path_returns_selected_catalog_output(tmp_path: Path) -> None:
    output = CroppedObjOutput(
        tmp_path / "crop" / "model_cropped.obj",
        tmp_path / "crop",
        12,
        datetime.now(timezone.utc),
    )

    assert selected_crop_path([output], ("0",)) == output.path
    assert selected_crop_path([output], ()) is None
    assert selected_crop_path([output], ("5",)) is None


def test_crop_preview_uses_less_detail_while_rotating() -> None:
    moving, settled = crop_preview_limits()

    assert moving < settled
    assert moving == 700


def test_crop_view_presets_define_full_orbit_angles() -> None:
    assert crop_view_preset("front") == (-math.pi / 2.0, 0.0)
    assert crop_view_preset("back") == (math.pi / 2.0, 0.0)
    assert crop_view_preset("top") == (0.0, math.pi / 2.0)
    assert crop_view_preset("bottom") == (0.0, -math.pi / 2.0)
