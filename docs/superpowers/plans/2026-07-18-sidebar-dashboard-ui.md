# Sidebar Dashboard UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the existing scanner window into a persistent sidebar dashboard whose Camera, Scan, Sessions, and Export & Crop views can be opened independently.

**Architecture:** Add a pure navigation module that defines the available sidebar pages. Keep `Scanner3DController` and every RTAB-Map/camera/export/crop service unchanged; `Scanner3DWindow` becomes a shell that builds each page once, switches page visibility locally, and refreshes the existing widgets and dashboard summary from `DashboardState`.

**Tech Stack:** Python 3.11, Tkinter/ttk, standard-library `dataclasses` and `enum`, pytest. No new runtime dependencies.

## Global Constraints

- Do not change camera preflight, profile locking, RTAB-Map launch, Pause/Resume, auto-pause, session discovery, export, crop, GLB viewing, or filesystem locations.
- Do not add a scan operation, camera mode, export format, persistent settings store, or new domain controller.
- The sidebar only changes the visible page; it must never reinitialize services or bypass controller validation.
- Keep existing action callbacks and public widget attributes used by `tests/test_scanner_3d_window.py`.
- Keep camera controls disabled while RTAB-Map runs and retain all existing error messages.
- Use native Tkinter/ttk and support the current Windows desktop launch command.

---

### Task 1: Define pure, testable sidebar navigation

**Files:**
- Create: `src/scanner_app/visualization/navigation.py`
- Create: `tests/test_scanner_navigation.py`

**Interfaces:**
- Produces: `DashboardPage`, `NavigationItem`, `navigation_items()`, `default_page()`, and `is_navigable(page)`.
- Consumed by: `Scanner3DWindow` to render the sidebar and reject the reserved Settings item.

- [ ] **Step 1: Write the failing navigation tests**

Create `tests/test_scanner_navigation.py`:

```python
try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.navigation import (
    DashboardPage,
    default_page,
    is_navigable,
    navigation_items,
)


def test_navigation_lists_each_existing_scanner_area_once() -> None:
    items = navigation_items()

    assert [item.page for item in items] == [
        DashboardPage.OVERVIEW,
        DashboardPage.CAMERA,
        DashboardPage.SCAN,
        DashboardPage.SESSIONS,
        DashboardPage.OUTPUTS,
        DashboardPage.SETTINGS,
    ]
    assert [item.enabled for item in items] == [True, True, True, True, True, False]


def test_dashboard_is_the_default_and_settings_is_reserved() -> None:
    assert default_page() is DashboardPage.OVERVIEW
    assert is_navigable(DashboardPage.OVERVIEW)
    assert not is_navigable(DashboardPage.SETTINGS)
```

- [ ] **Step 2: Run the test and verify it fails because the module is absent**

Run:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/test_scanner_navigation.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scanner_app.visualization.navigation'`.

- [ ] **Step 3: Add the minimal navigation module**

Create `src/scanner_app/visualization/navigation.py`:

```python
from dataclasses import dataclass
from enum import Enum


class DashboardPage(str, Enum):
    OVERVIEW = "overview"
    CAMERA = "camera"
    SCAN = "scan"
    SESSIONS = "sessions"
    OUTPUTS = "outputs"
    SETTINGS = "settings"


@dataclass(frozen=True)
class NavigationItem:
    page: DashboardPage
    title: str
    group: str
    enabled: bool = True


def navigation_items() -> tuple[NavigationItem, ...]:
    return (
        NavigationItem(DashboardPage.OVERVIEW, "Overview", "Workspace"),
        NavigationItem(DashboardPage.CAMERA, "Camera setup", "Workspace"),
        NavigationItem(DashboardPage.SCAN, "Scan controls", "Workspace"),
        NavigationItem(DashboardPage.SESSIONS, "Saved sessions", "Models"),
        NavigationItem(DashboardPage.OUTPUTS, "Export & crop", "Models"),
        NavigationItem(DashboardPage.SETTINGS, "Settings", "System", enabled=False),
    )


def default_page() -> DashboardPage:
    return DashboardPage.OVERVIEW


def is_navigable(page: DashboardPage) -> bool:
    return next(item.enabled for item in navigation_items() if item.page is page)
```

- [ ] **Step 4: Run navigation tests and lint**

