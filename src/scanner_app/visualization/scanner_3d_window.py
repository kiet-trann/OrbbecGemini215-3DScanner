"""Desktop control window for the external RTAB-Map scanning workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Sequence

import customtkinter as ctk

from scanner_app.rtabmap.activity import ActivityMonitor, AutoPauseState, SqliteNodeCountProbe
from scanner_app.rtabmap.catalog import SessionCatalog
from scanner_app.rtabmap.exporter import ExportRequest, ExportService
from scanner_app.rtabmap.models import RuntimeStatus, SavedSession
from scanner_app.rtabmap.obj_crop import (
    CropRectangle, CropResult, crop_obj_bundle, perspective_projection_for_bounds,
    preview_stride, sample_visible_projected_vertices,
)
from scanner_app.rtabmap.runtime import RtabmapRuntime
from scanner_app.rtabmap.windows_bridge import BridgeResult, WindowsRtabmapBridge
from scanner_app.camera.models import CameraProfile, CameraSettingsSnapshot, CaptureConfig
from scanner_app.camera.preflight import CameraPreflight, CameraPreflightError
from scanner_app.visualization.crop_catalog import CroppedObjCatalog, CroppedObjOutput
from scanner_app.visualization.dashboard_theme import (
    NAVY,
    PRIMARY,
    SURFACE,
    card,
    configure_dashboard_theme,
    configure_treeview_style,
    dashboard_status,
)
from scanner_app.visualization.guided_workflow import GuidedMode, GuidedWorkflow, guided_workflow
from scanner_app.visualization.navigation import (
    DashboardPage,
    default_page,
    is_navigable,
    navigation_items,
)
from scanner_app.visualization.open_actions import OpenActionService


@dataclass(frozen=True)
class DashboardState:
    runtime_message: str
    auto_pause_available: bool
    auto_pause_message: str
    sessions: tuple[SavedSession, ...]
    busy: bool
    camera_profile: CameraProfile
    camera_snapshot: CameraSettingsSnapshot | None
    camera_controls_locked: bool


@dataclass(frozen=True)
class CardMetadata:
    title: str
    subtitle: str
    detail: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CameraProfileCard:
    profile: CameraProfile
    label: str
    range_label: str
    selected: bool


@dataclass(frozen=True)
class CameraDeviceCard:
    title: str
    subtitle: str
    inspection_label: str


@dataclass(frozen=True)
class CameraFactGroup:
    title: str
    subtitle: str
    facts: tuple[tuple[str, str], ...]


def camera_control_state(locked: bool) -> str:
    return tk.DISABLED if locked else tk.NORMAL


def camera_dashboard_cards(
    profile: CameraProfile, snapshot: CameraSettingsSnapshot | None
) -> tuple[tuple[CameraProfileCard, ...], CameraDeviceCard, tuple[CameraFactGroup, ...]]:
    profiles = tuple(
        CameraProfileCard(
            candidate,
            candidate.display_name,
            f"{candidate.distance_range_m[0]:.2f}–{candidate.distance_range_m[1]:.2f} m".replace(".", ","),
            candidate is profile,
        )
        for candidate in CameraProfile
    )
    if snapshot is None:
        device = CameraDeviceCard(
            "Chưa kiểm tra thiết bị",
            "Chưa có serial hoặc firmware",
            "Kiểm tra thiết bị để xác nhận mode và căn chỉnh.",
        )
        config = CaptureConfig()
        filters = "Chưa kiểm tra"
        alignment = "Chưa kiểm tra"
    else:
        device = CameraDeviceCard(
            snapshot.device_name,
            f"{snapshot.serial_number} · Firmware {snapshot.firmware_version}",
            f"{snapshot.confirmed_mode} · căn chỉnh {snapshot.alignment_target}",
        )
        config = snapshot.capture_config
        filters = "; ".join(snapshot.enabled_depth_filters) or "None"
        alignment = snapshot.alignment_target
    groups = (
        CameraFactGroup(
            "Thông số luồng",
            "Depth & Color",
            (
                ("Depth stream", f"{config.depth_width}×{config.depth_height} {config.depth_format} @ {config.depth_fps} FPS"),
                ("Color stream", f"{config.color_width}×{config.color_height} {config.color_format} @ {config.color_fps} FPS"),
                ("IMU", f"{config.imu_hz} Hz"),
            ),
        ),
        CameraFactGroup(
            "Khoảng cách & bộ lọc",
            "Depth range & filters",
            (
                ("Depth range", f"{config.depth_min_m:.2f}–{config.depth_max_m:.2f} m"),
                ("Normal scan range", f"{config.normal_scan_min_m:.2f}–{config.normal_scan_max_m:.2f} m"),
                ("Enabled depth filters", filters),
                ("Alignment target", alignment),
            ),
        ),
    )
    return profiles, device, groups


def display_size(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f}".replace(".", ",") + " MB"


def display_timestamp(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y · %H:%M") if value is not None else "Chưa có thời gian"


def session_card_metadata(session: SavedSession) -> CardMetadata:
    size = display_size(session.size_bytes)
    updated = display_timestamp(session.modified_at)
    return CardMetadata(
        session.path.name,
        f"{updated} · {size}",
        (("Dung lượng", size), ("Cập nhật", updated)),
    )


def crop_card_metadata(output: CroppedObjOutput) -> CardMetadata:
    size = display_size(output.size_bytes)
    updated = display_timestamp(output.modified_at)
    folder = output.output_dir.name
    return CardMetadata(
        output.path.name,
        f"{folder} · {updated} · {size}",
        (("Thư mục", folder), ("Dung lượng", size), ("Cập nhật", updated)),
    )


def preserved_selection(items: Sequence[Path], selected: Path | None) -> Path | None:
    return selected if selected in items else None


def build_summary_cards(
    profile: CameraProfile, sessions: list[SavedSession], latest_export_model: Path | None
) -> tuple[tuple[str, str, DashboardPage], ...]:
    count = len(sessions)
    session_copy = f"{count} phiên đã lưu" if count else "Chưa bắt đầu"
    result_copy = latest_export_model.name if latest_export_model is not None else "Chưa có mô hình"
    return (
        ("01 · CAMERA", profile.display_name, DashboardPage.CAMERA),
        ("02 · PHIÊN QUÉT", session_copy, DashboardPage.RESULTS),
        ("03 · KẾT QUẢ", result_copy, DashboardPage.RESULTS),
    )


def camera_settings_rows(
    profile: CameraProfile, snapshot: CameraSettingsSnapshot | None
) -> tuple[tuple[str, str], ...]:
    config = snapshot.capture_config if snapshot is not None else CaptureConfig()
    preflight_state = snapshot.preflight_state if snapshot is not None else "Not applied"
    mode = snapshot.confirmed_mode if snapshot is not None else "Unavailable until inspection"
    supported_modes = "; ".join(snapshot.supported_modes) if snapshot is not None else "Unavailable"
    device_name = snapshot.device_name if snapshot is not None else "Unavailable until inspection"
    serial = snapshot.serial_number if snapshot is not None else "Unavailable until inspection"
    firmware = snapshot.firmware_version if snapshot is not None else "Unavailable until inspection"
    alignment = snapshot.alignment_target if snapshot is not None else "Unavailable until inspection"
    filters = "; ".join(snapshot.enabled_depth_filters) if snapshot is not None else "Unavailable"
    return (
        ("Profile", profile.display_name),
        ("Profile range", f"{profile.distance_range_m[0]:.2f}-{profile.distance_range_m[1]:.2f} m"),
        ("Preflight", preflight_state),
        ("Depth work mode", mode or "Unavailable"),
        ("Supported depth modes", supported_modes or "Unavailable"),
        ("Device", device_name or "Unavailable"),
        ("Serial number", serial or "Unavailable"),
        ("Firmware", firmware or "Unavailable"),
        ("Depth stream", f"{config.depth_width}x{config.depth_height} {config.depth_format} @ {config.depth_fps} FPS"),
        ("Color stream", f"{config.color_width}x{config.color_height} {config.color_format} @ {config.color_fps} FPS"),
        ("Depth range", f"{config.depth_min_m:.2f}-{config.depth_max_m:.2f} m"),
        ("Normal scan range", f"{config.normal_scan_min_m:.2f}-{config.normal_scan_max_m:.2f} m"),
        ("Alignment target", alignment),
        ("IMU", f"{config.imu_hz} Hz"),
        ("Enabled depth filters", filters or "None"),
    )


@dataclass(frozen=True)
class CropPreviewLayout:
    view_title: str
    crop_title: str
    view_instructions: str
    crop_instructions: str


def crop_preview_layout() -> CropPreviewLayout:
    return CropPreviewLayout(
        view_title="Xem mô hình 3D",
        crop_title="Vùng cắt",
        view_instructions="Kéo chuột phải để xoay - lăn chuột để phóng to",
        crop_instructions="Kéo chuột trái một khung quanh phần cần giữ lại",
    )


def crop_preview_limits() -> tuple[int, int]:
    return 700, 2_800


def crop_view_preset(name: str) -> tuple[float, float]:
    return {
        "reset": (0.65, -0.25),
        "front": (-math.pi / 2.0, 0.0),
        "back": (math.pi / 2.0, 0.0),
        "top": (0.0, math.pi / 2.0),
        "bottom": (0.0, -math.pi / 2.0),
    }[name]


class Scanner3DController:
    def __init__(self, *, runtime, bridge, monitor, catalog, preflight=None) -> None:
        self._runtime = runtime
        self._bridge = bridge
        self._monitor = monitor
        self._catalog = catalog
        self._preflight = preflight
        self._camera_profile = CameraProfile.NEAR
        self._camera_snapshot: CameraSettingsSnapshot | None = None
        self._busy = False

    def refresh(self) -> DashboardState:
        state = self._monitor.state
        if state is AutoPauseState.UNCERTAIN:
            message = "Tự dừng không khả dụng: tín hiệu hoạt động không chắc chắn"
            available = False
        elif state is AutoPauseState.PAUSED:
            message = "Tự dừng đã tạm dừng RTAB-Map; hãy kiểm tra mô hình"
            available = True
        else:
            message = "Tự dừng sẵn sàng (thử nghiệm)"
            available = True
        runtime_status = self._runtime.status()
        return DashboardState(
            runtime_status.message,
            available,
            message,
            tuple(self._catalog.refresh()),
            self._busy,
            self._camera_profile,
            self._camera_snapshot,
            runtime_status.running,
        )

    def launch(self) -> RuntimeStatus:
        return self.apply_and_launch()

    def runtime_running(self) -> bool:
        return self._runtime.status().running

    def set_camera_profile(self, profile: CameraProfile) -> None:
        self._assert_camera_controls_unlocked()
        self._camera_profile = profile
        self._camera_snapshot = None

    def inspect_camera(self) -> CameraSettingsSnapshot:
        self._assert_camera_controls_unlocked()
        self._camera_snapshot = self._preflight_service().inspect(self._camera_profile)
        return self._camera_snapshot

    def apply_and_launch(self) -> RuntimeStatus:
        self._assert_camera_controls_unlocked()
        self._camera_snapshot = self._preflight_service().apply(self._camera_profile)
        return self._runtime.launch()

    def _preflight_service(self):
        if self._preflight is None:
            raise RuntimeError("Camera preflight is unavailable.")
        return self._preflight

    def _assert_camera_controls_unlocked(self) -> None:
        if self._runtime.status().running:
            raise RuntimeError("Camera profile is locked while RTAB-Map is running.")

    def request_pause(self) -> BridgeResult:
        return self._bridge.pause()

    def request_resume(self) -> BridgeResult:
        result = self._bridge.resume()
        if result.sent and hasattr(self._monitor, "resume"):
            self._monitor.resume(time.monotonic())
        return result


class Scanner3DWindow:
    def __init__(self, root: tk.Tk, *, controller: Scanner3DController, monitor: ActivityMonitor,
                 probe: SqliteNodeCountProbe, catalog: SessionCatalog, exporter: ExportService, output_root: Path) -> None:
        self.root, self.controller, self.monitor, self.probe = root, controller, monitor, probe
        self.catalog, self.exporter, self.output_root = catalog, exporter, output_root
        self.auto_enabled = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Sẵn sàng")
        self.auto_status = tk.StringVar(value="Tự dừng đang tắt")
        self.camera_profile_value = tk.StringVar(value=CameraProfile.NEAR.display_name)
        self.sessions: list[SavedSession] = []
        self.selected_session_path: Path | None = None
        self.crop_catalog = CroppedObjCatalog(output_root)
        self.cropped_outputs: list[CroppedObjOutput] = []
        self.selected_crop_path: Path | None = None
        self.open_actions = OpenActionService()
        self.latest_export_model: Path | None = None
        self.runtime_was_running = False
        self.active_page = default_page()
        self.page_frames: dict[DashboardPage, ttk.Frame] = {}
        self.sidebar_buttons: dict[DashboardPage, ttk.Button] = {}
        root.title("Quét 3D")
        root.geometry("1080x780")
        root.minsize(860, 640)
        self._build()
        self.refresh()
        self._poll_auto_pause()
        self._poll_runtime()

    def _build(self) -> None:
        configure_dashboard_theme(self.root)
        configure_treeview_style(self.root)
        self._configure_styles()
        shell = ctk.CTkFrame(self.root, fg_color=SURFACE, corner_radius=0)
        shell.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(shell, width=220, fg_color=NAVY, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        content = ctk.CTkFrame(shell, fg_color=SURFACE, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew")
        header = ctk.CTkFrame(content, fg_color="transparent", corner_radius=0)
        header.pack(fill=tk.X, padx=28, pady=(22, 8))
        title_box = ctk.CTkFrame(header, fg_color="transparent", corner_radius=0)
        title_box.pack(side=tk.LEFT)
        ctk.CTkLabel(title_box, text="QUÉT 3D", font=("Segoe UI", 11, "bold"), text_color="#64748B").pack(anchor=tk.W)
        self.page_title = tk.StringVar(value="Quét mới")
        ctk.CTkLabel(title_box, textvariable=self.page_title, font=("Segoe UI", 24, "bold"), text_color="#0F172A").pack(anchor=tk.W)
        self.status_chip = ctk.CTkLabel(header, textvariable=self.status, corner_radius=14, fg_color="#E8EEF7", text_color="#1E3A5F", padx=12, pady=6, font=("Segoe UI", 12))
        self.status_chip.pack(side=tk.RIGHT, pady=(10, 0))
        self.page_host = ctk.CTkScrollableFrame(content, fg_color=SURFACE, corner_radius=0)
        self.page_host.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 22))
        self.page_host.columnconfigure(0, weight=1)
        self.page_host.rowconfigure(0, weight=1)
        self._build_sidebar(sidebar)
        self._build_new_scan_page(self._new_page_frame(DashboardPage.NEW_SCAN))
        self._build_camera_page(self._new_page_frame(DashboardPage.CAMERA))
        self._build_results_page(self._new_page_frame(DashboardPage.RESULTS))
        self._build_advanced_page(self._new_page_frame(DashboardPage.ADVANCED))
        self.show_page(self.active_page)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Sidebar.TFrame", background="#173f5f")
        style.configure("Sidebar.TButton", anchor=tk.W, padding=(12, 8))
        style.configure("Sidebar.Active.TButton", anchor=tk.W, padding=(12, 8), font=("Segoe UI", 10, "bold"))
        style.configure("Dashboard.Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Guided.Primary.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"))

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ctk.CTkLabel(parent, text="3D Scanner", text_color="white", font=("Segoe UI", 18, "bold")).pack(anchor=tk.W, padx=22, pady=(28, 28))
        group: str | None = None
        for item in navigation_items():
            if item.group != group:
                group = item.group
                ctk.CTkLabel(parent, text=group.upper(), text_color="#A7B9CA", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=22, pady=(0, 8))
            button = ctk.CTkButton(
                parent,
                text=item.title,
                anchor="w",
                height=40,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#244C70",
                text_color="white",
                command=lambda page=item.page: self.show_page(page),
                state=tk.NORMAL if item.enabled else tk.DISABLED,
            )
            button.pack(fill=tk.X, padx=12, pady=3)
            self.sidebar_buttons[item.page] = button

    def _new_page_frame(self, page: DashboardPage) -> ttk.Frame:
        frame = ttk.Frame(self.page_host, padding=4)
        frame.columnconfigure(0, weight=1)
        self.page_frames[page] = frame
        return frame

    def show_page(self, page: DashboardPage) -> None:
        if not is_navigable(page):
            return
        for current, frame in self.page_frames.items():
            frame.grid_remove()
            if current is not page and current in self.sidebar_buttons:
                self.sidebar_buttons[current].configure(fg_color="transparent")
        self.page_frames[page].grid(row=0, column=0, sticky="nsew")
        if page in self.sidebar_buttons:
            self.sidebar_buttons[page].configure(fg_color=PRIMARY)
        self.active_page = page
        if hasattr(self, "page_title"):
            self.page_title.set(next(item.title for item in navigation_items() if item.page is page))

    def _build_new_scan_page(self, parent: ttk.Frame) -> None:
        parent.configure(style="Dashboard.TFrame")
        ctk.CTkLabel(parent, text="Sẵn sàng tạo mô hình", font=("Segoe UI", 14), text_color="#64748B").pack(anchor=tk.W, pady=(0, 14))
        workflow = card(parent)
        workflow.pack(fill=tk.X, pady=(0, 14))
        self.new_scan_heading = tk.StringVar(value="Bước 1 / 3 · Chuẩn bị camera")
        self.new_scan_detail = tk.StringVar(value="Kiểm tra camera trước khi bắt đầu.")
        ctk.CTkLabel(workflow, textvariable=self.new_scan_heading, font=("Segoe UI", 18, "bold"), text_color="#0F172A").pack(anchor=tk.W, padx=20, pady=(18, 0))
        ctk.CTkLabel(workflow, textvariable=self.new_scan_detail, font=("Segoe UI", 13), text_color="#64748B", wraplength=600, justify="left").pack(anchor=tk.W, padx=20, pady=(5, 14))
        self.new_scan_primary_button = ctk.CTkButton(workflow, text="Kiểm tra camera", fg_color=PRIMARY, hover_color="#1D4ED8", height=40, corner_radius=8)
        self.new_scan_primary_button.pack(anchor=tk.W, padx=20, pady=(0, 18))
        self.new_scan_results_button = ctk.CTkButton(
            workflow, command=lambda: self.show_page(DashboardPage.RESULTS)
        )
        self.new_scan_results_button.pack_forget()
        cards = ctk.CTkFrame(parent, fg_color="transparent")
        cards.pack(fill=tk.X)
        for title, value, page in build_summary_cards(CameraProfile.NEAR, [], None):
            item = card(cards)
            item.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
            ctk.CTkLabel(item, text=title, font=("Segoe UI", 10, "bold"), text_color="#64748B").pack(anchor=tk.W, padx=16, pady=(14, 5))
            ctk.CTkButton(item, text=value, fg_color="transparent", hover_color="#EEF3F8", text_color="#0F172A", anchor="w", command=lambda route=page: self.show_page(route)).pack(fill=tk.X, padx=8, pady=(0, 10))

    def _build_camera_page(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Thiết lập camera", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
        camera_setup = ttk.LabelFrame(parent, text="Cấu hình quét", padding=14, style="Dashboard.TLabelframe")
        camera_setup.pack(fill=tk.X, pady=(8, 10))
        profile_controls = ttk.Frame(camera_setup)
        profile_controls.pack(fill=tk.X)
        ttk.Label(profile_controls, text="Cấu hình:").pack(side=tk.LEFT)
        self.camera_profile_combo = ttk.Combobox(
            profile_controls,
            textvariable=self.camera_profile_value,
            values=tuple(profile.display_name for profile in CameraProfile),
            state="readonly",
            width=28,
        )
        self.camera_profile_combo.pack(side=tk.LEFT, padx=(6, 8))
        self.camera_profile_combo.bind("<<ComboboxSelected>>", self._select_camera_profile)
        self.inspect_camera_button = ttk.Button(
            profile_controls, text="Kiểm tra thiết bị", command=self.inspect_camera
        )
        self.inspect_camera_button.pack(side=tk.LEFT, padx=(0, 6))
        self.apply_camera_button = ttk.Button(
            profile_controls, text="Áp dụng & mở RTAB-Map", command=self.launch
        )
        self.apply_camera_button.pack(side=tk.LEFT)
        self.camera_settings_tree = ttk.Treeview(
            camera_setup, columns=("value",), show="tree headings", height=8, style="Dashboard.Treeview"
        )
        self.camera_settings_tree.heading("#0", text="Thông số")
        self.camera_settings_tree.heading("value", text="Giá trị hiện tại")
        self.camera_settings_tree.column("#0", width=190)
        self.camera_settings_tree.column("value", width=510)
        self.camera_settings_tree.pack(fill=tk.X, pady=(8, 0))

    def _build_advanced_page(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Công cụ nâng cao", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
        ttk.Label(parent, text="Các điều khiển kỹ thuật dành cho lúc bạn cần can thiệp vào phiên quét.").pack(
            anchor=tk.W, pady=(2, 12)
        )
        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Tạm dừng", command=lambda: self._bridge_action(self.controller.request_pause)).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Tiếp tục", command=lambda: self._bridge_action(self.controller.request_resume)).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(controls, text="Tự dừng (thử nghiệm)", variable=self.auto_enabled,
                        command=self._toggle_auto_pause).pack(side=tk.RIGHT)
        ttk.Label(parent, textvariable=self.auto_status).pack(anchor=tk.W, pady=(10, 6))

    def _build_results_page(self, parent: ttk.Frame) -> None:
        ctk.CTkLabel(parent, text="Phiên quét & kết quả", font=("Segoe UI", 18, "bold"), text_color="#0F172A").pack(anchor=tk.W)
        ctk.CTkLabel(
            parent,
            text="Chọn một mục để xem chi tiết và thực hiện thao tác phù hợp.",
            font=("Segoe UI", 13),
            text_color="#64748B",
        ).pack(anchor=tk.W, pady=(3, 14))

        sessions = card(parent)
        sessions.pack(fill=tk.X, pady=(0, 14))
        session_header = ctk.CTkFrame(sessions, fg_color="transparent")
        session_header.pack(fill=tk.X, padx=18, pady=(16, 8))
        ctk.CTkLabel(session_header, text="PHIÊN QUÉT ĐÃ LƯU", font=("Segoe UI", 11, "bold"), text_color="#64748B").pack(side=tk.LEFT)
        self.session_count = tk.StringVar(value="0 phiên")
        ctk.CTkLabel(session_header, textvariable=self.session_count, corner_radius=10, fg_color="#EEF3F8", text_color="#475569", padx=9, pady=3, font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkButton(session_header, text="Làm mới", command=self.refresh, width=84, height=32, corner_radius=8, fg_color="#EAF1FF", hover_color="#DCE8FF", text_color=PRIMARY).pack(side=tk.RIGHT)
        self.session_list = ctk.CTkFrame(sessions, fg_color="transparent")
        self.session_list.pack(fill=tk.X, padx=12)
        self.session_detail = ctk.CTkFrame(sessions, fg_color="transparent")
        self.session_detail.pack(fill=tk.X, padx=12, pady=(8, 14))

        crops = card(parent)
        crops.pack(fill=tk.X)
        crop_header = ctk.CTkFrame(crops, fg_color="transparent")
        crop_header.pack(fill=tk.X, padx=18, pady=(16, 8))
        ctk.CTkLabel(crop_header, text="MÔ HÌNH ĐÃ CẮT", font=("Segoe UI", 11, "bold"), text_color="#64748B").pack(side=tk.LEFT)
        self.crop_count = tk.StringVar(value="0 mô hình")
        ctk.CTkLabel(crop_header, textvariable=self.crop_count, corner_radius=10, fg_color="#EEF3F8", text_color="#475569", padx=9, pady=3, font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(8, 0))
        ctk.CTkButton(crop_header, text="Cắt OBJ gốc", command=self.choose_crop_source, width=112, height=32, corner_radius=8, fg_color=PRIMARY, hover_color="#1D4ED8").pack(side=tk.RIGHT)
        self.crop_list = ctk.CTkFrame(crops, fg_color="transparent")
        self.crop_list.pack(fill=tk.X, padx=12)
        self.crop_detail = ctk.CTkFrame(crops, fg_color="transparent")
        self.crop_detail.pack(fill=tk.X, padx=12, pady=(8, 14))

    def launch(self) -> None:
        try:
            message = self.controller.apply_and_launch().message
        except (CameraPreflightError, RuntimeError) as error:
            message = str(error)
        self.refresh()
        self.status.set(dashboard_status(message).label)

    def inspect_camera(self) -> None:
        try:
            self.controller.inspect_camera()
            message = "Đã kiểm tra thông số camera"
        except (CameraPreflightError, RuntimeError) as error:
            message = str(error)
        self.refresh()
        self.status.set(dashboard_status(message).label)

    def _select_camera_profile(self, _event=None) -> None:
        profile = next(
            candidate
            for candidate in CameraProfile
            if candidate.display_name == self.camera_profile_value.get()
        )
        try:
            self.controller.set_camera_profile(profile)
            message = f"Đã chọn cấu hình camera: {profile.display_name}"
        except RuntimeError as error:
            message = str(error)
        self.refresh()
        self.status.set(dashboard_status(message).label)

    def refresh(self) -> None:
        dashboard = self.controller.refresh()
        self.runtime_was_running = dashboard.camera_controls_locked
        status = dashboard_status(dashboard.runtime_message)
        self.status.set(status.label)
        self.status_chip.configure(
            text=status.label,
            fg_color={"ready": "#DCFCE7", "error": "#FEE2E2", "neutral": "#E8EEF7"}[status.tone],
            text_color={"ready": "#166534", "error": "#991B1B", "neutral": "#1E3A5F"}[status.tone],
        )
        self.auto_status.set(dashboard.auto_pause_message)
        self._refresh_camera_settings(dashboard)
        self.sessions = list(dashboard.sessions)
        self._refresh_session_cards()
        self.refresh_crop_outputs()
        self._refresh_new_scan(dashboard)

    def _refresh_new_scan(self, dashboard: DashboardState) -> None:
        workflow = guided_workflow(dashboard, has_sessions=bool(self.sessions))
        self._apply_guided_workflow(workflow, dashboard.runtime_message)

    def _apply_guided_workflow(self, workflow: GuidedWorkflow, runtime_message: str) -> None:
        if workflow.mode is GuidedMode.CHECK_CAMERA:
            heading = "Bước 1 / 3 · Chuẩn bị camera"
            detail = "Kiểm tra thiết bị và thông số camera trước khi bắt đầu quét."
            self.new_scan_primary_button.configure(text=workflow.primary_label, command=self.inspect_camera)
        elif workflow.mode is GuidedMode.START_SCAN:
            heading = "Bước 2 / 3 · Bắt đầu quét"
            detail = "Camera đã sẵn sàng. Áp dụng cấu hình để mở RTAB-Map và bắt đầu quét."
            self.new_scan_primary_button.configure(text=workflow.primary_label, command=self.launch)
        else:
            heading = "Đang quét"
            detail = f"{runtime_message}. Camera được khóa trong khi RTAB-Map đang chạy."
            self.new_scan_primary_button.configure(
                text=workflow.primary_label,
                command=lambda: self._bridge_action(self.controller.request_pause),
            )
        self.new_scan_heading.set(heading)
        self.new_scan_detail.set(detail)
        results_text = "Mở phiên & kết quả" if workflow.results_ready else "Chưa có phiên để xuất"
        self.new_scan_results_button.configure(text=results_text)

    def _refresh_camera_settings(self, dashboard: DashboardState) -> None:
        self.camera_profile_value.set(dashboard.camera_profile.display_name)
        self.camera_profile_combo.configure(
            state="disabled" if dashboard.camera_controls_locked else "readonly"
        )
        state = camera_control_state(dashboard.camera_controls_locked)
        self.inspect_camera_button.configure(state=state)
        self.apply_camera_button.configure(state=state)
        self.camera_settings_tree.delete(*self.camera_settings_tree.get_children())
        for index, (setting, value) in enumerate(
            camera_settings_rows(dashboard.camera_profile, dashboard.camera_snapshot)
        ):
            self.camera_settings_tree.insert("", tk.END, iid=str(index), text=setting, values=(value,))

    def refresh_crop_outputs(self, select_path: Path | None = None) -> None:
        self.cropped_outputs = self.crop_catalog.refresh()
        selected = select_path.resolve() if select_path is not None else self.selected_crop_path
        self.selected_crop_path = preserved_selection(
            [output.path.resolve() for output in self.cropped_outputs], selected
        )
        self._refresh_crop_cards()

    @staticmethod
    def _clear_children(parent) -> None:
        for child in parent.winfo_children():
            child.destroy()

    def _render_card(self, parent, metadata: CardMetadata, *, selected: bool, command) -> None:
        ctk.CTkButton(
            parent,
            text=f"{metadata.title}\n{metadata.subtitle}",
            command=command,
            anchor="w",
            height=52,
            corner_radius=9,
            border_width=1,
            border_color="#BFD3FF" if selected else "#DEE5ED",
            fg_color="#EAF1FF" if selected else "transparent",
            hover_color="#F1F5F9",
            text_color="#0F172A",
            font=("Segoe UI", 12, "bold"),
        ).pack(fill=tk.X, pady=4)

    def _render_empty_state(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 13), text_color="#64748B").pack(
            anchor=tk.W, padx=6, pady=(8, 12)
        )

    def _refresh_session_cards(self) -> None:
        self.selected_session_path = preserved_selection(
            [session.path.resolve() for session in self.sessions], self.selected_session_path
        )
        self.session_count.set(f"{len(self.sessions)} phiên")
        self._clear_children(self.session_list)
        if not self.sessions:
            self._render_empty_state(self.session_list, "Chưa có phiên quét đã lưu.")
        for session in self.sessions:
            path = session.path.resolve()
            self._render_card(
                self.session_list,
                session_card_metadata(session),
                selected=path == self.selected_session_path,
                command=lambda selected_path=path: self._select_session(selected_path),
            )
        self._render_session_detail()

    def _refresh_crop_cards(self) -> None:
        self.crop_count.set(f"{len(self.cropped_outputs)} mô hình")
        self._clear_children(self.crop_list)
        if not self.cropped_outputs:
            self._render_empty_state(self.crop_list, "Chưa có mô hình đã cắt.")
        for output in self.cropped_outputs:
            path = output.path.resolve()
            self._render_card(
                self.crop_list,
                crop_card_metadata(output),
                selected=path == self.selected_crop_path,
                command=lambda selected_path=path: self._select_crop(selected_path),
            )
        self._render_crop_detail()

    def _selected_session(self) -> SavedSession | None:
        return next(
            (session for session in self.sessions if session.path.resolve() == self.selected_session_path),
            None,
        )

    def _selected_crop_output(self) -> CroppedObjOutput | None:
        return next(
            (output for output in self.cropped_outputs if output.path.resolve() == self.selected_crop_path),
            None,
        )

    def _render_detail(self, parent, metadata: CardMetadata, *, primary_text: str, primary_command, secondary_text: str, secondary_command) -> None:
        self._clear_children(parent)
        panel = card(parent)
        panel.pack(fill=tk.X)
        ctk.CTkLabel(panel, text="ĐANG CHỌN", font=("Segoe UI", 10, "bold"), text_color="#2563EB").pack(anchor=tk.W, padx=14, pady=(12, 2))
        ctk.CTkLabel(panel, text=metadata.title, font=("Segoe UI", 14, "bold"), text_color="#0F172A").pack(anchor=tk.W, padx=14)
        facts = ctk.CTkFrame(panel, fg_color="transparent")
        facts.pack(fill=tk.X, padx=14, pady=(10, 8))
        for label, value in metadata.detail:
            fact = ctk.CTkFrame(facts, fg_color="#F7F9FC", corner_radius=8)
            fact.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
            ctk.CTkLabel(fact, text=label.upper(), font=("Segoe UI", 9, "bold"), text_color="#64748B").pack(anchor=tk.W, padx=9, pady=(7, 0))
            ctk.CTkLabel(fact, text=value, font=("Segoe UI", 11, "bold"), text_color="#0F172A").pack(anchor=tk.W, padx=9, pady=(1, 7))
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.pack(fill=tk.X, padx=14, pady=(0, 12))
        ctk.CTkButton(actions, text=primary_text, command=primary_command, height=34, corner_radius=8, fg_color=PRIMARY, hover_color="#1D4ED8").pack(side=tk.LEFT)
        ctk.CTkButton(actions, text=secondary_text, command=secondary_command, height=34, corner_radius=8, fg_color="#EAF1FF", hover_color="#DCE8FF", text_color=PRIMARY).pack(side=tk.LEFT, padx=8)

    def _render_session_detail(self) -> None:
        self._clear_children(self.session_detail)
        session = self._selected_session()
        if session is not None:
            self._render_detail(
                self.session_detail,
                session_card_metadata(session),
                primary_text="Xuất OBJ gốc",
                primary_command=self.export_selected,
                secondary_text="Mở thư mục",
                secondary_command=self.open_selected_session_folder,
            )

    def _render_crop_detail(self) -> None:
        self._clear_children(self.crop_detail)
        output = self._selected_crop_output()
        if output is not None:
            self._render_detail(
                self.crop_detail,
                crop_card_metadata(output),
                primary_text="Mở mô hình",
                primary_command=self.open_latest_cropped_obj,
                secondary_text="Mở thư mục",
                secondary_command=self.open_latest_output_folder,
            )
        elif self.latest_export_model is not None:
            ctk.CTkButton(
                self.crop_detail,
                text="Mở mô hình đã xuất gần đây",
                command=self.open_latest_exported_model,
                height=34,
                corner_radius=8,
                fg_color="#EAF1FF",
                hover_color="#DCE8FF",
                text_color=PRIMARY,
            ).pack(anchor=tk.W)

    def _select_session(self, path: Path) -> None:
        self.selected_session_path = path.resolve()
        self._refresh_session_cards()
        self._render_session_detail()

    def _select_crop(self, path: Path) -> None:
        self.selected_crop_path = path.resolve()
        self._refresh_crop_cards()
        self._render_crop_detail()

    def _toggle_auto_pause(self) -> None:
        if not self.auto_enabled.get():
            self.auto_status.set("Tự dừng đang tắt")
        else:
            self.auto_status.set("Tự dừng đang khởi tạo: chờ hoạt động từ RTAB-Map")

    def _poll_auto_pause(self) -> None:
        if self.auto_enabled.get():
            state = self.monitor.observe(self.probe.observe())
            self.auto_status.set({
                AutoPauseState.WARMING_UP: "Tự dừng đang khởi tạo: di chuyển camera để tạo điểm bản đồ",
                AutoPauseState.ACTIVE: "Tự dừng đã sẵn sàng: tạm dừng sau 3 giây không có điểm mới",
                AutoPauseState.COUNTDOWN: "Tự dừng đang đếm ngược",
                AutoPauseState.PAUSED: "Tự dừng đã tạm dừng RTAB-Map; hãy kiểm tra mô hình",
                AutoPauseState.UNCERTAIN: "Tự dừng không khả dụng: tín hiệu hoạt động không chắc chắn",
            }.get(state, "Tự dừng đang tắt"))
            if state is AutoPauseState.UNCERTAIN:
                self.auto_enabled.set(False)
        self.root.after(250, self._poll_auto_pause)

    def _bridge_action(self, action) -> None:
        result = action()
        self.status.set(dashboard_status(result.message).label)

    def _poll_runtime(self) -> None:
        running = self.controller.runtime_running()
        if self.runtime_was_running and not running:
            self.refresh()
        self.runtime_was_running = running
        self.root.after(500, self._poll_runtime)

    def export_selected(self) -> None:
        session = self._selected_session()
        if session is None:
            messagebox.showinfo("Quét 3D", "Hãy chọn phiên RTAB-Map đã lưu trước.")
            return
        self.status.set("Đang xuất OBJ có texture trong nền...")
        threading.Thread(target=self._export_worker, args=(session,), daemon=True).start()

    def _export_worker(self, session: SavedSession) -> None:
        result = self.exporter.export(ExportRequest(session.path, self.output_root))
        self.root.after(0, lambda: self._record_export_result(result))

    def _record_export_result(self, result) -> None:
        if result.error is None and result.viewer_model is not None:
            self.latest_export_model = result.viewer_model
            self._render_crop_detail()
        message = result.error or f"Exported for 3D Viewer: {result.viewer_model or result.obj}"
        self.status.set(message)

    def choose_crop_source(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Chọn OBJ gốc để cắt",
            initialdir=self.output_root,
            filetypes=[("Tệp Wavefront OBJ", "*.obj")],
        )
        if selected:
            self._show_crop_preview(Path(selected))

    def _show_crop_preview(self, source_obj: Path) -> None:
        vertices, faces = _read_obj_mesh(source_obj)
        if not vertices:
            messagebox.showerror("Máy quét 3D", "Tệp OBJ không có đỉnh hình học.")
            return
        width, height = 520, 430
        dialog = tk.Toplevel(self.root)
        layout = crop_preview_layout()
        dialog.title(f"Xem trước vùng cắt — {source_obj.name}")
        ttk.Label(dialog, text="Kéo chuột phải để xoay · lăn chuột để phóng to · kéo chuột trái để vẽ vùng cắt.").pack(padx=10, pady=(10, 4))
        ttk.Label(
            dialog,
            text="Dùng mô hình bên trái để chọn góc nhìn. Chỉ kéo khung ở vùng bên phải.",
        ).pack(padx=10, pady=(0, 4))
        panels = ttk.Frame(dialog)
        panels.pack(padx=10, pady=6)
        view_panel = ttk.LabelFrame(panels, text=layout.view_title)
        view_panel.pack(side=tk.LEFT, padx=(0, 6))
        crop_panel = ttk.LabelFrame(panels, text=layout.crop_title)
        crop_panel.pack(side=tk.LEFT)
        ttk.Label(view_panel, text=layout.view_instructions).pack(padx=6, pady=(5, 2))
        ttk.Label(crop_panel, text=layout.crop_instructions).pack(padx=6, pady=(5, 2))
        view_canvas = tk.Canvas(view_panel, width=width, height=height, background="#171717", cursor="fleur")
        view_canvas.pack(padx=6, pady=(0, 6))
        canvas = tk.Canvas(crop_panel, width=width, height=height, background="#171717", cursor="crosshair")
        canvas.pack(padx=6, pady=(0, 6))
        state: dict[str, float | int | None | object] = {"yaw": 0.65, "pitch": -0.25, "distance": 3.5,
                                                           "x": None, "y": None, "item": None,
                                                           "rotate_x": None, "rotate_y": None, "projection": None,
                                                           "scheduled": None}

        def render_3d(maximum_faces: int) -> None:
            projection = perspective_projection_for_bounds(
                vertices, viewport_width=width, viewport_height=height,
                yaw=float(state["yaw"]), pitch=float(state["pitch"]), distance=float(state["distance"]),
            )
            state["projection"] = projection
            view_canvas.delete("mesh")
            view_canvas.delete("kept")
            stride = preview_stride(len(faces), maximum_faces)
            for number, face in enumerate(faces[::stride]):
                points = [projection.project((*vertices[index - 1], 1.0)) for index in face]
                if all(point is not None for point in points):
                    flat = [coordinate for point in points for coordinate in point]
                    shade = 55 + (number % 4) * 12
                    color = f"#{15:02x}{shade:02x}{min(155, shade + 55):02x}"
                    view_canvas.create_polygon(*flat, fill=color, outline="#255a73", tags="mesh")

        def render_crop_plane() -> None:
            canvas.delete("mesh")
            projection = state["projection"]
            for x, y in sample_visible_projected_vertices(vertices, projection, maximum_items=10_000):
                canvas.create_line(x, y, x + 1, y, fill="#9ddcf5", tags="mesh")

        moving_limit, settled_limit = crop_preview_limits()
        render_3d(settled_limit)
        render_crop_plane()

        def show_kept_preview() -> None:
            view_canvas.delete("kept")
            if state["item"] is None:
                return
            x1, y1, x2, y2 = canvas.coords(state["item"])
            rectangle = CropRectangle(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            projection = state["projection"]
            stride = preview_stride(len(faces), settled_limit)
            for face in faces[::stride]:
                points = [projection.project((*vertices[index - 1], 1.0)) for index in face]
                if all(point is not None and rectangle.contains(*point) for point in points):
                    flat = [coordinate for point in points for coordinate in point]
                    view_canvas.create_polygon(*flat, fill="#ffc857", outline="#fff0bd", tags="kept")

        def start(event) -> None:
            canvas.delete("selection")
            state["x"], state["y"] = event.x, event.y
            state["item"] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline="#ffbf3f", width=2, tags="selection"
            )

        def drag(event) -> None:
            if state["item"] is not None:
                canvas.coords(state["item"], state["x"], state["y"], event.x, event.y)

        def crop_release(_event) -> None:
            show_kept_preview()

        def rotate_start(event) -> None:
            state["rotate_x"], state["rotate_y"] = event.x, event.y

        def rotate(event) -> None:
            if state["rotate_x"] is None:
                return
            state["yaw"] = (float(state["yaw"]) + (event.x - float(state["rotate_x"])) * 0.012) % (2.0 * math.pi)
            state["pitch"] = (float(state["pitch"]) + (event.y - float(state["rotate_y"])) * 0.012) % (2.0 * math.pi)
            state["rotate_x"], state["rotate_y"] = event.x, event.y
            canvas.delete("selection")
            state["item"] = None
            if state["scheduled"] is None:
                state["scheduled"] = dialog.after(33, moving_render)

        def moving_render() -> None:
            state["scheduled"] = None
            render_3d(moving_limit)

        def rotate_end(_event) -> None:
            state["rotate_x"] = None
            render_3d(settled_limit)
            render_crop_plane()

        def zoom(event) -> None:
            state["distance"] = max(2.2, min(8.0, float(state["distance"]) - event.delta / 1200.0))
            canvas.delete("selection")
            state["item"] = None
            render_3d(settled_limit)
            render_crop_plane()

        def apply_preset(name: str) -> None:
            state["yaw"], state["pitch"] = crop_view_preset(name)
            canvas.delete("selection")
            state["item"] = None
            render_3d(settled_limit)
            render_crop_plane()

        def create_crop() -> None:
            if state["item"] is None:
                messagebox.showinfo("Máy quét 3D", "Hãy kéo một khung quanh đối tượng trước.", parent=dialog)
                return
            x1, y1, x2, y2 = canvas.coords(state["item"])
            rectangle = CropRectangle(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            output_dir = source_obj.parent.parent / f"cropped_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.status.set("Đang tạo OBJ đã cắt trong nền...")
            threading.Thread(target=self._crop_worker, args=(source_obj, rectangle, state["projection"], output_dir), daemon=True).start()
            dialog.destroy()

        canvas.bind("<Button-1>", start)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", crop_release)
        view_canvas.bind("<Button-3>", rotate_start)
        view_canvas.bind("<B3-Motion>", rotate)
        view_canvas.bind("<ButtonRelease-3>", rotate_end)
        view_canvas.bind("<MouseWheel>", zoom)
        view_controls = ttk.Frame(dialog)
        view_controls.pack(pady=(0, 6))
        for name, label in (("reset", "Đặt lại"), ("front", "Trước"), ("back", "Sau"), ("top", "Trên"), ("bottom", "Dưới")):
            ttk.Button(view_controls, text=label, command=lambda value=name: apply_preset(value)).pack(side=tk.LEFT, padx=3)
        ttk.Button(dialog, text="Tạo OBJ đã cắt", command=create_crop).pack(pady=(0, 10))

    def _crop_worker(self, source: Path, rectangle: CropRectangle, projection, output_dir: Path) -> None:
        try:
            result = crop_obj_bundle(source, rectangle, projection, output_dir)
        except (OSError, ValueError) as error:
            self.root.after(0, self.status.set, f"Crop failed: {error}")
            return
        self.root.after(0, lambda: self._record_crop_result(result))

    def _record_crop_result(self, result: CropResult) -> None:
        self.refresh_crop_outputs(select_path=result.viewer_model)
        self.status.set(f"Cropped model: {result.viewer_model}")

    def open_latest_cropped_obj(self) -> None:
        output = self._selected_crop_output()
        if output is None:
            self.status.set("Hãy chọn mô hình đã cắt trước.")
            return
        self.status.set(self.open_actions.open_obj(output.path).message)

    def open_latest_exported_model(self) -> None:
        if self.latest_export_model is None:
            self.status.set("Export a model first")
            return
        self.status.set(self.open_actions.open_obj(self.latest_export_model).message)

    def open_latest_output_folder(self) -> None:
        output = self._selected_crop_output()
        if output is None:
            self.status.set("Hãy chọn mô hình đã cắt trước.")
            return
        self.status.set(self.open_actions.open_folder(output.path).message)

    def open_selected_session_folder(self) -> None:
        session = self._selected_session()
        if session is None:
            self.status.set("Hãy chọn phiên RTAB-Map đã lưu trước.")
            return
        self.status.set(self.open_actions.open_folder(session.path).message)


def _read_obj_mesh(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            values = line.split()
            vertices.append((float(values[1]), float(values[2]), float(values[3])))
        elif line.startswith("f "):
            faces.append(tuple(int(token.split("/")[0]) for token in line.split()[1:]))
    return vertices, faces


def main() -> int:
    project_root = Path(__file__).resolve().parents[3]
    rtabmap_root = project_root / "third_party" / "rtabmap" / "RTABMap-0.23.1-win64"
    session_dir = Path.home() / "Documents" / "RTAB-Map"
    runtime = RtabmapRuntime(RtabmapRuntime.discover(rtabmap_root))
    bridge = WindowsRtabmapBridge()
    monitor = ActivityMonitor(pause=bridge.pause)
    catalog = SessionCatalog(session_dir, project_root / "outputs" / "scanner_3d" / "catalog.json")
    controller = Scanner3DController(
        runtime=runtime, bridge=bridge, monitor=monitor, catalog=catalog, preflight=CameraPreflight()
    )
    root = ctk.CTk()
    Scanner3DWindow(root, controller=controller, monitor=monitor,
                         probe=SqliteNodeCountProbe(session_dir / "rtabmap.tmp.db"), catalog=catalog,
                         exporter=ExportService(exporter=runtime._paths.exporter),
                         output_root=project_root / "outputs" / "scanner_3d")
    root.mainloop()
    return 0
