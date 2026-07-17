"""Desktop control window for the external RTAB-Map scanning workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from scanner_app.rtabmap.activity import ActivityMonitor, AutoPauseState, SqliteNodeCountProbe
from scanner_app.rtabmap.catalog import SessionCatalog
from scanner_app.rtabmap.exporter import ExportRequest, ExportService
from scanner_app.rtabmap.models import RuntimeStatus, SavedSession
from scanner_app.rtabmap.runtime import RtabmapRuntime
from scanner_app.rtabmap.windows_bridge import BridgeResult, WindowsRtabmapBridge


@dataclass(frozen=True)
class DashboardState:
    runtime_message: str
    auto_pause_available: bool
    auto_pause_message: str
    sessions: tuple[SavedSession, ...]
    busy: bool


class scanner_3dController:
    def __init__(self, *, runtime, bridge, monitor, catalog) -> None:
        self._runtime = runtime
        self._bridge = bridge
        self._monitor = monitor
        self._catalog = catalog
        self._busy = False

    def refresh(self) -> DashboardState:
        state = self._monitor.state
        if state is AutoPauseState.UNCERTAIN:
            message = "Auto-pause unavailable: activity signal is uncertain"
            available = False
        elif state is AutoPauseState.PAUSED:
            message = "Auto-pause paused RTAB-Map; review the model"
            available = True
        else:
            message = "Auto-pause ready (experimental)"
            available = True
        return DashboardState(self._runtime.status().message, available, message, tuple(self._catalog.refresh()), self._busy)

    def launch(self) -> RuntimeStatus:
        return self._runtime.launch()

    def request_pause(self) -> BridgeResult:
        return self._bridge.pause()

    def request_resume(self) -> BridgeResult:
        result = self._bridge.resume()
        if result.sent and hasattr(self._monitor, "resume"):
            self._monitor.resume(time.monotonic())
        return result


class scanner_3dWindow:
    def __init__(self, root: tk.Tk, *, controller: scanner_3dController, monitor: ActivityMonitor,
                 probe: SqliteNodeCountProbe, catalog: SessionCatalog, exporter: ExportService, output_root: Path) -> None:
        self.root, self.controller, self.monitor, self.probe = root, controller, monitor, probe
        self.catalog, self.exporter, self.output_root = catalog, exporter, output_root
        self.auto_enabled = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready")
        self.auto_status = tk.StringVar(value="Auto-pause is off")
        self.sessions: list[SavedSession] = []
        root.title("3D Scanner 3D Scanner")
        root.geometry("760x520")
        self._build()
        self.refresh()
        self._poll_auto_pause()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="3D Scanner 3D Scanner", font=("Segoe UI", 18, "bold")).pack(anchor=tk.W)
        ttk.Label(frame, textvariable=self.status).pack(anchor=tk.W, pady=(2, 10))
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="Open RTAB-Map", command=self.launch).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Pause", command=lambda: self._bridge_action(self.controller.request_pause)).pack(side=tk.LEFT, padx=6)
        ttk.Button(controls, text="Resume", command=lambda: self._bridge_action(self.controller.request_resume)).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(controls, text="Auto-pause (experimental)", variable=self.auto_enabled,
                        command=self._toggle_auto_pause).pack(side=tk.RIGHT)
        ttk.Label(frame, textvariable=self.auto_status).pack(anchor=tk.W, pady=(10, 6))
        sessions = ttk.LabelFrame(frame, text="Saved RTAB-Map sessions", padding=8)
        sessions.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(sessions, columns=("size", "modified"), show="tree headings", height=10)
        self.tree.heading("#0", text="Database")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Modified (UTC)")
        self.tree.column("#0", width=330)
        self.tree.column("size", width=100)
        self.tree.column("modified", width=180)
        self.tree.pack(fill=tk.BOTH, expand=True)
        actions = ttk.Frame(frame)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions, text="Refresh sessions", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(actions, text="Export raw OBJ", command=self.export_selected).pack(side=tk.RIGHT)

    def launch(self) -> None:
        self.status.set(self.controller.launch().message)

    def refresh(self) -> None:
        dashboard = self.controller.refresh()
        self.status.set(dashboard.runtime_message)
        self.auto_status.set(dashboard.auto_pause_message)
        self.sessions = list(dashboard.sessions)
        self.tree.delete(*self.tree.get_children())
        for index, session in enumerate(self.sessions):
            self.tree.insert("", tk.END, iid=str(index), text=session.path.name,
                             values=(f"{session.size_bytes / 1024 / 1024:.1f} MB", session.modified_at.isoformat()))

    def _toggle_auto_pause(self) -> None:
        if not self.auto_enabled.get():
            self.auto_status.set("Auto-pause is off")
        else:
            self.auto_status.set("Auto-pause warming up: waiting for RTAB-Map activity")

    def _poll_auto_pause(self) -> None:
        if self.auto_enabled.get():
            state = self.monitor.observe(self.probe.observe())
            self.auto_status.set({
                AutoPauseState.WARMING_UP: "Auto-pause warming up: move camera to create map nodes",
                AutoPauseState.ACTIVE: "Auto-pause armed: pauses after 3 seconds without new nodes",
                AutoPauseState.COUNTDOWN: "Auto-pause countdown",
                AutoPauseState.PAUSED: "Auto-pause paused RTAB-Map; review the model",
                AutoPauseState.UNCERTAIN: "Auto-pause unavailable: activity signal is uncertain",
            }.get(state, "Auto-pause is off"))
            if state is AutoPauseState.UNCERTAIN:
                self.auto_enabled.set(False)
        self.root.after(250, self._poll_auto_pause)

    def _bridge_action(self, action) -> None:
        result = action()
        self.status.set(result.message)

    def export_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("3D Scanner 3D Scanner", "Select a saved RTAB-Map database first.")
            return
        session = self.sessions[int(selected[0])]
        self.status.set("Exporting textured OBJ in the background...")
        threading.Thread(target=self._export_worker, args=(session,), daemon=True).start()

    def _export_worker(self, session: SavedSession) -> None:
        result = self.exporter.export(ExportRequest(session.path, self.output_root))
        message = result.error or f"Exported: {result.obj}"
        self.root.after(0, lambda: self.status.set(message))


def main() -> int:
    project_root = Path(__file__).resolve().parents[3]
    rtabmap_root = project_root / "third_party" / "rtabmap" / "RTABMap-0.23.1-win64"
    session_dir = Path.home() / "Documents" / "RTAB-Map"
    runtime = RtabmapRuntime(RtabmapRuntime.discover(rtabmap_root))
    bridge = WindowsRtabmapBridge()
    monitor = ActivityMonitor(pause=bridge.pause)
    catalog = SessionCatalog(session_dir, project_root / "outputs" / "scanner_3d" / "catalog.json")
    controller = scanner_3dController(runtime=runtime, bridge=bridge, monitor=monitor, catalog=catalog)
    root = tk.Tk()
    scanner_3dWindow(root, controller=controller, monitor=monitor,
                         probe=SqliteNodeCountProbe(session_dir / "rtabmap.tmp.db"), catalog=catalog,
                         exporter=ExportService(exporter=runtime._paths.exporter),
                         output_root=project_root / "outputs" / "scanner_3d")
    root.mainloop()
    return 0
