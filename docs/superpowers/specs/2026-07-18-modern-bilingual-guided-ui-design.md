# Modern bilingual guided scanner UI

## Status

Design direction agreed with user; written spec pending final review.

## Goal

Make the 3D Scanner desktop application easier to operate for both Vietnamese-speaking operators and English-speaking technicians, without changing the existing camera, RTAB-Map, session, export, or crop behavior.

## User experience

The main window becomes a guided four-step workflow:

1. **Camera setup / Thiết lập camera** — select a camera profile, inspect settings, and apply the profile before launching RTAB-Map.
2. **Scan / Quét** — launch, pause, resume, and monitor RTAB-Map while scanning.
3. **Saved sessions / Session đã lưu** — refresh and select a saved RTAB-Map database.
4. **Export & crop / Xuất & cắt** — export raw OBJ, crop a selected OBJ, open the generated model, or open its folder.

The application keeps the current function boundaries and controller APIs. The redesign changes presentation, grouping, wording, and enablement feedback rather than moving scan ownership into the dashboard.

## Layout

The window uses a resizable modern dashboard layout:

- **Header**: application name, current runtime status, and a `VI | EN` language switch.
- **Workflow stepper**: four steps with the current step highlighted, completed steps marked, and unavailable/future steps visually subdued.
- **Main content card**: the active step's primary controls and the most useful information for that step.
- **Advanced details panel**: collapsible camera settings, auto-pause details, and session metadata. Technical values remain available without dominating the default view.
- **Status bar**: persistent translated status message, severity styling, and background-task progress.

The window should remain usable at the existing desktop size and support resizing. Tables keep horizontal/vertical scrolling where required instead of forcing long technical values into the primary layout.

## Step behavior

The active step is derived from current application state:

- Before a verified camera setup, step 1 is active.
- When RTAB-Map is running, step 2 is active; camera profile and preflight controls are disabled.
- When RTAB-Map is not running and saved sessions are available, step 3 is active.
- After a raw export or when cropped outputs exist, step 4 is active.
- The operator may revisit completed steps, subject to the existing runtime locks and controller validation.

The stepper is an orientation aid, not a second state machine. Existing controller operations remain the source of truth. A failed operation leaves the operator on the same step and presents an actionable message in the status area.

## Actions and feedback

Primary actions use consistent emphasis and translated labels:

- `Apply & Open RTAB-Map / Áp dụng & mở RTAB-Map`
- `Refresh camera settings / Làm mới thông số camera`
- `Pause / Tạm dừng`
- `Resume / Tiếp tục`
- `Refresh sessions / Làm mới session`
- `Export raw OBJ / Xuất OBJ gốc`
- `Crop raw OBJ / Cắt OBJ gốc`
- `Open model / Mở model`
- `Open output folder / Mở thư mục kết quả`

Controls are disabled only when the current runtime state makes the operation invalid. Disabled controls have nearby explanatory text where the reason is not obvious. Long-running export and crop actions continue in background threads, show `Processing... / Đang xử lý...`, and disable only the related action until completion.

Errors use a consistent structure: short problem statement, likely cause when known, and next action. Existing exceptions and result messages remain the source data; the UI maps them to translated, user-facing copy without hiding technical details.

## Localization

UI copy is stored in a small centralized translation catalog keyed by stable identifiers. The active locale is held by the window and all visible labels/status templates are resolved through that catalog. Dynamic values such as file names, FPS, sizes, and error details are interpolated after translation lookup.

Default locale selection follows the Windows UI language: Vietnamese selects Vietnamese; all other locales select English. The explicit `VI | EN` switch takes precedence for the current session and updates visible text immediately. No restart is required.

Technical names such as RTAB-Map, OBJ, GLB, camera profiles, and firmware values are not translated. Where helpful, the UI uses Vietnamese followed by English in the same label rather than translating the technical value.

## Theme and visual system

The UI uses the Windows light/dark preference as its initial theme. Colors, spacing, typography, emphasis, and severity styles are defined through a small theme layer rather than scattered widget-specific constants. The theme must preserve contrast for normal text, disabled controls, focus indicators, and status severities in both modes.

The redesign should use native Tkinter/ttk controls and existing project dependencies. It does not introduce a webview or a new GUI framework.

## Component boundaries

- `Scanner3DWindow`: composes the header, stepper, active content cards, advanced panels, and status bar; forwards actions to the existing controller/services.
- `WorkflowStepper`: presentation-only view of the derived workflow state.
- `TranslationCatalog`: locale selection, translated labels, and formatted status templates.
- `ThemeManager`: applies Windows-aware light/dark styles and semantic severity colors.
- Existing `Scanner3DController`, `ActivityMonitor`, `SessionCatalog`, `ExportService`, `OpenActionService`, and crop workflow remain responsible for domain behavior.

If the current single window file becomes too large, these presentation-only helpers may be split into focused modules, but no unrelated refactor is in scope.

## Data flow

```text
controller.refresh()
        -> DashboardState
        -> derive workflow step + control enablement
        -> render translated cards, details, and status
        -> user action
        -> existing controller/service operation
        -> refresh state and preserve actionable result message
```

The UI must not infer a successful scan from a button click. It refreshes from runtime/catalog state after operations and continues to respect the controller's camera-lock and preflight checks.

## Error handling and edge cases

- Missing camera or failed preflight: keep the user on Camera setup, show the error and a retry action.
- RTAB-Map already running: keep camera controls disabled and explain that the profile is locked until the process stops.
- Uncertain auto-pause activity: show the existing unavailable state and keep manual Pause/Resume visible.
- No saved sessions: show an empty state with the database folder location and Refresh sessions action.
- No crop output selected: disable Open actions and explain that an output must be selected.
- Export/crop failure: re-enable the related controls and retain the failure message in the status bar.
- Narrow window: allow the main card to scroll or stack action groups; do not truncate primary labels.

## Testing and verification

Unit tests should cover:

- workflow-step derivation for preflight, running, saved-session, and exported-output states;
- translation lookup, fallback to English, Windows-language default selection, and immediate locale switching;
- semantic control enablement for runtime locks and missing selections;
- status severity mapping and formatted dynamic values;
- theme selection without changing domain state.

Existing controller, catalog, crop, export, and window behavior tests remain passing. A manual verification pass should launch the Tkinter window in both Windows themes, switch VI/EN while each step is visible, resize the window, trigger a preflight error, and run the export/crop busy states.

## Non-goals

- Replacing RTAB-Map or changing camera/SLAM ownership.
- Adding an embedded 3D preview to the main dashboard.
- Changing file formats, session storage, or export algorithms.
- Adding user accounts, persistent preferences, or a new GUI framework.
