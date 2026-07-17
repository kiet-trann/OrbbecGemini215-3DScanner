# 3D Scanner 3D Scanner Design

Date: 2026-07-17

## Purpose and scope

3D Scanner 3D Scanner is a Windows desktop control application around the verified
RTAB-Map + Orbbec Gemini 215 workflow. RTAB-Map remains the only process that
opens the camera, performs SLAM, and maintains the live 3D view. 3D Scanner 3D
Scanner makes that workflow easier to operate: it launches RTAB-Map, presents
the current session state, provides a fail-safe experimental auto-pause mode,
tracks saved sessions, and produces cropped OBJ exports.

Version 1 does not replace RTAB-Map, implement a new SLAM pipeline, open the
Gemini camera itself, save a database automatically, or silently alter a saved
database. It supports one Windows installation of the packaged RTAB-Map 0.23.1
distribution and the existing Gemini 215 configuration.

## Operator experience

1. The operator opens 3D Scanner 3D Scanner and presses **Open RTAB-Map**. The app
   verifies that the configured executable exists, starts it if necessary, and
   shows whether it can identify the RTAB-Map window.
2. The operator scans in RTAB-Map as normal. 3D Scanner 3D Scanner displays a
   companion state only; it does not attempt to claim ownership of the camera.
3. The operator may enable **Auto-pause (experimental)**. After the configured
   inactivity interval (initially three seconds), the app gives a short visible
   countdown and sends RTAB-Map's Pause shortcut exactly once.
4. The operator reviews the live 3D model in RTAB-Map, then chooses to resume
   scanning or manually save the database. The save dialog remains RTAB-Map's
   dialog, preserving its native save semantics.
5. Once a saved `.db` is selected, 3D Scanner 3D Scanner lists it as a session. The
   operator can export a raw OBJ or open its crop workflow. Crop produces a
   second, clearly named OBJ output; the source database and raw export stay
   untouched.

## Architecture

The application is a Python desktop window reusing the repository's packaging,
Open3D, and point-cloud utilities. It is divided into the following focused
components:

* `RtabmapRuntime` resolves the configured RTAB-Map executable, starts it, and
  reports process lifetime. It has no camera API.
* `WindowsRtabmapBridge` finds the RTAB-Map window and can issue only two
  guarded commands: Pause and Resume. A command is permitted only when the
  process and expected window are both present. The bridge never closes the
  application or invokes Save.
* `ActivityMonitor` receives observations from an injected `ActivityProbe` and
  is a small state machine: disabled, warming-up, active, countdown, paused,
  and uncertain. Its first probe reads a non-destructive activity signal from
  RTAB-Map's active temporary database or runtime state; no write access is
  used. The exact signal is a feasibility spike, not an assumption.
* `SessionCatalog` scans the chosen session directory for saved `.db` files and
  stores display metadata in a sidecar catalog. The `.db` is always treated as
  immutable input.
* `ExportService` builds and runs the known RTAB-Map export command, captures
  its log, validates that the OBJ, MTL, and texture outputs exist, and places
  every result under a session-specific output directory.
* `MeshCropService` opens a raw OBJ in an Open3D preview and retains a selected
  3D view-frustum region. It keeps the remaining mesh triangles, UVs, material
  references, and texture files so that a successful cropped export remains a
  textured OBJ. The source OBJ is never overwritten.
* `scanner_3dWindow` presents the control panel, status, session list,
  export/crop actions, and a readable activity log. It depends on the services
  through narrow interfaces, so each service can be tested without a window or
  real RTAB-Map process.

## Auto-pause safety contract

Auto-pause is deliberately opt-in and visibly marked experimental. The monitor
starts only after RTAB-Map is identified and a successful activity baseline has
been observed. While scanning activity continues, the inactivity timer resets.
After three seconds without activity it enters a countdown state, rechecks the
same conditions, then requests a single Pause action. It never sends Stop,
Exit, Close Database, or Save.

If the probe cannot read a reliable signal, RTAB-Map disappears, the window
cannot be identified, the user manually pauses, or the activity signal changes
in an ambiguous way, the monitor transitions to `uncertain`, cancels any
countdown, and sends no keystroke. The UI explains why auto-pause is disabled.
The operator can turn it off at any time and always has explicit Pause/Resume
controls.

The first implementation task is an isolated feasibility spike on the actual
computer. It records whether an active RTAB-Map session exposes a stable,
read-only signal that distinguishes map activity from three seconds of no map
activity. If that acceptance test fails, the release ships with the monitor
disabled and clearly labelled unavailable; the rest of the app is not blocked.

## Sessions, export, and crop

Saving remains a manual RTAB-Map action: File -> Close database -> Save. 3D Scanner
3D Scanner detects the saved file and adds it to the catalog; it does not move,
rename, or rewrite it. Each export is placed in a folder derived from the
session stem and timestamp, with the command log and export metadata beside it.

Raw export uses RTAB-Map's native OBJ path and is validated before the UI calls
it successful. The crop workflow always begins from a successful raw OBJ. The
operator rotates the 3D preview to frame the object, then drags one rectangle.
The rectangle defines an extrusion through the current viewing direction;
triangles outside that view frustum are removed. This preserves faces behind
the visible surface when they project inside the selected rectangle. The app
shows the cropped preview before writing a distinct `*_cropped.obj` bundle.

A single rectangle cannot infer which overlapping surfaces belong to the object
(for example, an object touching a similarly coloured table). Version 1 makes
that limitation explicit: it provides manual framing and a preview, not an
unreliable automatic object recognizer. The original raw OBJ is retained for
retrying the selection.

## Failure handling

Missing RTAB-Map files, a failed process launch, an unidentified window, a
failed auto-pause probe, failed export command, missing export artifacts,
unreadable mesh, cancelled crop, and output-write errors each produce a clear
status plus a saved log location. A failure does not overwrite a `.db`, raw
OBJ, MTL, or texture. Commands run in the background so the window remains
responsive, and conflicting actions are disabled while an export or crop is
running.

## Testing and acceptance

Unit tests cover executable discovery, process state, guarded bridge command
rules, every `ActivityMonitor` transition, catalog change detection, export
command construction and artifact validation, and crop geometry using small
synthetic meshes. Integration tests use fake processes and fake probes to prove
that an uncertain state cannot issue a pause command and that failed exports
leave inputs intact.

Hardware acceptance has four separate checks:

1. 3D Scanner 3D Scanner launches the configured RTAB-Map and never opens a second
   Gemini camera stream.
2. The activity feasibility spike correctly observes both active mapping and a
   three-second inactive interval in repeated real scans. Only then is
   auto-pause enabled for use.
3. A manually saved Gemini session appears in the catalog unchanged.
4. The known `scan_box_20260716.db` produces a validated raw OBJ and a
   separately named cropped OBJ that opens with its material and texture.