Run:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/test_scanner_navigation.py -v
rtk proxy .\.venv\Scripts\python.exe -m ruff check src/scanner_app/visualization/navigation.py tests/test_scanner_navigation.py
```

Expected: 2 navigation tests pass and ruff reports no violations.

- [ ] **Step 5: Commit the navigation boundary**

```powershell
rtk git add src/scanner_app/visualization/navigation.py tests/test_scanner_navigation.py
rtk git commit -m "feat: add scanner dashboard navigation model"
```

### Task 2: Build the sidebar shell and independent page containers

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py:1-340`
- Modify: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes: `DashboardPage`, `NavigationItem`, `default_page()`, `is_navigable()`, and existing `DashboardState`.
- Produces: `Scanner3DWindow.show_page(page: DashboardPage) -> None`, persistent page frames, and a dashboard page that only calls existing UI actions.

- [ ] **Step 1: Write object-level failing tests for page selection**

Append to `tests/test_scanner_3d_window.py`:

```python
from scanner_app.visualization.navigation import DashboardPage


class FakePageFrame:
    def __init__(self) -> None:
        self.grid_calls = 0
        self.remove_calls = 0

    def grid(self, **_kwargs) -> None:
        self.grid_calls += 1

    def grid_remove(self) -> None:
        self.remove_calls += 1


class FakeSidebarButton:
    def __init__(self) -> None:
        self.styles: list[str] = []

    def configure(self, *, style: str) -> None:
        self.styles.append(style)


def test_show_page_only_changes_visible_page_and_sidebar_style() -> None:
    overview = FakePageFrame()
    camera = FakePageFrame()
    overview_button = FakeSidebarButton()
    camera_button = FakeSidebarButton()
    window = object.__new__(Scanner3DWindow)
    window.page_frames = {DashboardPage.OVERVIEW: overview, DashboardPage.CAMERA: camera}
    window.sidebar_buttons = {DashboardPage.OVERVIEW: overview_button, DashboardPage.CAMERA: camera_button}
    window.active_page = DashboardPage.OVERVIEW

    window.show_page(DashboardPage.CAMERA)

    assert window.active_page is DashboardPage.CAMERA
    assert overview.remove_calls == 1
    assert camera.grid_calls == 1
    assert overview_button.styles == ["Sidebar.TButton"]
    assert camera_button.styles == ["Sidebar.Active.TButton"]


def test_show_page_ignores_the_reserved_settings_page() -> None:
    window = object.__new__(Scanner3DWindow)
    window.active_page = DashboardPage.OVERVIEW
    window.page_frames = {}
    window.sidebar_buttons = {}

    window.show_page(DashboardPage.SETTINGS)

    assert window.active_page is DashboardPage.OVERVIEW
```

- [ ] **Step 2: Run the tests and verify they fail because `show_page` is absent**

