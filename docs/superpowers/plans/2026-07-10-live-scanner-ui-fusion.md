# Live Scanner UI and Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a runnable single-pass markerless scanner with the camera image on the left, a live TSDF model on the right, bounded worker latency, tracking guidance, and optimized single-pass mesh output.

**Architecture:** `ScanSession` owns capture, processing, tracking, recording, keyframes, and fusion workers behind bounded queues. `LiveFusionEngine` integrates only accepted keyframes and throttles geometry extraction. Open3D GUI receives immutable snapshots on its main thread and never performs camera or SLAM work.

**Tech Stack:** Python 3.10+, Open3D GUI/Rendering, NumPy, OpenCV, standard-library threading/queues, existing scanner modules.

## Global Constraints

- Phase 1 hardware gate and Phase 2 tracking benchmark must PASS.
- Camera pane target: 24 FPS or better.
- Tracking target: 15 FPS or better.
- Live geometry preview: 2-5 updates per second.
- TSDF default voxel length: 1.5 mm; SDF truncation: 6 mm.
- Integrate at most 10 accepted keyframes per second.
- Object ROI maximum: 0.35 m per axis.
- Never integrate `DEGRADED` or `LOST` frames.
- UI must remain responsive during capture, optimization, and export.
- `rtk` is unavailable; use the direct commands below.

## File Map

- Create `src/scanner_app/fusion/live.py`: live/rebuild TSDF facade.
- Create `src/scanner_app/session/__init__.py`: package marker.
- Create `src/scanner_app/session/models.py`: session states and snapshots.
- Create `src/scanner_app/session/coverage.py`: accepted-view coverage bins and trajectory.
- Create `src/scanner_app/session/controller.py`: worker lifecycle and bounded queues.
- Create `src/scanner_app/visualization/scanner_window.py`: side-by-side Open3D GUI.
- Create `scripts/14_markerless_scanner.py`: application entry point.
- Create `tests/test_live_fusion.py`, `tests/test_scan_session.py`, `tests/test_scanner_window_model.py`, and `tests/test_markerless_scanner_script.py`.

---

### Task 1: Live TSDF Facade and Deterministic Rebuild

**Files:**
- Create: `src/scanner_app/fusion/live.py`
- Modify: `src/scanner_app/tracking/keyframes.py`
- Test: `tests/test_live_fusion.py`

**Interfaces:**
- Consumes: `Keyframe(packet, processed_depth, camera_to_world, timestamp_us)` and world ROI bounds.
- Produces: `LiveFusionEngine.integrate(keyframe)`, `extract_preview()`, and `rebuild(keyframes)`.

- [ ] **Step 1: Write failing integration/rebuild tests with a fake volume**

```python
import numpy as np
from dataclasses import dataclass

from scanner_app.fusion.live import LiveFusionEngine


class FakeVolume:
    def __init__(self) -> None:
        self.poses = []

    def integrate_keyframe(self, keyframe, roi_min, roi_max) -> None:
        self.poses.append(keyframe.camera_to_world.copy())

    def extract_triangle_mesh(self):
        return {"count": len(self.poses)}


@dataclass(frozen=True)
class FakeKeyframe:
    camera_to_world: np.ndarray


def test_rebuild_discards_live_volume_and_integrates_optimized_keyframes() -> None:
    keyframes = (FakeKeyframe(np.eye(4)), FakeKeyframe(np.eye(4)))
    volumes = []

    def factory():
        volume = FakeVolume()
        volumes.append(volume)
        return volume

    engine = LiveFusionEngine(volume_factory=factory)
    engine.integrate(keyframes[0])
    mesh = engine.rebuild(keyframes)

    assert len(volumes) == 2
    assert mesh == {"count": len(keyframes)}
```

- [ ] **Step 2: Verify the facade is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_live_fusion.py -q`

Expected: FAIL with missing `scanner_app.fusion.live`.

- [ ] **Step 3: Implement the facade and concrete Open3D adapter**

```python
class LiveFusionEngine:
    def __init__(
        self,
        volume_factory=None,
        roi_min=None,
        roi_max=None,
        voxel_length_m=0.0015,
        sdf_trunc_m=0.006,
    ) -> None:
        self.voxel_length_m = float(voxel_length_m)
        self.sdf_trunc_m = float(sdf_trunc_m)
        self.volume_factory = volume_factory or (
            lambda: Open3dTsdfAdapter(self.voxel_length_m, self.sdf_trunc_m)
        )
        self.roi_min = np.asarray(roi_min if roi_min is not None else [-0.175] * 3)
        self.roi_max = np.asarray(roi_max if roi_max is not None else [0.175] * 3)
        self._volume = self.volume_factory()

    def integrate(self, keyframe) -> None:
        self._volume.integrate_keyframe(keyframe, self.roi_min, self.roi_max)

    def extract_preview(self):
        return self._volume.extract_triangle_mesh()

    def rebuild(self, keyframes):
        self._volume = self.volume_factory()
        for keyframe in keyframes:
            self.integrate(keyframe)
        return self.extract_preview()
