# 3D Scanner

🇻🇳 [Tiếng Việt](README.md) · 🇬🇧 [English](README.en.md)

Windows application that supports a 3D-scanning workflow with the **Orbbec
Gemini 215** and **RTAB-Map**. RTAB-Map operates the camera, performs SLAM,
and creates the 3D model; 3D Scanner opens RTAB-Map, manages saved sessions,
exports OBJ files, and crops individual objects.

> RTAB-Map is the only process that uses the camera and owns the scan session.
> 3D Scanner does not replace RTAB-Map and never stops it or saves a database
> automatically.

## Main workflow

```text
Open 3D Scanner
        ↓
Choose camera profile → Apply & Open RTAB-Map → scan the object → save the database (.db)
        ↓
Refresh sessions → select a database → Export raw OBJ
        ↓
Crop raw OBJ → select the object area → Create cropped OBJ
```

One database can contain the full scanned space. You can export one raw OBJ
for the session, then create several separate cropped OBJ bundles from it. The
application does not automatically determine how many objects the database
contains.

## Requirements

- Windows 10 or Windows 11.
- An Orbbec Gemini 215 with a working driver and SDK.
- The project's Python `.venv` environment.
- Git LFS when cloning the repository; the RTAB-Map runtime is stored in Git
  LFS.

After cloning on another machine, fetch the runtime before launching the app:

```powershell
git lfs pull
```

The following files must then exist:

```text
third_party\rtabmap\RTABMap-0.23.8-win64\bin\RTABMap.exe
third_party\rtabmap\RTABMap-0.23.8-win64\bin\rtabmap-export.exe
third_party\rtabmap\RTABMap-0.23.1-win64\bin\RTABMap.exe
third_party\rtabmap\RTABMap-0.23.1-win64\bin\rtabmap-export.exe
```

RTAB-Map 0.23.8 is the default runtime. The retained 0.23.1 bundle is available
for rollback. Gemini 215 firmware 1.0.9 is recommended for this tested
configuration.

The packaged official 0.23.8 portable bundle reports these actual versions:

| Component | Actual version |
| --- | --- |
| OrbbecSDK | 2.8.7 |
| OpenCV | 4.12.0 |
| PCL | 1.15.1 |
| VTK | 9.3.20231030 |

These values come directly from `rtabmap-export.exe --version` and the
ProductVersion metadata of `OrbbecSDK.dll`. In particular, OpenCV and PCL
differ from the 0.23.8 release-note/design expectations (OpenCV 4.13.0 and
PCL 1.15.0); the versions in the portable bundle are authoritative at runtime.

To use 0.23.1 for one PowerShell launch, set the override before starting the
application:

```powershell
$env:SCANNER_RTABMAP_VERSION='0.23.1'
```

Restore the 0.23.8 default in that PowerShell session with:

```powershell
Remove-Item Env:SCANNER_RTABMAP_VERSION -ErrorAction SilentlyContinue
```

If the project environment does not exist yet, open PowerShell in the cloned
project root and run:

```powershell
$ProjectRoot = (Get-Location).Path
python -m venv .venv
& "$ProjectRoot\.venv\Scripts\Activate.ps1"
python -m pip install -e .[dev]
```

## Launch the application

If you created a desktop shortcut, open **3D Scanner** from that shortcut.

Or, from the cloned project root, run the application directly:

```powershell
$ProjectRoot = (Get-Location).Path
& "$ProjectRoot\.venv\Scripts\pythonw.exe" "$ProjectRoot\scripts\17_3d_scanner.py"
```

When you need terminal error output, use `python.exe` instead:

```powershell
$ProjectRoot = (Get-Location).Path
& "$ProjectRoot\.venv\Scripts\python.exe" "$ProjectRoot\scripts\17_3d_scanner.py"
```

## Scan and save a session

1. Open 3D Scanner.
2. In **Camera setup**, choose **Near — Close-up Precision** (0.15--0.32 m)
   or **Far — Long-distance** (0.20--0.70 m).
3. Optionally select **Refresh camera settings** to see the device's reported
   mode, serial number, firmware, stream profiles, depth range, alignment, IMU,
   and depth filters.
4. Select **Apply & Open RTAB-Map**. The app configures and verifies the mode
   before RTAB-Map opens the camera.
5. In RTAB-Map, select the Orbbec Gemini 215 source and slowly scan around
   the object. Keep the camera focused on the surfaces you need and avoid
   moving too quickly.
