# Scan Workflow

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