```

`Open3dTsdfAdapter` creates `ScalableTSDFVolume(voxel_length=0.0015,
sdf_trunc=0.006, color_type=RGB8)` and calls the existing
`integrate_rgbd_frame` helper after converting a packet into the compatibility
`RgbdFrame`. Its `extract_triangle_mesh()` computes normals and returns the mesh.

Use the exact keyframe contract created in Phase 2:

```python
from scanner_app.tracking.keyframes import Keyframe
```

- [ ] **Step 4: Run fusion and existing TSDF tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_live_fusion.py tests/test_tsdf_fusion.py -q`

Expected: PASS; rebuild uses a new volume and optimized poses.

- [ ] **Step 5: Commit live fusion**

```powershell
git add src/scanner_app/fusion/live.py src/scanner_app/tracking/keyframes.py tests/test_live_fusion.py
git commit -m "feat: add rebuildable live TSDF fusion"
```

---

### Task 2: Session State Machine and Bounded Workers

**Files:**
- Create: `src/scanner_app/session/__init__.py`
- Create: `src/scanner_app/session/models.py`
- Create: `src/scanner_app/session/coverage.py`
- Create: `src/scanner_app/session/controller.py`
- Test: `tests/test_scan_session.py`

**Interfaces:**
- Consumes: capture, recorder, depth processor, tracker factory, keyframe store, pose graph, and fusion engine dependencies.
- Produces: `ScanSession.start()`, `pause()`, `finish_pass()`, `reset()`, `latest_snapshot()`, and `close()`.

- [ ] **Step 1: Write failing state and stale-frame tests**

```python
from scanner_app.session.controller import ScanSession, put_latest
from scanner_app.session.models import ScanSessionState


def test_put_latest_drops_stale_item_from_full_queue() -> None:
    queue = Queue(maxsize=1)
    queue.put("old")
    put_latest(queue, "new")
    assert queue.get_nowait() == "new"


def test_finish_is_allowed_only_from_tracking() -> None:
    session = object.__new__(ScanSession)
    session.state = ScanSessionState.IDLE
    assert session.state is ScanSessionState.IDLE
    with pytest.raises(RuntimeError, match="TRACKING"):
        session.finish_pass()


def test_view_coverage_counts_unique_azimuth_bins() -> None:
    coverage = ViewCoverage(object_center=np.zeros(3), azimuth_bins=4, elevation_bins=1)
    coverage.add_camera_position(np.array([1.0, 0.0, 0.0]))
    coverage.add_camera_position(np.array([0.0, 0.0, 1.0]))
    coverage.add_camera_position(np.array([1.0, 0.0, 0.0]))
    assert coverage.ratio == 0.5
    assert len(coverage.trajectory) == 3
```

- [ ] **Step 2: Verify the session package is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_scan_session.py -q`

Expected: FAIL with missing `scanner_app.session`.

- [ ] **Step 3: Implement state contracts and queue behavior**

```python
# src/scanner_app/session/models.py
class ScanSessionState(Enum):
    IDLE = "idle"
    CALIBRATING = "calibrating"
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass(frozen=True)
class ScannerSnapshot:
    state: ScanSessionState
    color_bgr: np.ndarray | None
    tracking: TrackingResult | None
    preview_geometry: object | None
    capture_fps: float
    tracking_fps: float
    preview_fps: float
    depth_valid_ratio: float
    coverage_ratio: float
    trajectory_points: tuple[np.ndarray, ...]
    message: str | None
```

```python
# src/scanner_app/session/coverage.py
class ViewCoverage:
    def __init__(self, object_center, azimuth_bins=24, elevation_bins=3) -> None:
        self.object_center = np.asarray(object_center, dtype=np.float64)
        self.azimuth_bins = int(azimuth_bins)
        self.elevation_bins = int(elevation_bins)
        self._visited: set[tuple[int, int]] = set()
        self._trajectory: list[np.ndarray] = []

    def add_camera_position(self, position) -> None:
        position = np.asarray(position, dtype=np.float64)
        direction = position - self.object_center
        azimuth = (np.arctan2(direction[2], direction[0]) + 2 * np.pi) % (2 * np.pi)
        elevation = np.arctan2(direction[1], np.linalg.norm(direction[[0, 2]]))
        az_bin = min(int(azimuth / (2 * np.pi) * self.azimuth_bins), self.azimuth_bins - 1)
        normalized_elevation = np.clip((elevation + np.pi / 2) / np.pi, 0.0, 0.999999)
        el_bin = int(normalized_elevation * self.elevation_bins)
        self._visited.add((az_bin, el_bin))
        self._trajectory.append(position.copy())

    @property
    def ratio(self) -> float:
        return len(self._visited) / (self.azimuth_bins * self.elevation_bins)

    @property
    def trajectory(self) -> tuple[np.ndarray, ...]:
        return tuple(self._trajectory)
