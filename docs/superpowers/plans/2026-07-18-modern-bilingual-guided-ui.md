# Modern bilingual guided scanner UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Tkinter scanner dashboard as a simple four-step Vietnamese/English workflow that follows the Windows light/dark preference while preserving all existing scanner, RTAB-Map, session, export, and crop behavior.

**Architecture:** Keep `Scanner3DController` and all domain services as the source of truth. Add small presentation-only modules for workflow derivation, translation, and theme selection, then make `Scanner3DWindow` compose a header, workflow stepper, active content cards, advanced details, and a status bar. State changes still flow through `controller.refresh()` and existing worker callbacks.

**Tech Stack:** Python 3.10+, Tkinter/ttk, standard-library `enum`, `dataclasses`, `locale`, and Windows `winreg` when available; pytest and ruff for verification; no new runtime dependencies.

## Global Constraints

- The redesign must not change camera, RTAB-Map, session storage, export, crop, or file-format behavior.
- Existing controller operations remain the source of truth; the stepper is presentation-only and must not become a second state machine.
- The main window must support Vietnamese and English, with an immediate `VI | EN` switch and English fallback for unsupported Windows locales.
- The initial locale follows the Windows UI language: Vietnamese selects Vietnamese, all other locales select English.
- The initial theme follows the Windows light/dark preference; light is the safe fallback when the preference cannot be read.
- Use native Tkinter/ttk and existing project dependencies; do not introduce a webview or another GUI framework.
- Long-running export and crop work remains in background threads and disables only the related action.
- Every new pure helper must have unit tests; existing tests must remain passing.
- UI labels must not truncate the primary action; long tables may scroll or stack at narrow widths.

## File map

- Create `src/scanner_app/visualization/workflow.py` for the pure four-step state model and active-step derivation.
- Create `src/scanner_app/visualization/localization.py` for locale detection, translation keys, and formatted UI copy.
- Create `src/scanner_app/visualization/theme.py` for Windows theme detection, semantic palettes, and ttk style configuration.
- Modify `src/scanner_app/visualization/scanner_3d_window.py` to compose the new shell, cards, translated actions, state feedback, and responsive layout while preserving existing callbacks.
- Create `tests/test_scanner_ui_support.py` for workflow, localization, and theme unit tests.
- Modify `tests/test_scanner_3d_window.py` for window-facing state, action enablement, busy-state, and translated status regression tests.
- Update `README.md` and `README.en.md` only after implementation if the visible workflow or language switch needs user-facing instructions; do not change technical setup steps.

---

### Task 1: Add the pure workflow state model

**Files:**
- Create: `src/scanner_app/visualization/workflow.py`
- Test: `tests/test_scanner_ui_support.py`

**Interfaces:**
- Consumes: `CameraSettingsSnapshot | None`, `RuntimeStatus`, saved-session count, exported-model presence, and cropped-output count.
- Produces: `WorkflowStep`, `WorkflowState`, and `derive_workflow_state(...)` for `Scanner3DWindow`.

- [ ] **Step 1: Write failing tests for step derivation**

Add these tests to `tests/test_scanner_ui_support.py`:

```python
from pathlib import Path

from scanner_app.rtabmap.models import RuntimeStatus
from scanner_app.visualization.workflow import WorkflowStep, derive_workflow_state


def test_workflow_starts_at_camera_setup_without_verified_snapshot() -> None:
    state = derive_workflow_state(
        camera_snapshot=None,
        runtime=RuntimeStatus(False, "RTAB-Map is not running"),
        session_count=0,
        exported_model=None,
        cropped_output_count=0,
    )

    assert state.active is WorkflowStep.CAMERA
    assert state.completed == ()


def test_running_rtabmap_activates_scan_and_locks_camera_step() -> None:
    state = derive_workflow_state(
        camera_snapshot=make_snapshot(),
        runtime=RuntimeStatus(True, "RTAB-Map is running"),
        session_count=0,
        exported_model=None,
        cropped_output_count=0,
    )

    assert state.active is WorkflowStep.SCAN
    assert state.completed == (WorkflowStep.CAMERA,)


def test_saved_session_activates_sessions_after_scan_stops() -> None:
    state = derive_workflow_state(
        camera_snapshot=make_snapshot(),
        runtime=RuntimeStatus(False, "RTAB-Map is not running"),
        session_count=1,
        exported_model=None,
        cropped_output_count=0,
    )

    assert state.active is WorkflowStep.SESSIONS
    assert state.completed == (WorkflowStep.CAMERA, WorkflowStep.SCAN)


def test_export_or_crop_activates_output_step() -> None:
    state = derive_workflow_state(
        camera_snapshot=make_snapshot(),
        runtime=RuntimeStatus(False, "RTAB-Map is not running"),
        session_count=1,
        exported_model=Path("viewer/scan.glb"),
        cropped_output_count=0,
    )

    assert state.active is WorkflowStep.OUTPUTS
    assert state.completed == (
        WorkflowStep.CAMERA,
        WorkflowStep.SCAN,
        WorkflowStep.SESSIONS,
    )
```

The test module should define a small `make_snapshot()` using the existing `CameraSettingsSnapshot` and `CaptureConfig` types, matching the fixture data already used in `tests/test_scanner_3d_window.py`.

- [ ] **Step 2: Run the focused tests and verify the import fails**

Run:

```powershell
rtk pytest tests/test_scanner_ui_support.py -q
```

Expected: FAIL because `scanner_app.visualization.workflow` does not exist yet.

- [ ] **Step 3: Implement the minimal pure workflow model**

Create `workflow.py` with these exact public types and rules:

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from scanner_app.camera.models import CameraSettingsSnapshot
from scanner_app.rtabmap.models import RuntimeStatus


class WorkflowStep(str, Enum):
    CAMERA = "camera"
    SCAN = "scan"
    SESSIONS = "sessions"
    OUTPUTS = "outputs"


@dataclass(frozen=True)
class WorkflowState:
    active: WorkflowStep
    completed: tuple[WorkflowStep, ...]


def _camera_verified(snapshot: CameraSettingsSnapshot | None) -> bool:
    return snapshot is not None and snapshot.preflight_state == "applied-and-verified"


def derive_workflow_state(
    *,
    camera_snapshot: CameraSettingsSnapshot | None,
    runtime: RuntimeStatus,
    session_count: int,
    exported_model: Path | None,
    cropped_output_count: int,
) -> WorkflowState:
    camera_done = _camera_verified(camera_snapshot)
    scan_done = camera_done and not runtime.running and session_count > 0
    sessions_done = scan_done and (exported_model is not None or cropped_output_count > 0)
    if exported_model is not None or cropped_output_count > 0:
        active = WorkflowStep.OUTPUTS
    elif runtime.running:
        active = WorkflowStep.SCAN
    elif session_count > 0:
        active = WorkflowStep.SESSIONS
    else:
        active = WorkflowStep.CAMERA
    completed = tuple(
        step
        for step, done in (
            (WorkflowStep.CAMERA, camera_done),
            (WorkflowStep.SCAN, scan_done),
            (WorkflowStep.SESSIONS, sessions_done),
        )
        if done
    )
    return WorkflowState(active=active, completed=completed)
```

The implementation must leave `exported_model` and `cropped_output_count` independent so either output path activates the fourth step.

- [ ] **Step 4: Run the focused tests and lint**

```powershell
rtk pytest tests/test_scanner_ui_support.py -q
rtk ruff check src/scanner_app/visualization/workflow.py tests/test_scanner_ui_support.py
```

Expected: all workflow tests PASS and ruff reports no violations.

- [ ] **Step 5: Commit the workflow model**

```powershell
rtk git add src/scanner_app/visualization/workflow.py tests/test_scanner_ui_support.py
rtk git commit -m "feat: add guided scanner workflow state"
```

### Task 2: Add the bilingual translation catalog

**Files:**
- Create: `src/scanner_app/visualization/localization.py`
- Modify: `tests/test_scanner_ui_support.py`

**Interfaces:**
- Consumes: optional system locale string and stable translation keys.
- Produces: `Locale`, `default_locale(...)`, and `TranslationCatalog` with `text(key, **values)` and `set_locale(...)`.

- [ ] **Step 1: Write failing localization tests**

Add:

```python
from scanner_app.visualization.localization import Locale, TranslationCatalog, default_locale


