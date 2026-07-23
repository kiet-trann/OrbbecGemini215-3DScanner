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
from scanner_app.rtabmap.obj_crop import CropRectangle, CropResult
from scanner_app.rtabmap.exporter import ExportResult
from scanner_app.rtabmap.windows_bridge import BridgeResult
from scanner_app.camera.models import CameraProfile, CameraSettingsSnapshot, CaptureConfig
from scanner_app.camera.preflight import CameraPreflightError
from scanner_app.visualization.crop_catalog import CroppedObjOutput
from scanner_app.visualization.dashboard_theme import PRIMARY
from scanner_app.visualization.navigation import DashboardPage
from scanner_app.visualization.open_actions import OpenActionResult
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
        firmware_version="1.0.9",
        capture_config=CaptureConfig(),
        alignment_target="depth",
        enabled_depth_filters=("TemporalFilter",),
        connection_type="USB3.0",
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


def test_apply_and_launch_does_not_launch_runtime_after_usb_preflight_failure() -> None:
    class RejectingPreflight:
        def apply(self, _profile: CameraProfile) -> CameraSettingsSnapshot:
            raise CameraPreflightError("Gemini 215 yêu cầu kết nối USB 3")

    runtime = FakeRuntime(RuntimeStatus(False, "RTAB-Map is not running"))
    controller = make_controller(runtime=runtime, preflight=RejectingPreflight())

    with pytest.raises(CameraPreflightError, match="USB 3"):
        controller.apply_and_launch()

    assert runtime.launch_calls == 0


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
    assert ("Connection", "Unavailable until inspection") in camera_settings_rows(
        CameraProfile.NEAR, None
    )

    rows = camera_settings_rows(CameraProfile.NEAR, make_snapshot())

    assert ("Depth work mode", "Close_Up Precision Mode") in rows
    assert ("Supported depth modes", "Close_Up Precision Mode; Long-distance Mode") in rows
    assert ("Connection", "USB3.0") in rows
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
    assert "USB3.0" in device.inspection_label
    assert ("Enabled depth filters", "TemporalFilter") in groups[1].facts


def test_select_camera_profile_rerenders_after_a_successful_change() -> None:
    class Controller:
        def set_camera_profile(self, profile: CameraProfile) -> None:
            self.profile = profile

    rendered: list[str] = []
    notifications: list[tuple[str, str]] = []
    window = object.__new__(Scanner3DWindow)
    window.controller = Controller()
    window.refresh = lambda: rendered.append("dashboard")
    window.notify = lambda message, tone="info": notifications.append((message, tone))

    window._select_camera_profile(CameraProfile.FAR)

    assert window.controller.profile is CameraProfile.FAR
    assert rendered == ["dashboard"]
    assert notifications == [("Đã chọn cấu hình camera: Far — Long-distance", "success")]


def test_notify_does_not_show_absolute_paths() -> None:
    class Toast:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show(self, message: str, tone: str) -> None:
            self.messages.append((message, tone))

    window = object.__new__(Scanner3DWindow)
    window.toast = Toast()

    window.notify("Không thể mở C:\\models\\scan.obj", "error")

    message, tone = window.toast.messages[0]
    assert "C:\\models\\scan.obj" not in message
    assert tone == "error"


def test_notify_redacts_a_bare_drive_root_at_end_of_message() -> None:
    class Toast:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show(self, message: str, tone: str) -> None:
            self.messages.append((message, tone))

    window = object.__new__(Scanner3DWindow)
    window.toast = Toast()

    window.notify("Failed C:\\", "error")

    message, tone = window.toast.messages[0]
    assert "C:\\" not in message
    assert "Failed" in message
    assert tone == "error"