```

```python
# src/scanner_app/session/controller.py
def put_latest(queue: Queue, item) -> None:
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(item)
```

`ScanSession.start()` starts capture, reads calibrated depth intrinsics, creates
the tracker through `tracker_factory(scale_tracking_intrinsics(intrinsics))`,
transitions IDLE to CALIBRATING, estimates the Phase 1 object ROI, creates
`ViewCoverage` from its center, starts recording,
collects two seconds of stationary IMU, initializes tracking, then enters
TRACKING. Capture uses a size-2 latest-frame queue. Tracking stores every packet
in the recorder, creates keyframes only from accepted results, and sends accepted
keyframes to a size-4 fusion queue. Fusion integrates keyframes and emits preview
geometry no more often than every 0.5 seconds. `close()` sets one stop event,
joins all workers with five-second timeouts, then stops camera and recorder.

- [ ] **Step 4: Run lifecycle/concurrency tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_scan_session.py -q`

Expected: PASS for valid transitions, invalid transitions, stale-frame dropping,
worker shutdown, and camera-disconnect preservation of recorded data.

- [ ] **Step 5: Commit session orchestration**

```powershell
git add src/scanner_app/session tests/test_scan_session.py
git commit -m "feat: orchestrate bounded live scan workers"
```

---

### Task 3: Side-by-Side Open3D Scanner Window

**Files:**
- Create: `src/scanner_app/visualization/scanner_window.py`
- Test: `tests/test_scanner_window_model.py`

**Interfaces:**
- Consumes: `ScannerSnapshot` and `ScanSession` commands.
- Produces: `ScannerWindow.run()` and pure `status_from_snapshot(snapshot)` presentation data.

- [ ] **Step 1: Write failing presentation-model tests**

```python
from scanner_app.session.models import ScannerSnapshot, ScanSessionState
from scanner_app.tracking.models import TrackingMetrics, TrackingResult, TrackingState
from scanner_app.visualization.scanner_window import status_from_snapshot


def test_lost_tracking_status_is_red_and_blocks_fusion() -> None:
    tracking = TrackingResult(
        state=TrackingState.LOST,
        camera_to_world=np.eye(4),
        metrics=TrackingMetrics(0.0, float("inf"), 0.0, 0.0, 1.0),
        accepted=False,
        keyframe=False,
        reason="lost",
    )
    snapshot = ScannerSnapshot(
        state=ScanSessionState.TRACKING,
        color_bgr=None,
        tracking=tracking,
        preview_geometry=None,
        capture_fps=25.0,
        tracking_fps=15.0,
        preview_fps=2.0,
        depth_valid_ratio=0.8,
        coverage_ratio=0.5,
        trajectory_points=tuple(),
        message=None,
    )
    status = status_from_snapshot(snapshot)
    assert status.tracking_text == "LOST"
    assert status.tracking_color == (1.0, 0.2, 0.2)
    assert status.guidance == "Return to the last accepted view"
```

- [ ] **Step 2: Verify the scanner window module is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_scanner_window_model.py -q`

Expected: FAIL with missing `scanner_window`.

- [ ] **Step 3: Implement pure status mapping and GUI skeleton**

```python
@dataclass(frozen=True)
class ScannerStatus:
    tracking_text: str
    tracking_color: tuple[float, float, float]
    guidance: str


def status_from_snapshot(snapshot: ScannerSnapshot) -> ScannerStatus:
    tracking = None if snapshot.tracking is None else snapshot.tracking.state
    if tracking is TrackingState.LOST:
        return ScannerStatus("LOST", (1.0, 0.2, 0.2), "Return to the last accepted view")
    if tracking is TrackingState.DEGRADED:
        return ScannerStatus("WEAK", (1.0, 0.75, 0.1), "Move slowly and keep overlap")
    if tracking is TrackingState.TRACKING:
        return ScannerStatus("TRACKING", (0.2, 0.85, 0.35), "")
    return ScannerStatus("READY", (0.7, 0.7, 0.7), "Hold the camera still")