def test_default_locale_selects_vietnamese_only_for_vi_locales() -> None:
    assert default_locale("vi-VN") is Locale.VI
    assert default_locale("vi") is Locale.VI
    assert default_locale("en-US") is Locale.EN
    assert default_locale("") is Locale.EN


def test_translation_catalog_switches_immediately_and_formats_values() -> None:
    catalog = TranslationCatalog(Locale.EN)

    assert catalog.text("action.export_raw") == "Export raw OBJ"
    catalog.set_locale(Locale.VI)
    assert catalog.text("action.export_raw") == "Xuất OBJ gốc"
    assert catalog.text("status.processing_export", name="scan.db") == (
        "Đang xuất OBJ: scan.db"
    )


def test_unknown_key_falls_back_to_key_without_crashing() -> None:
    catalog = TranslationCatalog(Locale.EN)

    assert catalog.text("missing.key") == "missing.key"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

```powershell
rtk pytest tests/test_scanner_ui_support.py -q
```

Expected: FAIL because `localization.py` does not exist.

- [ ] **Step 3: Implement the catalog and locale detection**

Implement these interfaces:

```python
from enum import Enum
import locale as system_locale


class Locale(str, Enum):
    VI = "vi"
    EN = "en"


def default_locale(system_name: str | None = None) -> Locale:
    value = (system_name if system_name is not None else system_locale.getlocale()[0] or "").casefold()
    return Locale.VI if value == "vi" or value.startswith("vi-") else Locale.EN


class TranslationCatalog:
    def __init__(self, locale: Locale) -> None:
        self.locale = locale

    def set_locale(self, locale: Locale) -> None:
        self.locale = locale

    def text(self, key: str, **values: object) -> str:
        template = TRANSLATIONS.get(key, {}).get(self.locale) or TRANSLATIONS.get(key, {}).get(Locale.EN, key)
        return template.format(**values) if values else template
```

Define all keys required by the redesigned window in one `TRANSLATIONS` mapping, including header, stepper, camera actions, scan actions, session actions, output actions, advanced-details labels, empty states, status messages, error headings, and auto-pause messages. The English copy must remain the fallback. Use the exact Vietnamese labels agreed in the spec; preserve technical values such as RTAB-Map, OBJ, GLB, FPS, and firmware strings.

- [ ] **Step 4: Run localization tests and lint**

```powershell
rtk pytest tests/test_scanner_ui_support.py -q
rtk ruff check src/scanner_app/visualization/localization.py tests/test_scanner_ui_support.py
```

Expected: all localization tests PASS and ruff reports no violations.

- [ ] **Step 5: Commit the catalog**

```powershell
rtk git add src/scanner_app/visualization/localization.py tests/test_scanner_ui_support.py
rtk git commit -m "feat: add bilingual scanner UI catalog"
```

### Task 3: Add Windows-aware theme support

**Files:**
- Create: `src/scanner_app/visualization/theme.py`
- Modify: `tests/test_scanner_ui_support.py`

**Interfaces:**
- Consumes: optional Windows registry value and a `ttk.Style` instance.
- Produces: `ThemeName`, `ThemePalette`, `detect_system_theme(...)`, and `configure_theme(...)`.

- [ ] **Step 1: Write failing theme tests**

Add:

```python
from scanner_app.visualization.theme import ThemeName, ThemePalette, detect_system_theme


def test_theme_detection_maps_windows_registry_value() -> None:
    assert detect_system_theme(0) is ThemeName.DARK
    assert detect_system_theme(1) is ThemeName.LIGHT
    assert detect_system_theme(None) is ThemeName.LIGHT


def test_theme_palette_contains_semantic_status_colors() -> None:
    palette = ThemePalette.for_theme(ThemeName.DARK)

    assert palette.background
    assert palette.foreground
    assert palette.success
    assert palette.warning
    assert palette.error
```

- [ ] **Step 2: Run the focused tests and verify they fail**

```powershell
rtk pytest tests/test_scanner_ui_support.py -q
```

Expected: FAIL because `theme.py` does not exist.

- [ ] **Step 3: Implement theme detection and ttk configuration**

Implement:

```python
from dataclasses import dataclass
from enum import Enum
import tkinter.ttk as ttk


class ThemeName(str, Enum):
    LIGHT = "light"
    DARK = "dark"


def detect_system_theme(apps_use_light_theme: int | None = None) -> ThemeName:
    return ThemeName.DARK if apps_use_light_theme == 0 else ThemeName.LIGHT


@dataclass(frozen=True)
class ThemePalette:
    background: str
    surface: str
    foreground: str
    muted: str
    accent: str
    success: str
    warning: str
    error: str

    @classmethod
    def for_theme(cls, theme: ThemeName) -> "ThemePalette":
        if theme is ThemeName.DARK:
            return cls("#171a1f", "#222832", "#f2f4f7", "#aab4c0", "#4aa3df", "#55c98a", "#e7b84b", "#ef6b73")
        return cls("#f4f6f8", "#ffffff", "#1d2733", "#5e6b78", "#1769aa", "#137a4b", "#9a6500", "#b4232d")


def configure_theme(style: ttk.Style, palette: ThemePalette) -> None:
    style.configure("App.TFrame", background=palette.background)
    style.configure("Card.TLabelframe", background=palette.surface)
    style.configure("Card.TLabelframe.Label", background=palette.surface, foreground=palette.foreground)
    style.configure("App.TLabel", background=palette.background, foreground=palette.foreground)
    style.configure("Muted.TLabel", background=palette.background, foreground=palette.muted)
    style.configure("Status.Success.TLabel", background=palette.background, foreground=palette.success)
    style.configure("Status.Warning.TLabel", background=palette.background, foreground=palette.warning)
    style.configure("Status.Error.TLabel", background=palette.background, foreground=palette.error)
    style.configure("Primary.TButton", padding=(12, 7))
```

Add a `read_windows_theme()` helper with return type `ThemeName` that returns `detect_system_theme()` using `winreg.OpenKey` on `Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize` and the `AppsUseLightTheme` value. Catch `OSError`, use light mode, and keep non-Windows environments on the light fallback so tests and development remain portable.

- [ ] **Step 4: Run theme tests and lint**

```powershell
rtk pytest tests/test_scanner_ui_support.py -q
rtk ruff check src/scanner_app/visualization/theme.py tests/test_scanner_ui_support.py
```

Expected: all theme tests PASS and ruff reports no violations.

- [ ] **Step 5: Commit theme support**

```powershell
rtk git add src/scanner_app/visualization/theme.py tests/test_scanner_ui_support.py
rtk git commit -m "feat: add Windows-aware scanner theme"
```

### Task 4: Replace the window shell with the guided layout

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py:1-330`
- Test: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes: `DashboardState`, `WorkflowState`, `TranslationCatalog`, and `ThemePalette`.
- Produces: a resizable `Scanner3DWindow` with header, stepper, active cards, and status bar; existing public callbacks remain available.

- [ ] **Step 1: Add window-facing tests for composition state**

Extend `tests/test_scanner_3d_window.py` with lightweight object-level tests that do not require a display server:

```python
def test_status_style_name_maps_severity() -> None:
    window = object.__new__(Scanner3DWindow)

    assert window._status_style("success") == "Status.Success.TLabel"
    assert window._status_style("warning") == "Status.Warning.TLabel"
    assert window._status_style("error") == "Status.Error.TLabel"
    assert window._status_style("info") == "App.TLabel"
