# Markerless Handheld 3D Scanner Design

**Status:** Approved

**Date:** 2026-07-10

## Objective

Build a complete markerless handheld scanner for the Orbbec Gemini 215. The
operator keeps a 5-30 cm object stationary, moves the camera around it by hand,
and sees the live RGB view and an incrementally reconstructed 3D model side by
side. A second pass after flipping the object captures the real bottom surface.
The final optimized mesh must export as PLY, OBJ, and STL with a target
dimensional error of no more than 2 mm on supported objects.

## Supported Operating Envelope

- Object size: 5-30 cm.
- Camera distance: 0.20-0.40 m during normal scanning.
- Camera depth mode: Close_Up Precision Mode.
- Object remains rigid during each pass.
- Initial material scope: matte, opaque, IR-visible surfaces.
- Unsupported in the first release: transparent, mirror-like, strongly
  IR-absorbing, deformable, or moving objects.
- Platform: Windows, Python 3.10 or newer.
- Target workstation: Intel Xeon W-2133, NVIDIA Quadro P2000 5 GB.

## Hardware Baseline

The verified Gemini 215 provides the inputs required by this design:

- USB 3.0 connection.
- Firmware 1.0.9.
- Depth up to 1280x800 at 30 FPS.
- RGB up to 1920x1080 at 30 FPS.
- IR up to 1280x800 at 30 FPS.
- Gyroscope and accelerometer streams, verified at approximately 199 Hz when
  configured for 200 Hz.
- RGB-depth calibration and depth-IMU extrinsics.
- SDK frame synchronization, RGB-depth alignment, and depth post-processing
  filters.

The current marker-based implementation is retained as a diagnostic fallback,
but it is not part of the normal scanning workflow.

## Architecture

```text
[Gemini 215: RGB + Depth + IMU]
                |
        [Capture Worker]
                |
   [Alignment + Depth Processing]
                |
     [IMU Rotation Prediction]
                |
 [RGB-D Odometry + ICP Refinement]
                |
       [Tracking Quality Gate]
          | accept       | reject
          v              v
   [Keyframe Store]  [Relocalizer]
          |
   +------+------------------+
   |                         |
[Live TSDF]          [Pose Graph / Loops]
   |                         |
[Live Preview]       [Optimized Keyframes]
   |                         |
   +------------+------------+
                |
       [Final TSDF Rebuild]
                |
       [PLY / OBJ / STL]
```

Open3D is the first pose and fusion backend. The pose tracker is isolated behind
an interface so RTAB-Map can replace it later without changing capture, session
control, visualization, or export. 3D Gaussian Splatting is not part of the
initial geometry pipeline; it may be added later as an optional appearance
renderer after metric tracking and meshing are stable.

## Data Models and Interfaces

### Synchronized Frame Packet

The capture worker emits one immutable packet containing:

- Aligned BGR color image.
- Raw uint16 depth image and depth scale.
- Depth intrinsics and distortion data.
- RGB-depth and depth-IMU extrinsics.
- Depth and color timestamps.
- All IMU samples between the previous and current depth frame.
- Monotonic packet sequence number.

The queue between capture and tracking is bounded. When tracking falls behind,
the oldest unprocessed packet is dropped so latency cannot grow without bound.

### Pose Tracker

The tracker consumes a synchronized packet and returns:

- `camera_to_world` 4x4 transform.
- Tracking state: `INITIALIZING`, `TRACKING`, `DEGRADED`, or `LOST`.
- ICP fitness and inlier RMSE.
- RGB-D odometry confidence.
- Translation and rotation since the previous accepted frame.
- Whether the frame should become a keyframe.
- A human-readable reason when a pose is rejected.

### Fusion Engine

The fusion engine accepts only approved keyframes. It provides:

- Incremental integration into the live TSDF volume.
- Throttled point-cloud or mesh extraction for preview.
- Full reset and deterministic rebuild from optimized keyframes.
- Final mesh cleanup and export.

## Capture Configuration

- Depth: explicit 1280x800, Y16, 30 FPS.
- Color: explicit 1280x720, RGB, 30 FPS.
- IMU: gyro and accelerometer at 200 Hz.
- Enable SDK frame synchronization.
- Align color to depth coordinates.
- Record both device and host monotonic timestamps.
- Use a worker thread that never performs odometry, fusion, or GUI work.

