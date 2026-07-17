# Camera Profile Preflight Design

Date: 2026-07-17

## Purpose and scope

Add a camera-profile preflight to the Windows 3D Scanner application. Before
RTAB-Map is launched, the operator chooses either the Gemini 215 close-range
or long-range depth-work profile. The application temporarily opens the
camera through Orbbec SDK, selects the requested supported work mode, reads
the device state back, releases the camera, and only then starts RTAB-Map.

The application must never change the profile while RTAB-Map is running. The
profile selector, settings refresh, and launch action are disabled for the
whole RTAB-Map lifetime. The app retains the existing safety contract: it does
not stop RTAB-Map, close its database, or save a session.

The Gemini 215 profiles exposed by the UI are:

* **Near / Close-up Precision:** intended operating distance 0.15--0.32 m.
* **Far / Long-distance:** intended operating distance 0.20--0.70 m.

No hard-coded SDK work-mode string is used for long range. The preflight asks
the connected device for its available work modes and maps the two profile
labels to matching reported modes. If a required mode is not present, the
operation fails before RTAB-Map starts.

## Operator experience

1. On startup, the dashboard displays a **Camera setup** panel. It defaults to
   Near / Close-up Precision and marks the state as **Not applied**.
2. The operator selects Near or Far. The panel shows the intended range,
   selected label, and current application capture defaults.
3. Pressing **Apply & Open RTAB-Map** first checks that RTAB-Map is not
   running. It configures the camera, reads its settings back, and releases
   the SDK handle. A successful result displays **Applied and verified** with
   the confirmed device mode, then launches RTAB-Map.
4. The panel also contains **Refresh camera settings**, which performs the
   same read-only device inspection but does not switch a profile. It is
   available only when RTAB-Map is not running.
5. While RTAB-Map runs, the panel is read-only and clearly shows that the
   selected preflight profile is locked for this scan. Pause and Resume keep
   their current behavior and do not unlock the profile.
6. When RTAB-Map exits, the panel becomes editable again. The next scan must
   run a new preflight; a prior successful result is never treated as the
   current hardware state.

## Settings visibility

The panel has a readable key/value table populated after a successful
inspection or preflight. It contains:

* application profile, preflight state, and confirmed depth work-mode name;
* all depth work-mode names reported by the camera;
* product name, serial number, firmware version when SDK supplies them;
* depth and color width, height, pixel format, and FPS;
* depth range, normal object-scan range, RGB/depth alignment target, IMU rate,
  and enabled depth-filter names from the actual capture configuration.

Before a connected camera has been inspected, the table distinguishes
application defaults from unavailable device values instead of presenting
defaults as observed hardware state.

## Architecture

Introduce a small `camera.preflight` service separate from the current capture
pipeline. It owns the short-lived SDK context used before scanning and returns
an immutable `CameraSettingsSnapshot`. The service exposes two operations:

* `inspect(profile)` reads the device identity, supported work modes, current
  work mode, and configured application values without changing the device.
* `apply(profile)` validates the requested profile against the enumerated modes,
  switches the device if needed, reads the selected mode back, returns the
  snapshot, and closes every SDK resource before returning.

The profile is a closed domain model (`NEAR`, `FAR`) with its display text and
operating range. `CameraPreflightController` owns the selected profile and the
last snapshot. It delegates `apply` before `RtabmapRuntime.launch`; it rejects
both actions while `RtabmapRuntime.status().running` is true. The Tkinter
window renders controller state and does not call the SDK itself.

Existing `CaptureConfig` keeps the capture defaults, but its depth-work mode
field expands from Close-Up only to the two application profiles. Direct
markerless scripts retain their current Close-Up default unless they explicitly
select a profile; this feature changes the 3D Scanner dashboard workflow only.

## Failure handling and safety

If the SDK is missing, no camera is connected, device metadata cannot be read,
the requested mode is unavailable, switching fails, verification reads a
different mode, or cleanup raises an error, the dashboard shows a concise
error. RTAB-Map is not launched and the profile remains editable.

The implementation serializes preflight work and UI launch requests so a
second click cannot open concurrent SDK contexts. It never opens the camera
while RTAB-Map is running. Every successful SDK operation releases its
pipeline/context before the RTAB-Map process is started.

The confirmed value is a preflight verification, not a claim about changes
RTAB-Map may make after it takes camera ownership. Hardware acceptance must
verify that the target RTAB-Map build retains the configured work mode through
the start of a scan. If it does not, the app will report the limitation rather
than label the in-scan setting as confirmed.

## Testing and acceptance

Unit tests with a fake SDK cover near and far mode discovery, switching only
when needed, post-switch verification, unavailable-mode failure, device
inspection without mutation, and cleanup on failures. Controller tests prove
that RTAB-Map is launched only after a verified preflight, and that inspect,
apply, and profile changes are rejected while RTAB-Map is running. Window tests
verify that the controls are disabled while locked and that the key/value table
shows all snapshot fields.

Hardware acceptance on Gemini 215 is required before treating both profiles as
ready for normal use:

1. With RTAB-Map stopped, select Near and confirm the device reports its
   close-up mode before RTAB-Map opens.
2. Repeat for Far and confirm the device reports its long-distance mode.
3. In two independent scans, check in Orbbec Viewer or the RTAB-Map depth view
   that the mode remains selected after RTAB-Map begins acquisition.
4. Attempt to edit a profile while RTAB-Map runs and confirm the UI prevents
   it without interrupting the scan.
