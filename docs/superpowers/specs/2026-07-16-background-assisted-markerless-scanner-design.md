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

1. Preserve native color and align depth **to the color stream**. This changes
   depth coordinates without resampling or depth-masking RGB.
2. Match ORB features in consecutive native-color images. Office background,
   table, and the object are all valid tracking features because they are
   stationary in the same world coordinate system.
3. Lift only matches with valid depth into 3D and estimate a rigid motion with
   RANSAC. Missing object depth therefore removes only those correspondences;
   it does not black out or discard the raw RGB observation.
4. Accept a visual estimate only after geometric quality checks. Integrate
   depth only from accepted keyframes and only inside the existing object ROI.
5. Expose color visibility, depth validity, and alignment-target diagnostics
   so a hardware limitation can be distinguished from an alignment failure.

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

`OrbbecCapture` gains an explicit alignment target: none, color (D2C), or
depth (legacy C2D). The background-assisted mode selects D2C. Its packet has
native BGR color plus depth resampled in color coordinates, and uses
color-camera intrinsics for tracking and fusion. Legacy C2D retains depth
intrinsics.

### Diagnostic runner

A small headless-capable script records color visibility, alignment target,
frame dimensions, and depth-valid ratio. The operator runs it with D2C and
legacy C2D to prove whether the dark corner comes from color-to-depth
alignment before attempting a full scan.

### Background-assisted odometry

The new OpenCV backend runs ORB matching on native RGB with depth aligned to
the color camera. It builds 3D--3D matches only where both matched pixels have
valid aligned depth, estimates a rigid transform with RANSAC, and rejects
low-inlier or high-RMSE results. It is an alternative backend behind the
existing odometry adapter, keeping the current Open3D path available for
comparison.

### Fusion policy

The existing depth ROI and TSDF code remain responsible for object geometry.
An accepted pose from the background-assisted backend can be used for fusion,
but an estimate with insufficient geometric evidence never becomes a keyframe.
The preview is explicitly partial and only shows observed surfaces.

## Acceptance Criteria

1. A synthetic native-color pair with an invalid depth hole still yields a valid
   background-assisted rigid pose from valid background correspondences.
2. D2C selects color intrinsics and keeps the native color image, while legacy
   C2D selects depth intrinsics.
3. The live scanner can select the new backend without changing the legacy
   OpenCV or Open3D paths.
4. A depth-invalid tracking frame cannot be integrated into TSDF.
5. Camera-free unit and script tests pass. A hardware trial produces a
   diagnostic report that records alignment target, color visibility, and tracking state
   while moving around a box corner.

## Fallback Decision

If native RGB is also dark at the box corner, or if the office background cannot
provide enough valid depth-backed feature correspondences, this approach is
recorded as failed with its diagnostic report. The next experiment is a raw
RGB visual-only tracker with calibrated PnP/depth registration, followed by an
actual RTAB-Map bridge only if that still cannot maintain pose.