```

Add a second test that `_set_status("status.ready", "info")` calls the catalog with the key and configures the status label with the info style. Use the existing fake `Status` and `Button` patterns instead of creating `tk.Tk()` in unit tests.

- [ ] **Step 2: Run the new focused tests and verify they fail**

```powershell
rtk pytest tests/test_scanner_3d_window.py::test_status_style_name_maps_severity -q
```

Expected: FAIL because `_status_style` does not exist.

- [ ] **Step 3: Add the window state and shell helpers**

In `Scanner3DWindow.__init__`, add:

```python
self.catalog_i18n = TranslationCatalog(default_locale())
self.workflow_state = WorkflowState(WorkflowStep.CAMERA, ())
self.status_severity = "info"
self.status_label = None
self.active_step_label = None
self.export_busy = False
self.crop_busy = False
self._theme = read_windows_theme()
self._palette = ThemePalette.for_theme(self._theme)
```

Initialize `ttk.Style`, call `configure_theme`, set `root.minsize(720, 700)`, use a larger default geometry such as `980x760`, and set the root title through the translation catalog. Build the following top-level regions in `_build()`:

```python
shell = ttk.Frame(self.root, padding=18, style="App.TFrame")
shell.grid(row=0, column=0, sticky="nsew")
self.root.columnconfigure(0, weight=1)
self.root.rowconfigure(0, weight=1)
shell.columnconfigure(0, weight=1)
shell.rowconfigure(2, weight=1)
self._build_header(shell)
self._build_stepper(shell)
self.content = ttk.Frame(shell, style="App.TFrame")
self.content.grid(row=2, column=0, sticky="nsew", pady=(12, 8))
self._build_status_bar(shell)
```

Use `grid` for the main shell and `pack` only inside small cards. Keep the existing Treeview widgets and crop dialog behavior, but move them into the relevant cards.

- [ ] **Step 4: Implement header and stepper rendering**

Add presentation-only methods with exact signatures:

```python
def _build_header(self, parent: ttk.Frame) -> None: ...
def _build_stepper(self, parent: ttk.Frame) -> None: ...
def _render_stepper(self) -> None: ...
def _status_style(self, severity: str) -> str: ...
def _set_status(self, key: str, severity: str = "info", **values: object) -> None: ...
```

The header contains translated title, runtime-status label, and two radio-style ttk buttons/checkbuttons for `VI` and `EN`. The language command calls `self.catalog_i18n.set_locale(Locale.VI/EN)` and then `_retranslate()`.

The stepper uses four numbered labels. `_render_stepper()` marks a step as completed when it is in `self.workflow_state.completed`, active when it matches `active`, and pending otherwise. It must not invoke controller actions when clicked; it only updates visual emphasis and the active card focus.

- [ ] **Step 5: Run existing window tests**

```powershell
rtk pytest tests/test_scanner_3d_window.py -q
```

Expected: all existing window/controller tests PASS. If a test depends on an old widget attribute, preserve that attribute name while changing its parent card.

- [ ] **Step 6: Commit the shell**

```powershell
rtk git add src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py
rtk git commit -m "feat: add guided scanner window shell"
```

### Task 5: Move existing controls into translated workflow cards

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py:200-430`
- Modify: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes: `DashboardState`, `WorkflowState`, `TranslationCatalog`, existing Treeview/action fields, and current controller methods.
- Produces: `_render_content()`, `_build_camera_card()`, `_build_scan_card()`, `_build_sessions_card()`, `_build_outputs_card()`, and `_retranslate()`.

- [ ] **Step 1: Add tests for derived state refresh and enablement**

Add tests using the existing fake controller/runtime objects:

