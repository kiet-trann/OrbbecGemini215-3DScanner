# Next Session Handoff

Date noted: 2026-07-04

## Current Status

- Project workspace is ready at `C:\Users\TD-998\OrbbecGemini215-3DScanner`.
- Python virtual environment `.venv` has been created.
- `pyorbbecsdk2`, OpenCV, Open3D, and NumPy are installed in `.venv`.
- Milestone 1 viewer code is implemented:
  - `scripts/01_rgbd_viewer.py`
  - `src/scanner_app/camera/orbbec_capture.py`
- Unit tests pass.
- The latest viewer run reached the Orbbec SDK, but no camera was connected.

## Current Blocker

Gemini 215 camera is not attached yet.

Latest observed message:

```text
No Orbbec device found. Connect Gemini 215 through USB 3.0 and verify it in Orbbec Viewer or Device Manager.
Check USB 3.0 connection, camera power, Orbbec driver/runtime, and Orbbec Viewer.
```

## Continue Tomorrow

1. Connect Orbbec Gemini 215 through USB 3.0.
2. Confirm Windows Device Manager can see the camera.
3. If available, open Orbbec Viewer and confirm RGB/depth stream works.
4. Run:

```powershell
cd C:\Users\TD-998\OrbbecGemini215-3DScanner
.\.venv\Scripts\python.exe scripts\01_rgbd_viewer.py
```

## Expected Result

- OpenCV window named `Gemini 215 RGB-D Viewer` opens.
- Left side shows RGB if color stream is available.
- Right side shows colorized depth.
- Press `Q` or `ESC` to exit.

## Next Development Step After Camera Works

Milestone 2: implement `scripts/02_export_pointcloud.py` to export one depth frame as:

```text
outputs/ply/single_frame.ply
```