@pytest.mark.parametrize(
    ("path", "tail"),
    [
        ("C:\\Scan Results\\batch one\\model.obj", "batch one\\model.obj"),
        ("\\\\scanner-host\\shared results\\batch one\\model.obj", "batch one\\model.obj"),
    ],
)
def test_notify_redacts_windows_paths_with_spaces_and_unc_paths(path: str, tail: str) -> None:
    class Toast:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show(self, message: str, tone: str) -> None:
            self.messages.append((message, tone))

    window = object.__new__(Scanner3DWindow)
    window.toast = Toast()

    window.notify(f"Không thể mở {path} ngay bây giờ", "error")

    message, tone = window.toast.messages[0]
    assert path not in message
    assert tail not in message
    assert "Không thể mở" in message
    assert tone == "error"


@pytest.mark.parametrize(
    ("path", "tail"),
    [
        ("C:\\Scan Results\\active batch", "active batch"),
        ("\\\\scanner-host\\shared results\\active batch", "active batch"),
    ],
)
def test_notify_redacts_windows_directory_paths_without_extensions(path: str, tail: str) -> None:
    class Toast:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show(self, message: str, tone: str) -> None:
            self.messages.append((message, tone))

    window = object.__new__(Scanner3DWindow)
    window.toast = Toast()

    window.notify(f"Không thể mở {path}", "error")

    message, tone = window.toast.messages[0]
    assert path not in message
    assert tail not in message
    assert "Không thể mở" in message
    assert tone == "error"


@pytest.mark.parametrize(
    ("path", "tail"),
    [
        ("C:\\", "C:\\"),
        ("\\\\scanner-host\\shared results", "shared results"),
        ("C:/Scan Results/active batch", "active batch"),
        ('"C:\\Scan Results\\active batch"', "active batch"),
        ("/var/scan results/active batch", "active batch"),
    ],
)
def test_notify_redacts_root_quoted_forward_slash_and_posix_paths(path: str, tail: str) -> None:
    class Toast:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show(self, message: str, tone: str) -> None:
            self.messages.append((message, tone))

    window = object.__new__(Scanner3DWindow)
    window.toast = Toast()

    window.notify(f"Không thể mở ({path})", "error")

    message, tone = window.toast.messages[0]
    assert path not in message
    assert tail not in message
    assert "Không thể mở" in message
    assert tone == "error"


@pytest.mark.parametrize(
    ("path", "fragments"),
    [
        ("C:/Forward Results/active batch", ("Results", "batch")),
        ("/var/posix results/active batch", ("results", "batch")),
    ],
)
def test_notify_redacts_entire_forward_slash_and_posix_paths(path: str, fragments: tuple[str, str]) -> None:
    class Toast:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def show(self, message: str, tone: str) -> None:
            self.messages.append((message, tone))

    window = object.__new__(Scanner3DWindow)
    window.toast = Toast()

    window.notify(f"Không thể mở ({path}); vui lòng thử lại", "error")

    message, _tone = window.toast.messages[0]
    assert path not in message
    assert all(fragment not in message for fragment in fragments)
    assert "Không thể mở" in message
    assert "vui lòng thử lại" in message


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


def test_launch_reports_preflight_error_after_refresh() -> None:
    class FailingController:
        def apply_and_launch(self):
            raise RuntimeError("No Orbbec camera found")

    window = object.__new__(Scanner3DWindow)
    window.controller = FailingController()
    notifications: list[tuple[str, str]] = []
    window.refresh = lambda: None
    window.notify = lambda message, tone="info": notifications.append((message, tone))

    window.launch()

    assert notifications == [("No Orbbec camera found", "error")]


def test_launch_resets_monitor_and_arms_database_probe_after_success(monkeypatch) -> None:
    class Controller:
        def apply_and_launch(self) -> RuntimeStatus:
            return RuntimeStatus(True, "RTAB-Map started")

    calls: list[str] = []
    window = object.__new__(Scanner3DWindow)
    window.controller = Controller()
    window.monitor = type("Monitor", (), {"reset": lambda self: calls.append("reset")})()
    window.probe = type(
        "Probe", (), {"start": lambda self, started_at: calls.append(f"start:{started_at}")}
    )()
    window.refresh = lambda: calls.append("refresh")
    window.notify = lambda _message, _tone="info": None
    monkeypatch.setattr(scanner_window_module.time, "time", lambda: 100.0)

    window.launch()

    assert calls == ["reset", "start:100.0", "refresh"]


