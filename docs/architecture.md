# Architecture

## Main Pipeline

```text
[Gemini 215 Camera]
        |
[Camera Capture]
        |
[RGB-D Processing]
        |
[Marker Tracking / Camera Pose]
        |
[Point Cloud Generation]
        |
[3D Fusion]
        |
[3D Preview]
        |
[Export]
```

## Modules

### Camera Capture

Responsible for opening the Gemini 215, reading RGB/depth frames, retrieving
intrinsics and depth scale, handling missing frames, and shutting down safely.

### RGB-D Processing

Converts raw depth to metric units, filters invalid ranges, aligns depth and RGB
when available, and prepares frames for point cloud generation.

### Marker Tracking

Detects ArUco or AprilTag markers, estimates marker pose, and reports tracking
quality. The first implementation should use OpenCV ArUco because it is included
in `opencv-contrib-python`.

### Camera Pose

Converts marker pose into camera-to-world transforms, stores per-frame pose, and
rejects frames when tracking is lost or unstable.

### Point Cloud Generation

Converts depth pixels to XYZ:

```text
Z = depth
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
```

RGB color is attached when RGB/depth alignment is available.

### 3D Fusion

Prototype stages:

1. Merge transformed point clouds by pose.
2. Downsample and remove outliers.
3. Add Open3D TSDF fusion after marker-based pose is stable.

### Preview

Uses OpenCV windows for RGB/depth and Open3D visualizer for point cloud preview.
The UI can remain simple during the prototype stage.

### Export

Initial required output is point cloud `.PLY`. Mesh `.PLY`, `.OBJ`, and `.STL`
are prepared as later export targets.