Tracking uses a 640x400 RGB-D pyramid. Full-resolution depth is retained for
accepted keyframes and final fusion. This separates low-latency pose estimation
from high-detail reconstruction.

## Depth Processing and Object ROI

Depth processing applies the camera-recommended enabled filter chain, followed
by an explicit 0.15-0.50 m range gate. Each filter remains individually
configurable because a filter is retained only when controlled benchmarks show
that it improves valid coverage or temporal noise without erasing small detail.

At scan start, the operator centers the object and holds the camera still. The
system uses valid central depth samples to estimate the object center and creates
a world-space object volume no larger than 0.35 m per axis. The ROI suppresses
the table and distant background before fusion. A dominant support plane is
estimated and excluded from the final object model.

## IMU Processing

The camera remains stationary for two seconds at the start of each pass. Samples
from this interval estimate gyro bias and accelerometer gravity direction. The
first release uses IMU integration as a short-term rotation prediction for
RGB-D odometry and as a motion-speed guard. It does not use raw double-integrated
accelerometer position because that would drift rapidly without a fully
calibrated visual-inertial estimator.

The measured SDK intrinsic fields for IMU bias, noise density, and random walk
are zero/default values, so runtime bias calibration is mandatory.

## Markerless Pose Estimation

The first frame defines the pass coordinate system. For every later packet:

1. Integrate IMU samples to predict relative rotation.
2. Run coarse-to-fine Open3D RGB-D odometry using the prediction as the initial
   transform.
3. Refine the transform with multi-scale point-to-plane ICP.
4. Evaluate fitness, RMSE, overlap, motion magnitude, and timestamp continuity.
5. Accept, degrade, or reject the pose.

Initial configurable quality gates are:

- ICP fitness at least 0.35.
- ICP inlier RMSE no more than 4 mm for live tracking.
- Per-frame translation no more than 50 mm.
- Per-frame rotation no more than 15 degrees.
- No timestamp regression or gap longer than 200 ms.

A frame becomes a keyframe when the accepted camera motion exceeds 5 mm,
rotation exceeds 3 degrees, or 200 ms has elapsed since the previous keyframe.
Frames with poor depth coverage never become keyframes.

## Relocalization and Loop Closure

When tracking is degraded, fusion pauses while pose estimation continues. When
tracking is lost, the displayed model and last accepted pose remain unchanged.
The relocalizer matches ORB features against recent and selected historical
keyframes, lifts matched pixels into 3D using depth, estimates pose with
`solvePnPRansac`, and refines the candidate with ICP. Fusion resumes only after
the normal quality gate accepts the recovered pose.

Keyframes form an Open3D pose graph. Sequential odometry edges are always added;
non-sequential loop candidates use the same feature and geometric verification.
The live TSDF is provisional because it cannot be deformed after pose graph
optimization. Finishing a pass optimizes the graph and reintegrates all
keyframes into a clean TSDF volume.

## Live Fusion

- TSDF voxel length: initial default 1.5 mm.
- SDF truncation: initial default 6 mm.
- Integrate at most 5-10 accepted keyframes per second.
- Extract preview geometry at 2-5 Hz.
- Run preview extraction away from the capture thread.
- Store keyframes so the final TSDF can always be rebuilt deterministically.

## Two-Pass Complete Object Scan

Pass A captures the side and top surfaces in the original orientation. The user
then flips the object and records Pass B to expose the real bottom surface. Each
pass is tracked and optimized independently.

After Pass B:

1. Remove the support plane from both optimized pass clouds.
2. Compute downsampled geometry and FPFH features.
3. Estimate a coarse Pass-B-to-Pass-A transform with RANSAC registration.
4. Refine the transform with multi-scale point-to-plane ICP.
5. Require registration RMSE no greater than 2 mm and verified inlier overlap
   of at least 30 percent.
6. If automatic registration is ambiguous, show both models and require three
   corresponding point pairs from the operator.
7. Transform all Pass B keyframe poses into Pass A coordinates.
8. Rebuild one final TSDF from keyframes from both passes.
9. Remove small disconnected components, fill only small residual holes, and
   compute normals before export.

Automatic registration must never silently accept a low-confidence alignment.
Symmetric objects are expected to require the three-point fallback.

## Application State and UI

One Open3D GUI window is split into two primary panes:

- Left: live RGB image with object ROI and depth-validity overlay.
- Right: live point cloud or mesh with camera trajectory and accepted views.