```python
def test_camera_controls_are_disabled_when_dashboard_reports_runtime_lock() -> None:
    window = object.__new__(Scanner3DWindow)
    window.camera_profile_combo = Button()
    window.inspect_camera_button = Button()
    window.apply_camera_button = Button()

    dashboard = DashboardState(
        runtime_message="RTAB-Map is running",
        auto_pause_available=True,
        auto_pause_message="Auto-pause ready",
        sessions=(),
        busy=False,
        camera_profile=CameraProfile.NEAR,
        camera_snapshot=make_snapshot(),
        camera_controls_locked=True,
    )

    window._refresh_camera_settings(dashboard)

    assert window.camera_profile_combo.states == [tk.DISABLED]
    assert window.inspect_camera_button.states == [tk.DISABLED]
    assert window.apply_camera_button.states == [tk.DISABLED]
```

Use a fake `Button.configure(**kwargs)` that records state and other options. Add a test that a selected crop output enables the two crop actions and that no selection disables them.

- [ ] **Step 2: Run the focused tests and verify any new assertions fail**

```powershell
rtk pytest tests/test_scanner_3d_window.py -q
```

Expected: the new assertions FAIL until the card-rendering and state-refresh changes are complete; existing tests should continue to pass.

- [ ] **Step 3: Rebuild `_build()` into four cards without changing callbacks**

Preserve the existing callback methods and widget attribute names. Create:

```python
def _build_camera_card(self, parent: ttk.Frame) -> None: ...
def _build_scan_card(self, parent: ttk.Frame) -> None: ...
def _build_sessions_card(self, parent: ttk.Frame) -> None: ...
def _build_outputs_card(self, parent: ttk.Frame) -> None: ...
def _build_advanced_details(self, parent: ttk.Frame) -> None: ...
```

The camera card contains profile selection, `Refresh camera settings`, primary `Apply & Open RTAB-Map`, and a collapsed settings Treeview. The scan card contains Pause, Resume, auto-pause checkbutton, and guidance. The sessions card contains the existing database Treeview and Refresh sessions/Export raw OBJ controls. The outputs card contains the crop output Treeview and Open/Crop controls. The advanced details area holds the technical camera Treeview and auto-pause explanation when not needed in the active card.

Use translated text only through `self.catalog_i18n.text(...)`; do not hard-code user-facing English or Vietnamese strings in widget creation.

- [ ] **Step 4: Implement `_render_content()` and refresh integration**

`refresh()` must continue calling `controller.refresh()` and `refresh_crop_outputs()`, then derive workflow state. Prefer adding a `runtime_status: RuntimeStatus` field to `DashboardState` rather than reaching into the controller's private `_runtime`:

```python
self.workflow_state = derive_workflow_state(
    camera_snapshot=dashboard.camera_snapshot,
    runtime=dashboard.runtime_status,
    session_count=len(self.sessions),
    exported_model=self.latest_export_model,
    cropped_output_count=len(self.cropped_outputs),
)
self._render_stepper()
self._render_content()
```

Update `Scanner3DController.refresh()` and all `DashboardState` construction sites/tests together if this field is added. `_render_content()` must update card visibility or stack order based on `workflow_state.active`, while keeping completed cards available as compact summaries. A card click may call `_show_step(step)` but must not bypass controller validation.

- [ ] **Step 5: Implement `_retranslate()`**

Store each dynamic label/button in a field and update it from the catalog:

```python
def _retranslate(self) -> None:
    self.root.title(self.catalog_i18n.text("app.title"))
    self.header_title.configure(text=self.catalog_i18n.text("app.title"))
    self.language_vi.configure(text="VI")
    self.language_en.configure(text="EN")
    self.apply_camera_button.configure(text=self.catalog_i18n.text("action.apply_open"))
    self.inspect_camera_button.configure(text=self.catalog_i18n.text("action.inspect_camera"))
    self._render_stepper()
    self._render_content()
```

Re-translate current status text by storing a status key and values in `_set_status`, not by attempting to parse already formatted strings.

