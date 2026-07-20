# ruff: noqa: E402

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import tkinter as tk

import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.activity import AutoPauseState
from scanner_app.rtabmap.models import RuntimeStatus, SavedSession
from scanner_app.rtabmap.obj_crop import CropResult
from scanner_app.rtabmap.exporter import ExportResult
from scanner_app.rtabmap.windows_bridge import BridgeResult
from scanner_app.camera.models import CameraProfile, CameraSettingsSnapshot, CaptureConfig
from scanner_app.visualization.crop_catalog import CroppedObjOutput
from scanner_app.visualization.dashboard_theme import PRIMARY
from scanner_app.visualization.navigation import DashboardPage
from scanner_app.visualization import scanner_3d_window as scanner_window_module
from scanner_app.visualization.scanner_3d_window import (
    CardMetadata,
    DashboardState,
    Scanner3DController,
    Scanner3DWindow,
    build_summary_cards,
    camera_dashboard_cards,
    camera_control_state,
    camera_settings_rows,
    crop_card_metadata,
    crop_preview_limits,
    crop_preview_layout,
    crop_view_preset,
    preserved_selection,
    session_card_metadata,
)


@dataclass
class FakeRuntime:
    status_value: RuntimeStatus = RuntimeStatus(True, "RTAB-Map is running")
    launch_calls: int = 0

    def status(self) -> RuntimeStatus:
        return self.status_value

    def launch(self) -> RuntimeStatus:
        self.launch_calls += 1
        self.status_value = RuntimeStatus(True, "RTAB-Map started")
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


def make_snapshot(profile: CameraProfile = CameraProfile.NEAR) -> CameraSettingsSnapshot:
    return CameraSettingsSnapshot(
        profile=profile,
        preflight_state="applied-and-verified",
        confirmed_mode="Close_Up Precision Mode",
        supported_modes=("Close_Up Precision Mode", "Long-distance Mode"),
        device_name="Gemini 215",
        serial_number="G215-123",
        firmware_version="1.0.0",
        capture_config=CaptureConfig(),
        alignment_target="depth",
        enabled_depth_filters=("TemporalFilter",),
    )


class FakePreflight:
    def __init__(self) -> None:
        self.applied_profiles: list[CameraProfile] = []
        self.inspected_profiles: list[CameraProfile] = []

    def apply(self, profile: CameraProfile) -> CameraSettingsSnapshot:
        self.applied_profiles.append(profile)
        return make_snapshot(profile)

    def inspect(self, profile: CameraProfile) -> CameraSettingsSnapshot:
        self.inspected_profiles.append(profile)
        return make_snapshot(profile)


def make_controller(*, runtime: FakeRuntime, preflight: FakePreflight | None = None) -> Scanner3DController:
    return Scanner3DController(
        runtime=runtime,
        bridge=FakeBridge(),
        monitor=FakeMonitor(AutoPauseState.ACTIVE),
        catalog=FakeCatalog(),
        preflight=preflight or FakePreflight(),
    )


def test_apply_and_launch_runs_verified_preflight_before_runtime_launch() -> None:
    runtime = FakeRuntime(RuntimeStatus(False, "RTAB-Map is not running"))
    preflight = FakePreflight()
    controller = make_controller(runtime=runtime, preflight=preflight)

    result = controller.apply_and_launch()

    assert preflight.applied_profiles == [CameraProfile.NEAR]
    assert runtime.launch_calls == 1
    assert result.running


def test_controller_blocks_profile_changes_and_preflight_while_rtabmap_runs() -> None:
    controller = make_controller(runtime=FakeRuntime(RuntimeStatus(True, "RTAB-Map is running")))

    with pytest.raises(RuntimeError, match="locked"):
        controller.set_camera_profile(CameraProfile.FAR)
    with pytest.raises(RuntimeError, match="locked"):
        controller.inspect_camera()