The toolbar provides Start, Pause, Finish Pass, Start Second Pass, Reset, and
Export commands. Status indicators report tracking state, distance, movement
speed, coverage, capture FPS, tracking FPS, and preview FPS.

The session state machine is:

```text
IDLE -> CALIBRATING -> INITIALIZING -> TRACKING
                                      |       |
                                      v       v
                                  DEGRADED -> LOST
                                      ^         |
                                      +---------+
                                       relocalize
```

Distance, speed, and tracking quality use clear color states. Frames are not
integrated while the camera is too close, too far, moving too quickly, or not
reliably tracked.

## Session Recording and Replay

Every pass records enough information to reproduce tracking without the camera:

- Tracking-resolution synchronized RGB-D packets.
- Full-resolution RGB-D for accepted keyframes.
- IMU samples and timestamps.
- Intrinsics, distortion, extrinsics, configuration, and firmware metadata.
- Accepted and rejected poses with quality metrics.

Recording is asynchronous and chunked. Replay uses the same processing and
tracking interfaces as the live camera, enabling deterministic regression tests
and tuning on identical sequences.

## Failure Handling

- Missing or sparse depth: reject the frame and display a distance/depth warning.
- Excessive motion: pause fusion until motion returns to range.
- Degraded tracking: continue pose attempts without integration.
- Lost tracking: freeze geometry and attempt keyframe relocalization.
- Failed two-pass alignment: require manual three-point correspondence.
- Camera disconnect: stop capture safely and preserve the recorded pass.
- Processing overload: drop stale packets rather than increasing latency.
- Preview extraction failure: keep scanning and retain the last valid preview.
- Export failure: preserve the optimized session and report the exact output
  operation that failed.

## Performance Targets

- Synchronized RGB-D capture: at least 24 FPS.
- IMU delivery: 190-210 samples per second at the 200 Hz setting.
- Pose tracking: at least 15 FPS during normal operation.
- Live geometry preview: at least 2 updates per second.
- End-to-end live latency: no unbounded queue growth.
- Continuous operation: 10 minutes without crash or unbounded memory growth.

## Accuracy and Acceptance Tests

### Hardware Qualification Gate

Use three matte test objects at 0.20, 0.30, and 0.40 m. For the visible object
mask, require at least 70 percent valid depth. Measure temporal depth stability
on a static planar target and require median noise no greater than 1 mm and the
90th percentile no greater than 2 mm at 0.30 m.

The camera is declared insufficient only if these tests fail after verifying:

- USB 3.0 operation.
- Firmware 1.0.9 or the current Orbbec-recommended version.
- Close_Up Precision Mode.
- Exposure and IR settings in Orbbec Viewer.
- The SDK-recommended depth filter chain.
- Clean lenses, controlled indoor lighting, and supported matte targets.

### Tracking Acceptance

- Complete a handheld 360-degree pass without unrecovered tracking loss.
- Maintain at least 15 tracking updates per second.
- Limit optimized loop-end position error to 3 mm.
- Reject deliberately fast motions without corrupting the TSDF.
- Recover from a short occlusion by relocalizing to a stored keyframe.

### Reconstruction Acceptance

- Scan calibrated box and cylinder references covering the supported size range.
- Keep measured mesh dimensions within 2 mm of caliper measurements.
- Keep automatic two-pass registration RMSE within 2 mm.
- Include side, top, and real bottom surfaces in the final model.
- Produce no large detached components after cleanup.
- Export readable PLY, OBJ, and STL files.

## Test Strategy

- Unit tests for timestamp grouping, IMU bias estimation, pose composition,
  quality gates, keyframe selection, state transitions, ROI generation, and
  pass-transform composition.
- Synthetic geometry tests for ICP, pose graph edges, support-plane removal,
  and two-pass registration.
- Recorded-sequence integration tests for tracking, relocalization, fusion, and
  deterministic replay.
- Hardware tests marked separately so the normal unit suite remains camera-free.
- End-to-end manual acceptance runs with calibrated reference objects.

## Delivery Boundaries

The first complete release includes hardware qualification, synchronized RGB-D
and IMU capture, markerless tracking, relocalization, live side-by-side display,
single-pass and two-pass reconstruction, final optimization, and mesh export.
RTAB-Map replacement and 3D Gaussian Splatting are explicit follow-on options,
not requirements for the first accepted scanner.