Run:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/test_scanner_3d_window.py::test_show_page_only_changes_visible_page_and_sidebar_style tests/test_scanner_3d_window.py::test_show_page_ignores_the_reserved_settings_page -v
```

Expected: both tests fail with `AttributeError: 'Scanner3DWindow' object has no attribute 'show_page'`.

- [ ] **Step 3: Replace the current vertical `_build()` shell with sidebar and content frames**

Import the navigation interfaces and, in `Scanner3DWindow.__init__`, add:

```python
self.active_page = default_page()
self.page_frames: dict[DashboardPage, ttk.Frame] = {}
self.sidebar_buttons: dict[DashboardPage, ttk.Button] = {}
self.dashboard_camera_value = tk.StringVar(value="Unavailable")
self.dashboard_runtime_value = tk.StringVar(value="RTAB-Map is not running")
self.dashboard_export_value = tk.StringVar(value="No exported model")
self.dashboard_session_value = tk.StringVar(value="0 saved sessions")
root.geometry("1080x780")
root.minsize(860, 640)
```

Implement `_build()` with a `grid`-based shell:

```python
shell = ttk.Frame(self.root, padding=12)
shell.pack(fill=tk.BOTH, expand=True)
shell.columnconfigure(1, weight=1)
shell.rowconfigure(0, weight=1)
sidebar = ttk.Frame(shell, padding=(4, 4, 12, 4), style="Sidebar.TFrame")
sidebar.grid(row=0, column=0, sticky="ns")
self.content = ttk.Frame(shell)
self.content.grid(row=0, column=1, sticky="nsew")
self.content.columnconfigure(0, weight=1)
self.content.rowconfigure(1, weight=1)
```

Build the title/runtime banner in `self.content`, then call `_build_sidebar(sidebar)` and create one frame for each `DashboardPage` under a shared content row. Use `grid_remove()` for inactive frames so every original widget survives page switches.

Implement:

```python
def _build_sidebar(self, parent: ttk.Frame) -> None: ...
def _new_page_frame(self, page: DashboardPage) -> ttk.Frame: ...
def show_page(self, page: DashboardPage) -> None: ...
```

`_build_sidebar()` must add section labels when `NavigationItem.group` changes, bind enabled items to `lambda current=item.page: self.show_page(current)`, and render Settings disabled. `show_page()` must return immediately when `not is_navigable(page)`, remove every frame, grid the selected frame with `row=0, column=0, sticky="nsew"`, and set `Sidebar.Active.TButton` only on the selected sidebar button.

- [ ] **Step 4: Place existing controls in their matching page frames without changing callbacks**

Split the body of the old `_build()` into these methods:

```python
def _build_overview_page(self, parent: ttk.Frame) -> None: ...
def _build_camera_page(self, parent: ttk.Frame) -> None: ...
def _build_scan_page(self, parent: ttk.Frame) -> None: ...
def _build_sessions_page(self, parent: ttk.Frame) -> None: ...
def _build_outputs_page(self, parent: ttk.Frame) -> None: ...
def _build_settings_page(self, parent: ttk.Frame) -> None: ...
```

Move the existing profile combobox, inspection button, apply-and-launch button, and camera settings Treeview to Camera. Move Pause, Resume, auto-pause checkbutton, and `auto_status` label to Scan. Move the existing session Treeview, Refresh sessions, and Export raw OBJ action to Sessions. Move the crop Treeview, Crop raw OBJ, Open cropped model, Open output folder, and Open exported model actions to Export & Crop.

Overview contains read-only labels bound to the four `dashboard_*_value` variables plus buttons that only call `show_page()` for Camera, Scan, Sessions, and Outputs. Settings contains one disabled-page explanatory label and no action callback. Preserve the existing fields `camera_profile_combo`, `inspect_camera_button`, `apply_camera_button`, `camera_settings_tree`, `tree`, `crop_tree`, `open_folder_button`, `open_obj_button`, and `open_exported_button`.

- [ ] **Step 5: Add minimal ttk styles and run window tests**

Configure these styles before building the shell:

```python
style = ttk.Style(self.root)
style.configure("Sidebar.TFrame", background="#173f5f")
style.configure("Sidebar.TButton", anchor=tk.W, padding=(12, 8))
style.configure("Sidebar.Active.TButton", anchor=tk.W, padding=(12, 8), font=("Segoe UI", 10, "bold"))
style.configure("Dashboard.Title.TLabel", font=("Segoe UI", 18, "bold"))
```

Run:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/test_scanner_3d_window.py tests/test_scanner_navigation.py -v
```

Expected: new page-selection tests and all existing controller/window tests pass.

- [ ] **Step 6: Commit the persistent sidebar shell**

```powershell
rtk git add src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py
rtk git commit -m "feat: add scanner sidebar dashboard shell"
```

### Task 3: Refresh dashboard summaries and verify existing workflows

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py:323-430`
- Modify: `tests/test_scanner_3d_window.py`
- Test: `tests/test_scanner_navigation.py`

**Interfaces:**
- Consumes: existing `DashboardState`, `self.sessions`, `self.cropped_outputs`, and `self.latest_export_model`.
- Produces: fresh Overview summary values without introducing another source of scanner state.

- [ ] **Step 1: Write failing tests for overview summary derivation**

Append to `tests/test_scanner_3d_window.py`:

```python
def test_refresh_dashboard_summary_uses_existing_dashboard_and_output_state(tmp_path: Path) -> None:
    class Value:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    window = object.__new__(Scanner3DWindow)
    window.dashboard_runtime_value = Value()
    window.dashboard_camera_value = Value()
    window.dashboard_session_value = Value()
    window.dashboard_export_value = Value()
    window.sessions = [SavedSession(tmp_path / "scan.db", 1, modified_at=None)]  # type: ignore[arg-type]
    window.latest_export_model = tmp_path / "viewer" / "scan.glb"

    dashboard = DashboardState(
        runtime_message="RTAB-Map is running",
        auto_pause_available=True,
        auto_pause_message="Auto-pause ready",
        sessions=tuple(window.sessions),
        busy=False,
        camera_profile=CameraProfile.NEAR,
        camera_snapshot=make_snapshot(),
        camera_controls_locked=True,
    )

    window._refresh_dashboard_summary(dashboard)

    assert window.dashboard_runtime_value.value == "RTAB-Map is running"
    assert window.dashboard_camera_value.value == CameraProfile.NEAR.display_name
    assert window.dashboard_session_value.value == "1 saved session"
    assert window.dashboard_export_value.value == "scan.glb"