def test_camera_settings_rows_show_defaults_before_inspection_and_snapshot_afterward() -> None:
    assert ("Preflight", "Not applied") in camera_settings_rows(CameraProfile.NEAR, None)
    assert ("Depth work mode", "Unavailable until inspection") in camera_settings_rows(
        CameraProfile.NEAR, None
    )

    rows = camera_settings_rows(CameraProfile.NEAR, make_snapshot())

    assert ("Depth work mode", "Close_Up Precision Mode") in rows
    assert ("Supported depth modes", "Close_Up Precision Mode; Long-distance Mode") in rows
    assert ("Enabled depth filters", "TemporalFilter") in rows


def test_camera_control_state_disables_profile_changes_when_locked() -> None:
    assert camera_control_state(False) == tk.NORMAL
    assert camera_control_state(True) == tk.DISABLED


def test_camera_dashboard_marks_the_active_profile_and_exposes_its_range() -> None:
    profiles, _device, _groups = camera_dashboard_cards(CameraProfile.NEAR, None)

    active = next(card for card in profiles if card.selected)

    assert active.profile is CameraProfile.NEAR
    assert active.label == CameraProfile.NEAR.display_name
    assert active.range_label == "0,15–0,32 m"


def test_camera_dashboard_uses_a_clear_uninspected_device_summary() -> None:
    _profiles, device, groups = camera_dashboard_cards(CameraProfile.NEAR, None)

    assert device.title == "Chưa kiểm tra thiết bị"
    assert device.inspection_label == "Kiểm tra thiết bị để xác nhận mode và căn chỉnh."
    assert groups[0].title == "Thông số luồng"


def test_camera_dashboard_keeps_orbbec_sdk_terms_after_inspection() -> None:
    _profiles, device, groups = camera_dashboard_cards(CameraProfile.NEAR, make_snapshot())

    assert device.title == "Gemini 215"
    assert "Close_Up Precision Mode" in device.inspection_label
    assert ("Enabled depth filters", "TemporalFilter") in groups[1].facts


class FakePageFrame:
    def __init__(self) -> None:
        self.grid_calls = 0
        self.remove_calls = 0

    def grid(self, **_kwargs) -> None:
        self.grid_calls += 1

    def grid_remove(self) -> None:
        self.remove_calls += 1


def test_summary_cards_keep_camera_session_and_result_navigation(tmp_path: Path) -> None:
    cards = build_summary_cards(
        CameraProfile.NEAR,
        [SavedSession(tmp_path / "scan.db", 1, modified_at=None)],  # type: ignore[arg-type]
        tmp_path / "scan.glb",
    )

    assert cards == (
        ("01 · CAMERA", CameraProfile.NEAR.display_name, DashboardPage.CAMERA),
        ("02 · PHIÊN QUÉT", "1 phiên đã lưu", DashboardPage.RESULTS),
        ("03 · KẾT QUẢ", "scan.glb", DashboardPage.RESULTS),
    )


class FakeSidebarButton:
    def __init__(self) -> None:
        self.colors: list[str] = []

    def configure(self, *, fg_color: str) -> None:
        self.colors.append(fg_color)


def test_show_page_only_changes_visible_page_and_sidebar_style() -> None:
    new_scan = FakePageFrame()
    camera = FakePageFrame()
    new_scan_button = FakeSidebarButton()
    camera_button = FakeSidebarButton()
    window = object.__new__(Scanner3DWindow)
    window.page_frames = {DashboardPage.NEW_SCAN: new_scan, DashboardPage.CAMERA: camera}
    window.sidebar_buttons = {
        DashboardPage.NEW_SCAN: new_scan_button,
        DashboardPage.CAMERA: camera_button,
    }
    window.active_page = DashboardPage.NEW_SCAN

    window.show_page(DashboardPage.CAMERA)

    assert window.active_page is DashboardPage.CAMERA
    assert new_scan.remove_calls == 1
    assert camera.grid_calls == 1
    assert new_scan_button.colors == ["transparent"]
    assert camera_button.colors == [PRIMARY]


