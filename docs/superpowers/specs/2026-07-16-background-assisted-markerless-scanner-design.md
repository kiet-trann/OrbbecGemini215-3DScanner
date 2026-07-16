# Background-Assisted Markerless Scanner Design

## Goal

Provide a live, markerless preview mesh for the visible top and side surfaces
of a rigid 5--30 cm object. The operator moves a Gemini 215 around an object
that remains stationary in an ordinary office. The scanner must not require a
fiducial marker, a turntable, a special tracking mat, a complete 360-degree
pass, or an observed bottom surface.

## Root Cause Addressed

The current live scanner requests `align_to_depth=True`. At an oblique or
low-confidence object edge, depth alignment can black out the delivered color
pixels. The existing RGB-D tracker then loses both color features and depth at
the same time. It either accepts a weak frame-to-frame transform or becomes
lost; either result corrupts or interrupts TSDF fusion.

## Chosen Approach

The first implementation is a staged, background-assisted tracker rather than
a wholesale RTAB-Map integration:

1. Capture and display the raw color image independently from an optional
   depth-aligned diagnostic image.
2. Match ORB features in consecutive raw color images. Office background,
   table, and the object are all valid tracking features because they are
   stationary in the same world coordinate system.
3. Lift only matches with valid depth into 3D and estimate a rigid motion with
   RANSAC. Missing object depth therefore removes only those correspondences;
   it does not black out or discard the raw RGB observation.
4. Accept a visual estimate only after geometric quality checks. Integrate
   depth only from accepted keyframes and only inside the existing object ROI.
5. Expose raw-color and aligned-color/depth validity diagnostics so a hardware
   limitation can be distinguished from an alignment-pipeline failure.

The result is an open partial mesh. No stage fills an unobserved bottom or
claims that the scan is watertight.

## Non-Goals

- RTAB-Map/C++ bridge, global loop closure, and full visual-inertial bundle
  adjustment are deferred. They are a fallback only if the bounded tracker
  cannot hold a real office scan.
- Transparent, mirror-like, or strongly IR-absorbing objects are unsupported.
- The first increment does not implement automatic object segmentation or
  texture baking.

## Components

### Capture contract

`OrbbecCapture` gains a raw-color capture mode and records whether a frame is
raw or depth-aligned. `SynchronizedFramePacket` carries raw BGR color as the
tracking image. Existing depth intrinsics continue to describe the depth image;
fusion remains depth-camera based.

### Diagnostic runner

A small headless-capable script presents and records raw color, aligned color
when available, and depth-valid ratio. It reports whether a target region is
dark in raw color, aligned color, or both. The operator can reproduce the
box-edge failure before attempting a full scan.

### Background-assisted odometry

The new OpenCV backend runs ORB matching on raw RGB. It builds 3D--3D matches
only where both matched pixels have valid depth, estimates a rigid transform
with RANSAC, and rejects low-inlier or high-RMSE results. It is an alternative
backend behind the existing odometry adapter, keeping the current Open3D path
available for comparison.

### Fusion policy

The existing depth ROI and TSDF code remain responsible for object geometry.
An accepted pose from the background-assisted backend can be used for fusion,
but an estimate with insufficient geometric evidence never becomes a keyframe.
The preview is explicitly partial and only shows observed surfaces.

## Acceptance Criteria

1. A synthetic raw-color pair with an invalid depth hole still yields a valid
   background-assisted rigid pose from valid background correspondences.
2. A synthetic aligned-black image is distinguishable from a raw-color image
   that contains visible texture.
3. The live scanner can select the new backend without changing the legacy
   OpenCV or Open3D paths.
4. A depth-invalid tracking frame cannot be integrated into TSDF.
5. Camera-free unit and script tests pass. A hardware trial produces a
   diagnostic report that records raw-vs-aligned visibility and tracking state
   while moving around a box corner.

## Fallback Decision

If raw RGB is also dark at the box corner, or if the office background cannot
provide enough valid depth-backed feature correspondences, this approach is
recorded as failed with its diagnostic report. The next experiment is a raw
RGB visual-only tracker with calibrated PnP/depth registration, followed by an
actual RTAB-Map bridge only if that still cannot maintain pose.