6. When scanning is complete, pause if you need to inspect the model.
7. Save the session from RTAB-Map: select **File → Close database**, then
   confirm saving the `.db` database.
8. Return to 3D Scanner and select **Refresh sessions**.

While RTAB-Map is running, the app locks the profile and preflight controls:
you **cannot change the profile** during a scan. Close RTAB-Map, choose the
next profile, then select **Apply & Open RTAB-Map** for the next scan.

RTAB-Map normally saves databases in:

```text
%USERPROFILE%\Documents\RTAB-Map
```

A `.db` file is not only an OBJ model. It stores RTAB-Map session and map
data, including images, depth, camera poses, and SLAM data, so the session can
be exported again or processed further.

## Export a raw OBJ

1. In **Saved RTAB-Map sessions**, select the database to use.
2. Select **Export raw OBJ**.
3. Wait for RTAB-Map to export the raw OBJ, MTL, and texture files.

The raw OBJ contains all session geometry. It can include the object, table,
floor, or several objects. It remains unchanged so that you can crop it again
as many times as needed.

After every export or crop, the app also creates a `viewer` GLB for Windows
3D Viewer. The GLB embeds the mesh, UV coordinates, material, and a JPEG whose
longest edge is capped at 4096 px for reliable colour loading. The original raw
OBJ, MTL, and full-resolution texture remain unchanged for later processing.
In 3D Viewer, open the single `.glb` file inside the `viewer` folder.

## Crop an OBJ

1. Select **Crop raw OBJ** and choose the exported raw OBJ.
2. In the left pane, right-drag to rotate the model and use the mouse wheel to
   zoom. Front, Back, Top, and Bottom return the model to standard RTAB-Map
   views.
3. In the right pane, left-drag a rectangle around the portion to keep.
4. Select **Create cropped OBJ**.

Each crop result is a separate bundle containing an `.obj`, `.mtl`, and
texture. Select a row under **Cropped OBJ outputs**, then select **Open
cropped OBJ** or **Open output folder** to reopen it after restarting the
application.

## Auto-pause (experimental)

Auto-pause is opt-in. When RTAB-Map is scanning and no new map node appears
for about three seconds, 3D Scanner only sends the **Pause** command so you
can inspect the model.

- It never stops RTAB-Map.
- It never closes a database.
- It never saves a session automatically.
- If `Auto-pause unavailable` appears, the application has no reliable
  activity signal from the active session; pause manually when needed.

## File locations

| Content | Location |
| --- | --- |
| Saved RTAB-Map database | `%USERPROFILE%\Documents\RTAB-Map` |
| Default RTAB-Map runtime | `third_party\rtabmap\RTABMap-0.23.8-win64` |
| Retained rollback runtime | `third_party\rtabmap\RTABMap-0.23.1-win64` |
| Raw and cropped OBJ files | `outputs\scanner_3d` |

`third_party/rtabmap` is managed by Git LFS. Scan files, raw OBJ files, and
cropped OBJ files in `outputs/scanner_3d` are generated operating data and
must not be committed to Git.

## Native runtime regressions

Native tests are opt-in so an ordinary test run never opens RTAB-Map or exports
a saved session. To exercise the selected runtime against a real saved
database:

```powershell
$env:RTABMAP_INTEGRATION_DB='C:\Users\you\Documents\RTAB-Map\scan.db'
& .\.venv\Scripts\python.exe -m pytest tests\test_rtabmap_runtime_integration.py -q -k exports
Remove-Item Env:RTABMAP_INTEGRATION_DB -ErrorAction SilentlyContinue
```

The export regression writes only to pytest's temporary output directory. It
checks the source database size and SHA-256 before and after export and
requires the source database to remain unchanged.

Run the real GUI smoke test only on an interactive Windows desktop with no
other RTAB-Map instance open:

```powershell
$env:RTABMAP_GUI_SMOKE='1'
& .\.venv\Scripts\python.exe -m pytest tests\test_rtabmap_runtime_integration.py -q -k launches
Remove-Item Env:RTABMAP_GUI_SMOKE -ErrorAction SilentlyContinue
```

The GUI smoke test opens no camera and no database, waits up to 20 seconds for
a visible RTAB-Map window, and closes only the process it spawned.

## Prototype scope

The repository still contains marker, markerless, and custom-fusion scripts
for technical reference and evaluation. They are not the primary operating
workflow. To scan with the Gemini 215, use 3D Scanner and RTAB-Map as
described above.