def test_refresh_new_scan_uses_existing_dashboard_state_for_the_primary_action() -> None:
    class Value:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class Button:
        def __init__(self) -> None:
            self.text = ""
            self.command = None

        def configure(self, *, text: str, command=None) -> None:
            self.text = text
            self.command = command

    window = object.__new__(Scanner3DWindow)
    window.new_scan_heading = Value()
    window.new_scan_detail = Value()
    window.new_scan_primary_button = Button()
    window.new_scan_results_button = Button()
    window.sessions = []
    dashboard = DashboardState(
        runtime_message="RTAB-Map is not running",
        auto_pause_available=True,
        auto_pause_message="Auto-pause ready",
        sessions=(),
        busy=False,
        camera_profile=CameraProfile.NEAR,
        camera_snapshot=None,
        camera_controls_locked=False,
    )

    window._refresh_new_scan(dashboard)

    assert window.new_scan_heading.value == "Bước 1 / 3 · Chuẩn bị camera"
    assert window.new_scan_primary_button.text == "Kiểm tra camera"
    assert window.new_scan_results_button.text == "Chưa có phiên để xuất"


def test_launch_keeps_preflight_error_visible_after_refresh() -> None:
    class FailingController:
        def apply_and_launch(self):
            raise RuntimeError("No Orbbec camera found")

    class Status:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    window = object.__new__(Scanner3DWindow)
    window.controller = FailingController()
    window.status = Status()
    window.refresh = lambda: window.status.set("RTAB-Map is not running")

    window.launch()

    assert window.status.value == "No Orbbec camera found"


def test_runtime_poll_refreshes_once_when_rtabmap_stops() -> None:
    class Controller:
        def __init__(self) -> None:
            self.running = False

        def runtime_running(self) -> bool:
            return self.running

    class Root:
        def after(self, delay: int, callback) -> None:
            assert delay == 500
            self.callback = callback

    window = object.__new__(Scanner3DWindow)
    window.controller = Controller()
    window.root = Root()
    window.runtime_was_running = True
    refresh_calls: list[None] = []
    window.refresh = lambda: refresh_calls.append(None)

    window._poll_runtime()

    assert refresh_calls == [None]
    assert window.runtime_was_running is False


def test_dashboard_marks_auto_pause_unavailable_when_activity_is_uncertain() -> None:
    controller = Scanner3DController(
        runtime=FakeRuntime(),
        bridge=FakeBridge(),
        monitor=FakeMonitor(AutoPauseState.UNCERTAIN),
        catalog=FakeCatalog(),
    )

    state = controller.refresh()

    assert not state.auto_pause_available
    assert state.auto_pause_message == "Tự dừng không khả dụng: tín hiệu hoạt động không chắc chắn"
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

    assert layout.view_title == "Xem mô hình 3D"
    assert layout.crop_title == "Vùng cắt"
    assert "chuột phải" in layout.view_instructions
    assert "lăn chuột" in layout.view_instructions
    assert "chuột trái" in layout.crop_instructions


def test_selected_crop_output_uses_the_path_selected_by_its_card(tmp_path: Path) -> None:
    output = CroppedObjOutput(
        tmp_path / "crop" / "viewer" / "model_cropped.glb",
        tmp_path / "crop" / "viewer",
        12,
        datetime.now(timezone.utc),
    )
    window = object.__new__(Scanner3DWindow)
    window.cropped_outputs = [output]
    window.selected_crop_path = output.path.resolve()

    assert window._selected_crop_output() == output


def test_session_card_metadata_formats_the_saved_session_for_a_card(tmp_path: Path) -> None:
    session = SavedSession(
        tmp_path / "scan_01.db",
        1_572_864,
        modified_at=datetime(2026, 7, 20, 9, 31, tzinfo=timezone.utc),
    )

    metadata = session_card_metadata(session)

    assert metadata.title == "scan_01.db"
    assert metadata.subtitle == "20/07/2026 · 09:31 · 1,5 MB"
    assert metadata.detail == (("Dung lượng", "1,5 MB"), ("Cập nhật", "20/07/2026 · 09:31"))


def test_crop_card_metadata_includes_the_output_folder(tmp_path: Path) -> None:
    output = CroppedObjOutput(
        tmp_path / "cut_01.obj",
        tmp_path / "batch_01",
        2_097_152,
        datetime(2026, 7, 20, 9, 44, tzinfo=timezone.utc),
    )

    metadata = crop_card_metadata(output)

    assert metadata.title == "cut_01.obj"
    assert metadata.subtitle == "batch_01 · 20/07/2026 · 09:44 · 2,0 MB"
    assert ("Thư mục", "batch_01") in metadata.detail


