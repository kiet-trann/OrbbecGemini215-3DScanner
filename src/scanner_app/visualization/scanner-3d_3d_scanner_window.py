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
from scanner_app.visualization.crop_catalog import CroppedObjCatalog, CroppedObjOutput
from scanner_app.visualization.open_actions import OpenActionService


@dataclass(frozen=True)
class DashboardState:
    runtime_message: str
    auto_pause_available: bool
    auto_pause_message: str
    sessions: tuple[SavedSession, ...]
    busy: bool


@dataclass(frozen=True)
class CropPreviewLayout:
    view_title: str
    crop_title: str
    view_instructions: str
    crop_instructions: str


def crop_preview_layout() -> CropPreviewLayout:
    return CropPreviewLayout(
        view_title="3D model view",
        crop_title="Crop here",
        view_instructions="Right-drag to rotate - wheel to zoom",
        crop_instructions="Left-drag one rectangle around the part to keep",
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


def selected_crop_path(outputs: list[CroppedObjOutput], selection: tuple[str, ...]) -> Path | None:
    if not selection:
        return None
    try:
        index = int(selection[0])
    except ValueError:
        return None
    return outputs[index].path if 0 <= index < len(outputs) else None


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
        self.crop_catalog = CroppedObjCatalog(output_root)
        self.cropped_outputs: list[CroppedObjOutput] = []
        self.open_actions = OpenActionService()
        root.title("3D Scanner 3D Scanner")
        root.geometry("760x720")
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
        self.tree = ttk.Treeview(sessions, columns=("size", "modified"), show="tree headings", height=6)
        self.tree.heading("#0", text="Database")
        self.tree.heading("size", text="Size")
        self.tree.heading("modified", text="Modified (UTC)")
        self.tree.column("#0", width=330)
        self.tree.column("size", width=100)
        self.tree.column("modified", width=180)
        self.tree.pack(fill=tk.BOTH, expand=True)
        crops = ttk.LabelFrame(frame, text="Cropped OBJ outputs", padding=8)
        crops.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.crop_tree = ttk.Treeview(crops, columns=("obj", "folder", "size", "modified"), show="headings", height=6)
        self.crop_tree.heading("obj", text="OBJ")
        self.crop_tree.heading("folder", text="Output folder")
        self.crop_tree.heading("size", text="Size")
        self.crop_tree.heading("modified", text="Modified (UTC)")
        self.crop_tree.column("obj", width=230)
        self.crop_tree.column("folder", width=190)
        self.crop_tree.column("size", width=90)
        self.crop_tree.column("modified", width=180)
        self.crop_tree.pack(fill=tk.BOTH, expand=True)
        self.crop_tree.bind("<<TreeviewSelect>>", self._on_crop_selection)
        actions = ttk.Frame(frame)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions, text="Refresh sessions", command=self.refresh).pack(side=tk.LEFT)
        self.open_folder_button = ttk.Button(
            actions, text="Open output folder", command=self.open_latest_output_folder, state=tk.DISABLED
        )
        self.open_folder_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.open_obj_button = ttk.Button(
            actions, text="Open cropped OBJ", command=self.open_latest_cropped_obj, state=tk.DISABLED
        )
        self.open_obj_button.pack(side=tk.RIGHT, padx=(0, 8))
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
        self.refresh_crop_outputs()

    def refresh_crop_outputs(self, select_path: Path | None = None) -> None:
        self.cropped_outputs = self.crop_catalog.refresh()
        self.crop_tree.delete(*self.crop_tree.get_children())
        selected_id: str | None = None
        for index, output in enumerate(self.cropped_outputs):
            identifier = str(index)
            self.crop_tree.insert(
                "", tk.END, iid=identifier,
                values=(
                    output.path.name,
                    output.output_dir.name,
                    f"{output.size_bytes / 1024 / 1024:.1f} MB",
                    output.modified_at.isoformat(),
                ),
            )
            if select_path is not None and output.path == select_path.resolve():
                selected_id = identifier
        if selected_id is not None:
            self.crop_tree.selection_set(selected_id)
            self.crop_tree.focus(selected_id)
            self.crop_tree.see(selected_id)
        self._set_crop_action_state()

    def _on_crop_selection(self, _event=None) -> None:
        self._set_crop_action_state()

    def _set_crop_action_state(self) -> None:
        state = tk.NORMAL if selected_crop_path(self.cropped_outputs, self.crop_tree.selection()) else tk.DISABLED
        self.open_obj_button.configure(state=state)
        self.open_folder_button.configure(state=state)

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
        width, height = 520, 430
        dialog = tk.Toplevel(self.root)
        layout = crop_preview_layout()
        dialog.title(f"Crop preview — {source_obj.name}")
        ttk.Label(dialog, text="Right-drag to rotate · wheel to zoom · left-drag one crop rectangle.").pack(padx=10, pady=(10, 4))
        ttk.Label(
            dialog,
            text="Use the left model to choose the angle. Drag the rectangle only in the right panel.",
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
                messagebox.showinfo("3D Scanner 3D Scanner", "Drag a rectangle around the object first.", parent=dialog)
                return
            x1, y1, x2, y2 = canvas.coords(state["item"])
            rectangle = CropRectangle(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            output_dir = source_obj.parent.parent / f"cropped_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.status.set("Creating cropped OBJ in the background...")
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
        for name, label in (("reset", "Reset"), ("front", "Front"), ("back", "Back"), ("top", "Top"), ("bottom", "Bottom")):
            ttk.Button(view_controls, text=label, command=lambda value=name: apply_preset(value)).pack(side=tk.LEFT, padx=3)
        ttk.Button(dialog, text="Create cropped OBJ", command=create_crop).pack(pady=(0, 10))

    def _crop_worker(self, source: Path, rectangle: CropRectangle, projection, output_dir: Path) -> None:
        try:
            result = crop_obj_bundle(source, rectangle, projection, output_dir)
        except (OSError, ValueError) as error:
            self.root.after(0, self.status.set, f"Crop failed: {error}")
            return
        self.root.after(0, lambda: self._record_crop_result(result))

    def _record_crop_result(self, result: CropResult) -> None:
        self.refresh_crop_outputs(select_path=result.obj)
        self.status.set(f"Cropped OBJ: {result.obj}")

    def open_latest_cropped_obj(self) -> None:
        path = selected_crop_path(self.cropped_outputs, self.crop_tree.selection())
        if path is None:
            self.status.set("Select a cropped OBJ output first")
            return
        self.status.set(self.open_actions.open_obj(path).message)

    def open_latest_output_folder(self) -> None:
        path = selected_crop_path(self.cropped_outputs, self.crop_tree.selection())
        if path is None:
            self.status.set("Select a cropped OBJ output first")
            return
        self.status.set(self.open_actions.open_folder(path).message)


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