```

```python
class ScannerWindow:
    def __init__(self, session: ScanSession) -> None:
        self.session = session
        app = gui.Application.instance
        self.window = app.create_window("Gemini 215 Markerless Scanner", 1440, 820)
        self.camera = gui.ImageWidget()
        self.scene = gui.SceneWidget()
        self.scene.scene = rendering.Open3DScene(self.window.renderer)
        panes = gui.Horiz()
        panes.add_child(self.camera)
        panes.add_child(self.scene)
        self.window.add_child(panes)
        self.window.set_on_layout(self._on_layout)
        self.window.set_on_close(self._on_close)

    def post_snapshot(self, snapshot: ScannerSnapshot) -> None:
        gui.Application.instance.post_to_main_thread(
            self.window, lambda: self._apply_snapshot(snapshot)
        )
```

Add stable toolbar buttons for Start, Pause, Finish Pass, Reset, and Export.
Use icon buttons when Open3D exposes a standard icon; otherwise use concise
command text. `_apply_snapshot` converts BGR to contiguous RGB, updates the image,
replaces geometry only when the snapshot contains a new preview, and updates
tracking/distance/FPS labels. Keep all Open3D GUI calls on the main thread.

- [ ] **Step 4: Run model tests and a 10-second GUI smoke test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_scanner_window_model.py -q`

Smoke test command is added in Task 4. Expected: unit tests PASS; no GUI call is
made from a worker thread in mocked tests.

- [ ] **Step 5: Commit the scanner window**

```powershell
git add src/scanner_app/visualization/scanner_window.py tests/test_scanner_window_model.py
git commit -m "feat: add side-by-side scanner interface"
```

---

### Task 4: Runnable Single-Pass Markerless Scanner

**Files:**
- Create: `scripts/14_markerless_scanner.py`
- Create: `tests/test_markerless_scanner_script.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: concrete capture, processing, tracker, pose graph, recorder, fusion, session, and GUI implementations.
- Produces: the first end-to-end scanner executable and optimized single-pass PLY.

- [ ] **Step 1: Write a failing dependency-construction test**

```python
def test_build_application_uses_approved_default_geometry_settings(monkeypatch) -> None:
    app = module.build_application(output_root=Path("outputs/ply"))
    assert app.session.fusion.voxel_length_m == 0.0015
    assert app.session.fusion.sdf_trunc_m == 0.006
    assert app.session.capture.capture_config.depth_fps == 30
```

- [ ] **Step 2: Verify the application script is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_markerless_scanner_script.py -q`

Expected: FAIL because `scripts/14_markerless_scanner.py` is absent.

- [ ] **Step 3: Implement composition root and failure exit codes**

```python
def build_application(output_root: Path) -> ScannerWindow:
    capture = OrbbecCapture(
        align_to_depth=True,
        capture_config=CaptureConfig(),
    )
    session = ScanSession(
        capture=capture,
        depth_processor=DepthProcessor(0.15, 0.50),
        tracker_factory=lambda intrinsics: build_markerless_tracker(intrinsics),
        pose_graph=MarkerlessPoseGraph(),
        fusion=LiveFusionEngine(voxel_length_m=0.0015, sdf_trunc_m=0.006),
        output_root=output_root,
    )
    return ScannerWindow(session)


def main() -> int:
    gui.Application.instance.initialize()
    window = build_application(Path("outputs/ply"))
    gui.Application.instance.run()
    return 0 if window.session.state is not ScanSessionState.ERROR else 1
```

Add `--replay PATH` so the entire UI/fusion workflow can run without the camera.
On Finish Pass, optimize poses, rebuild TSDF, clean the mesh, and save a
timestamped single-pass PLY while preserving the recorded session.

- [ ] **Step 4: Verify unit, replay, and live workflows**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_markerless_scanner_script.py tests/test_scan_session.py tests/test_live_fusion.py -q`

Replay smoke test: `.\.venv\Scripts\python.exe scripts\14_markerless_scanner.py --replay data\sessions\tracking_360`

Live run: `.\.venv\Scripts\python.exe scripts\14_markerless_scanner.py`

Expected: camera appears left; model updates right at least twice per second;
tracking loss freezes fusion; Finish produces an optimized single-pass PLY.

- [ ] **Step 5: Commit the single-pass application**

```powershell
git add scripts/14_markerless_scanner.py tests/test_markerless_scanner_script.py README.md
git commit -m "feat: run live markerless single-pass scanning"
```

## Phase Completion Check

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Then run a 10-minute live soak scan. Expected: no crash, no unbounded queue or
memory growth, capture >=24 FPS, tracking >=15 FPS, and preview >=2 FPS. Do not
start two-pass work until the saved single-pass model remains geometrically
coherent after a complete 360-degree camera path.
