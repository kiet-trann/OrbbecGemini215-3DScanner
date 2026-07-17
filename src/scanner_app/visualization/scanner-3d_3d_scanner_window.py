"""Desktop control window for the external RTAB-Map scanning workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from scanner_app.rtabmap.activity import ActivityMonitor, AutoPauseState, SqliteNodeCountProbe
from scanner_app.rtabmap.catalog import SessionCatalog
from scanner_app.rtabmap.exporter import ExportRequest, ExportService
from scanner_app.rtabmap.models import RuntimeStatus, SavedSession
from scanner_app.rtabmap.obj_crop import CropRectangle, crop_obj_bundle, perspective_projection_for_bounds
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
        ttk.Button(actions, text="Crop raw OBJ", command=self.choose_crop_source).pack(side=tk.RIGHT, padx=(0, 8))
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

    def choose_crop_source(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Choose raw OBJ to crop",
            initialdir=self.output_root,
            filetypes=[("Wavefront OBJ", "*.obj")],
        )
        if selected:
            self._show_crop_preview(Path(selected))

    def _show_crop_preview(self, source_obj: Path) -> None:
        vertices, faces = _read_obj_mesh(source_obj)
        if not vertices:
            messagebox.showerror("3D Scanner 3D Scanner", "The OBJ contains no vertices.")
            return
        width, height = 700, 500
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Crop preview — {source_obj.name}")
        ttk.Label(dialog, text="Right-drag to rotate · wheel to zoom · left-drag one crop rectangle.").pack(padx=10, pady=(10, 4))
        canvas = tk.Canvas(dialog, width=width, height=height, background="#171717", cursor="crosshair")
        canvas.pack(padx=10, pady=6)
        state: dict[str, float | int | None | object] = {"yaw": 0.65, "pitch": -0.25, "distance": 3.5,
                                                           "x": None, "y": None, "item": None,
                                                           "rotate_x": None, "rotate_y": None, "projection": None}

        def render() -> None:
            projection = perspective_projection_for_bounds(
                vertices, viewport_width=width, viewport_height=height,
                yaw=float(state["yaw"]), pitch=float(state["pitch"]), distance=float(state["distance"]),
            )
            state["projection"] = projection
            canvas.delete("mesh")
            stride = max(1, len(faces) // 2800)
            for number, face in enumerate(faces[::stride]):
                points = [projection.project((*vertices[index - 1], 1.0)) for index in face]
                if all(point is not None for point in points):
                    flat = [coordinate for point in points for coordinate in point]
                    shade = 55 + (number % 4) * 12
                    canvas.create_polygon(*flat, fill=f"#{15:02x}{shade:02x}{min(155, shade + 55):02x}", outline="#255a73", tags="mesh")

        render()

        def start(event) -> None:
            selection["x"], selection["y"] = event.x, event.y
            selection["item"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#ffbf3f", width=2)

        def drag(event) -> None:
            if selection["item"] is not None:
                canvas.coords(selection["item"], selection["x"], selection["y"], event.x, event.y)

        def rotate_start(event) -> None:
            state["rotate_x"], state["rotate_y"] = event.x, event.y

        def rotate(event) -> None:
            if state["rotate_x"] is None:
                return
            state["yaw"] = float(state["yaw"]) + (event.x - float(state["rotate_x"])) * 0.012
            state["pitch"] = max(-1.35, min(1.35, float(state["pitch"]) + (event.y - float(state["rotate_y"])) * 0.012))
            state["rotate_x"], state["rotate_y"] = event.x, event.y
            selection["item"] = None
            render()

        def zoom(event) -> None:
            state["distance"] = max(2.2, min(8.0, float(state["distance"]) - event.delta / 1200.0))
            selection["item"] = None
            render()

        def create_crop() -> None:
            if selection["item"] is None:
                messagebox.showinfo("3D Scanner 3D Scanner", "Drag a rectangle around the object first.", parent=dialog)
                return
            x1, y1, x2, y2 = canvas.coords(selection["item"])
            rectangle = CropRectangle(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            output_dir = source_obj.parent.parent / f"cropped_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.status.set("Creating cropped OBJ in the background...")
            threading.Thread(target=self._crop_worker, args=(source_obj, rectangle, state["projection"], output_dir), daemon=True).start()
            dialog.destroy()

        canvas.bind("<Button-1>", start)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<Button-3>", rotate_start)
        canvas.bind("<B3-Motion>", rotate)
        canvas.bind("<MouseWheel>", zoom)
        ttk.Button(dialog, text="Create cropped OBJ", command=create_crop).pack(pady=(0, 10))

    def _crop_worker(self, source: Path, rectangle: CropRectangle, projection, output_dir: Path) -> None:
        try:
            result = crop_obj_bundle(source, rectangle, projection, output_dir)
            message = f"Cropped OBJ: {result.obj}"
        except (OSError, ValueError) as error:
            message = f"Crop failed: {error}"
        self.root.after(0, lambda: self.status.set(message))


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
    controller = scanner_3dController(runtime=runtime, bridge=bridge, monitor=monitor, catalog=catalog)
    root = tk.Tk()
    scanner_3dWindow(root, controller=controller, monitor=monitor,
                         probe=SqliteNodeCountProbe(session_dir / "rtabmap.tmp.db"), catalog=catalog,
                         exporter=ExportService(exporter=runtime._paths.exporter),
                         output_root=project_root / "outputs" / "scanner_3d")
    root.mainloop()
    return 0