def test_new_scan_page_labels_the_auto_pause_switch_with_its_reason(monkeypatch) -> None:
    widget_texts: list[str] = []
    switch_texts: list[str] = []

    class Widget:
        def __init__(self, _parent=None, **kwargs) -> None:
            if "text" in kwargs:
                widget_texts.append(kwargs["text"])

        def configure(self, **_kwargs) -> None:
            pass

        def pack(self, **_kwargs) -> None:
            pass

        def pack_forget(self) -> None:
            pass

    class Switch(Widget):
        def __init__(self, parent=None, **kwargs) -> None:
            switch_texts.append(kwargs["text"])
            super().__init__(parent, **kwargs)

    monkeypatch.setattr(scanner_window_module.ctk, "CTkFrame", Widget)
    monkeypatch.setattr(scanner_window_module.ctk, "CTkLabel", Widget)
    monkeypatch.setattr(scanner_window_module.ctk, "CTkButton", Widget)
    monkeypatch.setattr(scanner_window_module.ctk, "CTkCheckBox", Widget)
    monkeypatch.setattr(scanner_window_module.ctk, "CTkSwitch", Switch)
    monkeypatch.setattr(scanner_window_module, "card", lambda parent: Widget(parent))
    monkeypatch.setattr(scanner_window_module.tk, "StringVar", lambda value=None: object())

    window = object.__new__(Scanner3DWindow)
    window.auto_enabled = object()
    window.auto_status = object()

    window._build_new_scan_page(Widget())

    assert "Tự dừng" in widget_texts
    assert "Tạm dừng khi bản đồ không có điểm mới" in widget_texts
    assert switch_texts == ["Bật"]


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


def test_runtime_poll_refreshes_once_when_rtabmap_starts() -> None:
    class Controller:
        def runtime_running(self) -> bool:
            return True

    class Root:
        def after(self, delay: int, callback) -> None:
            assert delay == 500
            self.callback = callback

    window = object.__new__(Scanner3DWindow)
    window.controller = Controller()
    window.root = Root()
    window.runtime_was_running = False
    refresh_calls: list[None] = []
    window.refresh = lambda: refresh_calls.append(None)

    window._poll_runtime()

    assert refresh_calls == [None]
    assert window.runtime_was_running is True


def test_refresh_configures_the_runtime_status_chip() -> None:
    class Value:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class Chip:
        def __init__(self) -> None:
            self.options: dict[str, str] = {}

        def configure(self, **kwargs: str) -> None:
            self.options = kwargs

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
    window = object.__new__(Scanner3DWindow)
    window.controller = type("Controller", (), {"refresh": lambda self: dashboard})()
    window.status = Value()
    window.status_chip = Chip()
    window.auto_status = Value()
    window._render_camera_dashboard = lambda _dashboard: None
    window._refresh_session_cards = lambda: None
    window.refresh_crop_outputs = lambda: None
    window._refresh_new_scan = lambda _dashboard: None

    window.refresh()

    assert window.status.value == "Sẵn sàng chuẩn bị"
    assert window.status_chip.options == {
        "text": "Sẵn sàng chuẩn bị",
        "fg_color": "#E8EEF7",
        "text_color": "#1E3A5F",
    }


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

    window = object.__new__(Scanner3DWindow)
    window.refresh_crop_outputs = lambda select_path: selected.append(select_path)
    notifications: list[tuple[str, str]] = []
    window.notify = lambda message, tone="info": notifications.append((message, tone))
    result = CropResult(
        tmp_path / "crop",
        tmp_path / "crop" / "model_cropped.obj",
        tmp_path / "crop" / "viewer" / "model_cropped.glb",
    )

    window._record_crop_result(result)

    assert selected == [result.viewer_model]
    assert notifications == [("Đã tạo mô hình đã cắt", "success")]


