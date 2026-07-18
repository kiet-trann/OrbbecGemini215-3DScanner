# Sidebar dashboard UI design

## Goal

Replace the single, vertically crowded scanner window with a sidebar dashboard that lets the operator open Camera setup, Scan controls, Sessions, and Export & Crop independently.

## Scope

This is a presentation-layer reorganization only. It preserves the existing Gemini preflight, RTAB-Map launch and Pause/Resume bridge, auto-pause behavior, session catalog, OBJ export, crop workflow, and GLB-opening behavior. It adds no camera modes, scan operations, file formats, or persistence.

## Layout

The application shell has a fixed left sidebar and one main-content region.

- **Dashboard:** shows current RTAB-Map and auto-pause state, camera profile, most recent export, recent sessions, and shortcuts to existing actions.
- **Camera setup:** holds profile selection, camera inspection, and Apply & Open RTAB-Map.
- **Scan controls:** holds Pause, Resume, auto-pause opt-in, and the detailed activity message.
- **Sessions:** holds saved databases and Refresh sessions.
- **Export & Crop:** holds export actions, cropped-output catalog, and the existing crop UI entry point.
- **Settings:** reserved, disabled placeholder that states no settings are currently available; it creates the navigation boundary without inventing functionality.

The sidebar always remains visible. Selecting an item changes only the main-content view; it does not change scan state or reinitialize any controller/service.

## Architecture

Split Tkinter view construction into a shell plus focused view builders. A small immutable navigation definition declares each route key, title, and builder. `Scanner3DWindow` owns shared Tk variables, controller references, refresh scheduling, and selected route. Each view builder receives only the widgets and callbacks it needs.

Existing `Scanner3DController` remains the state/command boundary. Refresh collects one `DashboardState`, updates shared status variables, then delegates visible data refreshes to the active view. This keeps RTAB-Map and camera logic out of the UI layout modules.

## State and error handling

The global dashboard status banner communicates RTAB-Map state. The Scan controls view shows the precise auto-pause message, including unavailable/error states. Camera controls remain locked while RTAB-Map runs, exactly as they are today. Session/export/crop actions retain their existing error messages and no route can issue Stop, Save, or Close Database commands.

## Testing

Add presentation tests for the registered navigation routes, default Dashboard route, route switching without controller calls, and scan-state-dependent control locks. Retain and run the existing controller/UI tests for preflight, auto-pause, Pause/Resume, sessions, export, crop, and viewer opening.

## Visual reference

The approved wireframe is persisted under the ignored project folder `.superpowers/brainstorm/ui-refresh-20260718/content/sidebar-dashboard.html`.
