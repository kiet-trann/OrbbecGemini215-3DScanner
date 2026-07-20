# Guided modern scanner dashboard design

## Goal

Replace the existing crowded sidebar dashboard with a modern, Vietnamese-first workspace that guides an operator through a 3D scan while retaining every current specialist control.

## Scope

This changes only the Tkinter presentation layer. It preserves camera preflight, profile selection, RTAB-Map launching, Pause/Resume, auto-pause monitoring, saved-session discovery, OBJ export, crop workflow, GLB opening, output locations, and controller validation.

No scan algorithm, hardware setting, export format, persisted settings store, or domain service changes are in scope.

## Navigation and information architecture

The persistent sidebar contains four Vietnamese routes:

1. **Quét mới** is the default route and the primary operator workflow.
2. **Camera** exposes scan profiles, device inspection, Apply & Open RTAB-Map, and the detailed camera-settings table.
3. **Phiên & kết quả** combines the saved RTAB-Map session catalog with raw export, cropped OBJ catalog, model-opening actions, and output-folder opening.
4. **Công cụ nâng cao** exposes auto-pause and its technical state without making it part of the normal scan path.

The old Overview, Scan controls, Sessions, Export & Crop, and disabled Settings entries are removed. Existing capabilities move into the four routes; none are deleted.

## Quét mới workflow

The default view is a three-stage guided flow:

1. **Kiểm tra camera** shows the selected profile and device/preflight readiness. Its primary action inspects camera settings. A secondary link opens Camera for detailed configuration.
2. **Bắt đầu quét** becomes available after the camera can be applied. Its primary action applies the selected profile and opens RTAB-Map.
3. **Xuất mô hình** remains inactive until a saved session is available, then directs the operator to Phiên & kết quả.

While RTAB-Map is running, the same view becomes a compact live control station instead of showing the setup steps. It displays runtime status prominently, shows Pause and Resume as the primary controls, explains that Camera is locked during a scan, and links to advanced auto-pause controls.

When RTAB-Map is not running, Quét mới returns to the guided preparation state. The view does not own scanner state or issue any controller calls except the existing inspect, launch, pause, and resume callbacks.

## Visual design

Use a restrained Windows-native ttk theme with one dark blue sidebar, a warm/neutral content surface supplied by the active theme, and one high-emphasis primary action per route. Typography establishes three levels: page title, workflow step/action, and contextual technical detail.

The page avoids a grid of competing dashboard cards. Readiness appears as a single concise status region above the current step. Specialist information is presented in labels, tables, and secondary sections only when the operator opens the corresponding route. All visible product language is Vietnamese; RTAB-Map, OBJ, and GLB remain in technical supporting labels when necessary for file compatibility.

The layout supports the current 860x640 minimum window size. At narrow widths, workflow content stacks vertically and action buttons remain visible without horizontal clipping.

## State, safety, and errors

`Scanner3DController` remains the command/state boundary. Route switching is local to `Scanner3DWindow` and must not reinitialize camera, RTAB-Map, monitor, catalog, or exporter services.

The existing refresh loop remains the only source of dashboard state. It derives the guided stage from existing `DashboardState`, the saved-session list, and the latest export path. It retains the current camera-control lock while RTAB-Map runs, availability handling for uncertain auto-pause activity, and existing action error messages.

## Implementation boundaries

Refine the pure navigation definition to the four routes. Split the current view builders into focused route builders and add a small guided-workflow presentation helper that maps existing state into setup, live-control, and results-ready displays.

Keep the existing public widget attributes used by tests, including camera-profile, inspection, launch, camera-settings, session, crop, and output-opening controls. Existing action callbacks remain intact.

## Verification

Add unit coverage for the four routes, default Quét mới selection, guided state derivation, and route switching without controller calls. Retain the existing preflight, profile-lock, Pause/Resume, auto-pause, session, export, crop, and viewer-opening tests.

Run focused UI tests, the full pytest suite, and Ruff. Manually launch the Windows desktop app to verify the guided setup flow, live-control state, advanced controls, session/export/crop actions, and narrow-window layout.
