# Scan Workflow

## 3D Scanner camera profile (before RTAB-Map starts)

1. Confirm RTAB-Map is closed.
2. Open 3D Scanner and choose **Near — Close-up Precision** (0.15--0.32 m)
   or **Far — Long-distance** (0.20--0.70 m) in **Camera setup**.
3. Optionally select **Refresh camera settings** to inspect the connected
   Gemini 215 and its available depth work modes.
4. Select **Apply & Open RTAB-Map**. The app switches and verifies the chosen
   mode, releases the camera, and only then starts RTAB-Map.
5. Do not attempt to change the profile while RTAB-Map is running; close
   RTAB-Map before choosing a different profile for a new scan.

1. Connect Gemini 215 to the computer.
2. Start the prototype.
3. Check RGB and depth views.
4. Put the object in the scan area.
5. Place markers around the object.
6. Start scan.
7. Move the camera slowly around the object.
8. Watch tracking status and point cloud preview.
9. Pause or stop scan after one full pass.
10. Inspect preview.
11. Export `.PLY`.
12. Open the exported file in CloudCompare, MeshLab, Blender, or Open3D.

## Basic Quality Rules

- Avoid shiny, transparent, very black, or very small objects in the first tests.
- Avoid harsh shadows.
- Keep camera distance stable.
- Move slowly and avoid sudden rotations.
- Make sure each surface is seen multiple times.

## Markerless office-background trial

Voi vat va moi truong phong dung yen, chay `scripts/16_capture_diagnostic.py
--alignment-target color` truoc. Neu JSON bao `color_visible: true` o canh vat,
thu `scripts/14_markerless_scanner.py --backend background-assisted`. Che do
nay dung depth-to-color alignment de RGB khong bi cat theo depth; no chi export
be mat quan sat va khong tao mat day.
