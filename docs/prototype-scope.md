# Prototype Scope

## Goal

Build a Python prototype that proves a handheld Orbbec Gemini 215 can capture
RGB-D data in real time, estimate camera pose with visual markers, fuse multiple
frames into a 3D model, and export 3D data for inspection or post-processing.

## In Scope

- Connect to Orbbec Gemini 215.
- Capture RGB frame, depth frame, camera intrinsic, and depth scale.
- Display RGB and depth in real time.
- Generate and display point cloud from depth.
- Track camera pose with ArUco or AprilTag markers.
- Merge point clouds using camera pose.
- Add TSDF fusion after basic point cloud merge works.
- Export `.PLY`.
- Prepare export interfaces for `.OBJ` and `.STL`.

## Out of Scope for First Prototype

- Commercial-quality UI.
- Markerless scanning.
- Fully automatic mesh cleanup and hole filling.
- Industrial accuracy from the first version.
- Robust scanning of shiny, transparent, very dark, or very small objects.
- Texture mapping.

## Recommended Scan Conditions

- Object is fixed on a table.
- 4 to 6 printed markers around the object.
- Marker size around 4 cm to 8 cm.
- Camera distance around 20 cm to 50 cm.
- Initial depth range filter: 0.15 m to 0.70 m.
- Slow camera movement with stable lighting.
