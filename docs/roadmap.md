# Prototype Roadmap

## Milestone 1: RGB-D Viewer

Deliverable: `scripts/01_rgbd_viewer.py`

- Open Gemini 215.
- Display depth real-time.
- Display RGB real-time if available.
- Run stably for at least 5 minutes.

## Milestone 2: Single Frame Point Cloud

Deliverable: `scripts/02_export_pointcloud.py`

- Convert one depth frame to point cloud.
- Export `outputs/ply/single_frame.ply`.
- Validate in CloudCompare, MeshLab, Blender, or Open3D.

## Milestone 2b: Real-Time Point Cloud Preview

Deliverable: `scripts/03_pointcloud_viewer.py`

- Convert live depth frames to point cloud.
- Display point cloud in a non-blocking Open3D window.
- Log frame rate and point count while running.

## Milestone 3: Marker Tracking

Deliverable: `scripts/03_marker_tracking.py`

- Detect ArUco or AprilTag.
- Draw marker axes.
- Report tracking status.

## Milestone 4: Camera Pose

Deliverable: `scripts/04_pose_estimation.py`

- Convert marker pose to camera pose.
- Save timestamp and 4x4 transform per frame.
- Log OK / weak / lost tracking.

## Milestone 5: Merge Point Clouds

Deliverable: `scripts/05_merge_pointcloud.py`

- Transform each valid frame by camera pose.
- Merge into a global point cloud.
- Export `outputs/ply/merged_cloud.ply`.

## Milestone 6: TSDF Fusion

Deliverable: `scripts/06_tsdf_fusion.py`

- Integrate depth frames into an Open3D TSDF volume.
- Extract point cloud or mesh.

## Milestone 7: Mesh Export

Deliverable: `scripts/07_export_mesh.py`

- Reconstruct mesh.
- Export `.PLY`.
- Prepare `.OBJ` and `.STL` paths if the mesh quality is usable.