- [ ] **Step 6: Run unit tests and lint**

```powershell
rtk pytest tests/test_scanner_3d_window.py tests/test_scanner_ui_support.py -q
rtk ruff check src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py
```

Expected: all focused tests PASS and ruff reports no violations.

- [ ] **Step 7: Commit the translated cards**

```powershell
rtk git add src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py
rtk git commit -m "feat: organize scanner controls into guided cards"
```

### Task 6: Add busy states, empty states, and actionable status feedback

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py:350-470`
- Modify: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes: export/crop worker callbacks, selection state, translation keys, and semantic theme styles.
- Produces: translated status messages, severity styling, empty-state labels, and narrowly scoped action locking.

- [ ] **Step 1: Write tests for busy and error feedback**

Add tests covering:

```python
def test_set_status_formats_translation_and_applies_severity() -> None:
    window = object.__new__(Scanner3DWindow)
    window.catalog_i18n = TranslationCatalog(Locale.EN)
    window.status = FakeStatusVariable()
    window.status_label = FakeStatusLabel()

    window._set_status("status.processing_export", "info", name="scan.db")

    assert window.status.value == "Exporting OBJ: scan.db"
    assert window.status_label.styles == ["App.TLabel"]


def test_export_failure_clears_busy_state_and_uses_error_style() -> None:
    window = make_window_without_tk()
    window.export_busy = True
    window.export_button = Button()
    window._record_export_result(failed_export_result("export failed"))

    assert window.export_busy is False
    assert window.export_button.states[-1] == tk.NORMAL
    assert window.status_severity == "error"
```

Add an empty-session test asserting the empty-state label contains the translated database-folder guidance, and a no-selection test asserting Export remains disabled or shows an actionable selection message without raising.

- [ ] **Step 2: Run the focused tests and verify they fail**

```powershell
rtk pytest tests/test_scanner_3d_window.py -q
```

Expected: new feedback tests FAIL before the implementation changes.

- [ ] **Step 3: Add status-key storage and semantic styles**

Implement `_set_status()` so it stores:

```python
self._status_key = key
self._status_values = values
self.status_severity = severity
self.status.set(self.catalog_i18n.text(key, **values))
self.status_label.configure(style=self._status_style(severity))
```

Use severity values exactly `info`, `success`, `warning`, and `error`; map them to `App.TLabel`, `Status.Success.TLabel`, `Status.Warning.TLabel`, and `Status.Error.TLabel`.

- [ ] **Step 4: Scope busy-state locking to export and crop actions**

In `export_selected()`, set `self.export_busy = True`, disable only Export raw OBJ and the selected-session action group, and call `_set_status("status.processing_export", "info", name=session.path.name)`. In `_record_export_result`, set `self.export_busy = False`, re-enable the action, set `latest_export_model` and Open exported model state on success, and call `_set_status("status.export_success", "success", name=...)` or `_set_status("status.export_failed", "error", error=...)` on failure.

Apply the same pattern to crop creation and `_record_crop_result`, with `self.crop_busy`, `status.processing_crop`, `status.crop_success`, and `status.crop_failed`. Do not disable session refresh, language switching, or window close.

- [ ] **Step 5: Add translated empty states and selection guidance**

When `self.sessions` is empty, show a label in the session card with the RTAB-Map database directory and a Refresh sessions button. When `self.cropped_outputs` is empty, show a label instructing the operator to export or crop an OBJ. When no session is selected, disable Export raw OBJ and show a status message only if the operator invokes the action through another path. When no crop output is selected, keep Open model/Open folder disabled and show the existing selection guidance.

- [ ] **Step 6: Run focused tests and lint**

```powershell
rtk pytest tests/test_scanner_3d_window.py tests/test_scanner_ui_support.py -q
rtk ruff check src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py
```

Expected: all focused tests PASS and ruff reports no violations.

- [ ] **Step 7: Commit feedback states**

```powershell
rtk git add src/scanner_app/visualization/scanner_3d_window.py tests/test_scanner_3d_window.py
rtk git commit -m "feat: add translated scanner feedback states"
```

### Task 7: Verify responsive layout, documentation, and full regression suite

**Files:**
- Modify: `README.md` only if the language switch or four-step workflow needs documentation.
- Modify: `README.en.md` only if the English instructions need the same update.
- Test: `tests/test_scanner_ui_support.py`
- Test: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes: all completed UI modules and the existing application entry point `scripts/17_3d_scanner.py`.
- Produces: verified behavior in both supported locales and both Windows theme modes, with no regression in existing scanner workflows.

- [ ] **Step 1: Add translation completeness tests**

Define a required-key tuple in `tests/test_scanner_ui_support.py` and assert both locales have non-empty values for every key used by the window:

```python
def test_required_window_translations_exist_for_both_locales() -> None:
    required = (
        "app.title",
        "step.camera",
        "step.scan",
        "step.sessions",
        "step.outputs",
        "action.apply_open",
        "action.inspect_camera",
        "action.export_raw",
        "status.processing_export",
        "status.processing_crop",
    )
    for locale in (Locale.EN, Locale.VI):
        catalog = TranslationCatalog(locale)
        assert all(catalog.text(key) and catalog.text(key) != key for key in required)