def test_preserved_selection_keeps_only_a_path_still_in_the_refreshed_list(tmp_path: Path) -> None:
    kept = (tmp_path / "kept.db").resolve()

    assert preserved_selection([kept], kept) == kept
    assert preserved_selection([kept], (tmp_path / "missing.db").resolve()) is None


def test_select_session_rerenders_the_card_list_and_its_detail(tmp_path: Path) -> None:
    path = (tmp_path / "scan.db").resolve()
    window = object.__new__(Scanner3DWindow)
    window.selected_session_path = None
    rendered: list[str] = []
    window._refresh_session_cards = lambda: rendered.append("list")
    window._render_session_detail = lambda: rendered.append("detail")

    window._select_session(path)

    assert window.selected_session_path == path
    assert rendered == ["list", "detail"]


def test_card_button_uses_only_supported_customtkinter_options(monkeypatch) -> None:
    buttons: list[dict[str, object]] = []

    class Button:
        def __init__(self, _parent, **kwargs) -> None:
            buttons.append(kwargs)

        def pack(self, **_kwargs) -> None:
            pass

    monkeypatch.setattr(scanner_window_module.ctk, "CTkButton", Button)
    window = object.__new__(Scanner3DWindow)

    window._render_card(
        object(),
        CardMetadata("scan.db", "20/07/2026 · 09:31 · 1,5 MB", ()),
        selected=False,
        command=lambda: None,
    )

    assert "justify" not in buttons[0]


def test_record_crop_result_selects_compatible_obj(tmp_path: Path) -> None:
    selected: list[Path] = []

    class Status:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    window = object.__new__(Scanner3DWindow)
    window.refresh_crop_outputs = lambda select_path: selected.append(select_path)
    window.status = Status()
    result = CropResult(
        tmp_path / "crop",
        tmp_path / "crop" / "model_cropped.obj",
        tmp_path / "crop" / "viewer" / "model_cropped.glb",
    )

    window._record_crop_result(result)

    assert selected == [result.viewer_model]
    assert window.status.value == f"Cropped model: {result.viewer_model}"


def test_record_export_result_enables_opening_the_viewer_model(tmp_path: Path) -> None:
    rendered: list[None] = []

    class Status:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    viewer_model = tmp_path / "viewer" / "scan.glb"
    result = ExportResult(tmp_path, tmp_path / "raw.obj", tmp_path / "raw.mtl", (), viewer_model, tmp_path / "log", None)
    window = object.__new__(Scanner3DWindow)
    window.status = Status()
    window._render_crop_detail = lambda: rendered.append(None)
    window.latest_export_model = None

    window._record_export_result(result)

    assert window.latest_export_model == viewer_model
    assert rendered == [None]
    assert window.status.value == f"Exported for 3D Viewer: {viewer_model}"


def test_open_latest_exported_model_uses_the_recent_viewer_model(tmp_path: Path) -> None:
    opened: list[Path] = []

    class Status:
        def set(self, _value: str) -> None:
            pass

    class OpenActions:
        def open_obj(self, path: Path) -> BridgeResult:
            opened.append(path)
            return BridgeResult(True, "Opened")

    viewer_model = tmp_path / "viewer" / "scan.glb"
    window = object.__new__(Scanner3DWindow)
    window.latest_export_model = viewer_model
    window.open_actions = OpenActions()
    window.status = Status()

    window.open_latest_exported_model()

    assert opened == [viewer_model]


def test_crop_preview_uses_less_detail_while_rotating() -> None:
    moving, settled = crop_preview_limits()

    assert moving < settled
    assert moving == 700


def test_crop_view_presets_define_full_orbit_angles() -> None:
    assert crop_view_preset("front") == (-math.pi / 2.0, 0.0)
    assert crop_view_preset("back") == (math.pi / 2.0, 0.0)
    assert crop_view_preset("top") == (0.0, math.pi / 2.0)
    assert crop_view_preset("bottom") == (0.0, -math.pi / 2.0)