def test_crop_worker_reports_unexpected_processing_errors(monkeypatch, tmp_path: Path) -> None:
    class Root:
        def after(self, _delay: int, callback, *args) -> None:
            callback(*args)

    notifications: list[tuple[str, str]] = []
    window = object.__new__(Scanner3DWindow)
    window.root = Root()
    window.notify = lambda message, tone="info": notifications.append((message, tone))
    monkeypatch.setattr(scanner_window_module, "crop_obj_bundle", lambda *_args: (_ for _ in ()).throw(IndexError("bad mesh")))

    window._crop_worker(tmp_path / "source.obj", CropRectangle(0, 0, 1, 1), object(), tmp_path / "output")

    assert notifications == [("Không thể tạo mô hình đã cắt: bad mesh", "error")]


def test_record_export_result_enables_opening_the_viewer_model(tmp_path: Path) -> None:
    rendered: list[None] = []

    viewer_model = tmp_path / "viewer" / "scan.glb"
    result = ExportResult(tmp_path, tmp_path / "raw.obj", tmp_path / "raw.mtl", (), viewer_model, tmp_path / "log", None)
    window = object.__new__(Scanner3DWindow)
    window._render_crop_detail = lambda: rendered.append(None)
    window.latest_export_model = None
    notifications: list[tuple[str, str]] = []
    window.notify = lambda message, tone="info": notifications.append((message, tone))

    window._record_export_result(result)

    assert window.latest_export_model == viewer_model
    assert rendered == [None]
    assert notifications == [("Đã xuất mô hình để xem 3D", "success")]


def test_export_worker_schedules_an_error_toast_for_operational_failures(tmp_path: Path) -> None:
    class Root:
        def __init__(self) -> None:
            self.scheduled: list[tuple[int, object, tuple[object, ...]]] = []

        def after(self, delay: int, callback, *args) -> None:
            self.scheduled.append((delay, callback, args))
            callback(*args)

    class Exporter:
        def export(self, _request) -> None:
            raise FileExistsError("output exists")

    notifications: list[tuple[str, str]] = []
    window = object.__new__(Scanner3DWindow)
    window.root = Root()
    window.exporter = Exporter()
    window.output_root = tmp_path / "output"
    window.notify = lambda message, tone="info": notifications.append((message, tone))
    session = SavedSession(tmp_path / "scan.db", 1, modified_at=None)  # type: ignore[arg-type]

    window._export_worker(session)

    assert window.root.scheduled[0][0] == 0
    assert notifications == [("Không thể xuất mô hình 3D: output exists", "error")]


def test_open_latest_exported_model_uses_the_recent_viewer_model(tmp_path: Path) -> None:
    opened: list[Path] = []

    class OpenActions:
        def open_obj(self, path: Path) -> OpenActionResult:
            opened.append(path)
            return OpenActionResult(True, "Đã mở mô hình 3D")

    viewer_model = tmp_path / "viewer" / "scan.glb"
    window = object.__new__(Scanner3DWindow)
    window.latest_export_model = viewer_model
    window.open_actions = OpenActions()
    notifications: list[tuple[str, str]] = []
    window.notify = lambda message, tone="info": notifications.append((message, tone))

    window.open_latest_exported_model()

    assert opened == [viewer_model]
    assert notifications == [("Đã mở mô hình 3D", "success")]


def test_crop_preview_uses_less_detail_while_rotating() -> None:
    moving, settled = crop_preview_limits()

    assert moving < settled
    assert moving == 700


def test_crop_view_presets_define_full_orbit_angles() -> None:
    assert crop_view_preset("front") == (-math.pi / 2.0, 0.0)
    assert crop_view_preset("back") == (math.pi / 2.0, 0.0)
    assert crop_view_preset("top") == (0.0, math.pi / 2.0)
    assert crop_view_preset("bottom") == (0.0, -math.pi / 2.0)