```

- [ ] **Step 2: Run the test and verify it fails because the helper is absent**

Run:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/test_scanner_3d_window.py::test_refresh_dashboard_summary_uses_existing_dashboard_and_output_state -v
```

Expected: FAIL with `AttributeError` for `_refresh_dashboard_summary`.

- [ ] **Step 3: Add overview refresh with no controller changes**

Add this method to `Scanner3DWindow`:

```python
def _refresh_dashboard_summary(self, dashboard: DashboardState) -> None:
    self.dashboard_runtime_value.set(dashboard.runtime_message)
    self.dashboard_camera_value.set(dashboard.camera_profile.display_name)
    count = len(self.sessions)
    suffix = "session" if count == 1 else "sessions"
    self.dashboard_session_value.set(f"{count} saved {suffix}")
    self.dashboard_export_value.set(
        self.latest_export_model.name if self.latest_export_model is not None else "No exported model"
    )
```

In `refresh()`, preserve the existing order that reads `controller.refresh()`, camera rows, sessions, and crop outputs. Immediately after `self.refresh_crop_outputs()`, call `self._refresh_dashboard_summary(dashboard)`. Do not put runtime, catalog, or exporter calls in the Overview page itself.

- [ ] **Step 4: Add coverage for unchanged safety behavior**

Keep the existing `test_controller_blocks_profile_changes_and_preflight_while_rtabmap_runs`, `test_dashboard_marks_auto_pause_unavailable_when_activity_is_uncertain`, `test_manual_pause_and_resume_are_available_independently_of_auto_pause`, `test_record_export_result_enables_opening_the_viewer_model`, and `test_record_crop_result_selects_compatible_obj`. Do not rewrite these tests; they are the regression coverage proving the sidebar did not change domain behavior.

- [ ] **Step 5: Run focused tests, full tests, and lint**

Run:

```powershell
rtk proxy .\.venv\Scripts\python.exe -m pytest tests/test_scanner_navigation.py tests/test_scanner_3d_window.py -v
rtk proxy .\.venv\Scripts\python.exe -m pytest -q
rtk proxy .\.venv\Scripts\python.exe -m ruff check src/scanner_app/visualization tests/test_scanner_navigation.py tests/test_scanner_3d_window.py
```

Expected: focused tests pass, the complete suite has zero failures, and ruff reports no violations.

- [ ] **Step 6: Manually verify the Windows desktop application**

Run:

```powershell
rtk .\.venv\Scripts\python.exe scripts\17_3d_scanner.py
```

Verify all of the following:

1. The app opens at 1080×780 or above its 860×640 minimum size.
2. The sidebar stays visible while switching among Overview, Camera setup, Scan controls, Saved sessions, and Export & Crop.
3. Switching pages does not reset the selected camera profile, auto-pause checkbox, selected session, or selected crop output.
4. Camera profile and preflight controls lock when RTAB-Map runs; Pause and Resume remain usable from Scan controls.
5. Existing saved databases can be exported from Saved sessions; existing OBJ files can be cropped from Export & Crop without using Camera or Scan first.
6. Overview labels refresh after session discovery and an export completes.
7. The disabled Settings item performs no action.

- [ ] **Step 7: Commit the summary refresh and verification coverage**

```powershell
rtk git add src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py tests/test_scanner_navigation.py
rtk git commit -m "test: verify independent scanner dashboard views"
```

## Plan self-review

- **Spec coverage:** independent sidebar routes are defined in Task 1; the persistent shell and all existing control placement are implemented in Task 2; dashboard summary/data flow, safety regressions, full suite, and manual Windows checks are in Task 3.
- **Placeholder scan:** no task uses a deferred implementation instruction; each contains paths, signatures, test code, commands, and expected result.
- **Type consistency:** `DashboardPage` and `NavigationItem` are produced only by `navigation.py` and consumed by `Scanner3DWindow` and tests. `DashboardState` remains unchanged and is the sole controller-to-UI state input.
- **Scope check:** the plan restructures presentation only. It deliberately leaves camera, RTAB-Map, auto-pause, catalog, exporter, crop implementation, and file formats unchanged.