```

- [ ] **Step 2: Run the complete test suite**

```powershell
rtk pytest -q
```

Expected: all tests PASS with zero failures.

- [ ] **Step 3: Run the complete lint check**

```powershell
rtk ruff check src tests
```

Expected: ruff reports no violations.

- [ ] **Step 4: Perform manual UI verification on Windows**

Run the application with:

```powershell
rtk .\\.venv\\Scripts\\python.exe scripts\\17_3d_scanner.py
```

Verify each item:

1. The first window opens at a usable size with the four-step workflow visible.
2. Windows light mode produces a light palette and Windows dark mode produces a dark palette.
3. The default language follows Windows language; clicking `VI` or `EN` updates all visible labels without restarting.
4. Camera preflight errors remain on step 1 and show an actionable translated message.
5. Running RTAB-Map activates Scan, disables camera profile/preflight controls, and keeps Pause/Resume available.
6. A saved session appears in Sessions; selecting it enables Export raw OBJ.
7. Export runs without freezing the window, disables only its related action, and enables Open exported model after success.
8. Crop opens the existing crop dialog; crop runs without freezing the window and selects the generated output.
9. Empty session/output lists show guidance instead of blank panels.
10. Resizing to the minimum window size does not truncate primary action labels.

- [ ] **Step 5: Update the bilingual README workflow if needed**

If the manual verification reveals that users need to know about the new stepper or language switch, add a short “Giao diện / Interface” section to `README.md` and the equivalent “Interface” section to `README.en.md`. Keep the existing camera and RTAB-Map instructions unchanged; document only the four steps and `VI | EN` switch.

- [ ] **Step 6: Commit verification/documentation updates**

```powershell
rtk git add src tests README.md README.en.md
rtk git commit -m "test: verify guided bilingual scanner UI"
```

## Plan self-review

- **Spec coverage:** layout is covered by Tasks 4–5; guided-step derivation by Task 1; localization and immediate switching by Task 2 and Task 5; Windows theme by Task 3; background-task/error/empty states by Task 6; tests and manual verification by Task 7.
- **Completeness scan:** the plan contains no unfinished or deferred implementation instructions. Every task identifies files, interfaces, tests, commands, and expected results.
- **Type consistency:** `WorkflowState` is produced by `derive_workflow_state` and consumed by `Scanner3DWindow`; `TranslationCatalog` and `Locale` are shared by the window and tests; `ThemeName`, `ThemePalette`, and `configure_theme` are shared by theme tests and the window.
- **Scope check:** all changes stay in the presentation layer and its tests. Camera, RTAB-Map, catalog, export, crop, and file formats remain out of scope.
