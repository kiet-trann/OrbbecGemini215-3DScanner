# Markerless Tracking Design

**Status:** Approved direction

**Date:** 2026-07-13

## Goal

Produce reliable metric camera poses and accepted RGB-D keyframes while an
operator moves the Gemini 215 around a stationary 5-30 cm matte object. This
sub-project deliberately stops before TSDF fusion and the live scanner window.

## Operating Envelope

- The object is rigid, opaque, matte, and IR-visible.
- The camera remains 0.20-0.30 m from the object during one scan pass.
- The camera uses `Close_Up Precision Mode` throughout the pass.
- A stationary two-second calibration occurs before motion begins.
- The operator moves slowly with continuous view overlap.
- `Extended Distance Mode` is a separate capture configuration for distances
  near 0.40 m; the tracker never switches depth mode during a pass.

## Chosen Approach

The tracker uses Open3D RGB-D odometry followed by multi-scale point-to-plane
ICP. Gyroscope integration provides an initial relative rotation only; the
accelerometer is used to estimate gravity during stationary calibration and is
not double-integrated into translation. This preserves metric translation from
depth while avoiding accelerometer drift.

## Data Flow

```text
SynchronizedFramePacket
  -> depth validity and 640x400 tracking image
  -> IMU rotation prediction
  -> RGB-D odometry
  -> point-to-plane ICP refinement
  -> tracking quality gate
  -> accepted pose and optional keyframe
```

The first accepted frame defines the pass world coordinate system. Every
accepted relative camera motion is composed into `camera_to_world`. Rejected
frames never alter the last accepted pose or keyframe store.

## Components

### Tracking Contracts

`TrackingState` has `INITIALIZING`, `TRACKING`, `DEGRADED`, and `LOST` values.
`TrackingResult` contains `camera_to_world`, metrics, acceptance, keyframe
decision, and rejection reason. All transforms are finite 4x4 float64 matrices.

### IMU Estimator

`ImuEstimator.calibrate(samples)` requires stationary gyro and accelerometer
samples and stores gyro bias plus a normalized gravity direction. The estimator
integrates bias-corrected gyroscope samples with timestamp order validation to
return a 3x3 predicted relative rotation. A missing or discontinuous IMU slice
returns identity rotation and reports no prediction rather than fabricating
motion.

### RGB-D Odometry Adapter

The adapter consumes depth-processed packets at 640x400 with scaled intrinsics.
It runs Open3D RGB-D odometry initialized from the IMU rotation and refines a
candidate transform using a three-level point-to-plane ICP schedule. Open3D is
isolated behind an adapter so synthetic tests can supply deterministic odometry
and ICP responses without a camera or GPU.

### Quality Gate

An estimate is accepted only when all conditions hold:

- ICP fitness is at least 0.35.
- ICP inlier RMSE is at most 0.004 m.
- Relative translation is at most 0.050 m.
- Relative rotation is at most 15 degrees.
- Packet timestamps are strictly increasing and the gap is at most 200 ms.
- The tracking-depth valid ratio is sufficient for the odometry adapter.

An estimate failing a gate becomes `DEGRADED`. Consecutive rejected estimates
become `LOST`; a later valid estimate may restore `TRACKING`. The threshold for
that transition is configurable and defaults to three rejected estimates.

### Keyframes

Only accepted poses can create keyframes. A frame becomes a keyframe when it is
the first accepted frame or has moved at least 0.005 m, rotated at least 3
degrees, or is at least 200 ms newer than the preceding keyframe. The keyframe
stores the full-resolution synchronized packet, camera pose, and metrics.

## Runnable Benchmark

`scripts/13_markerless_tracking.py` supports a recorded session and a live
Gemini 215 capture. It prints per-frame state, accepted/rejected decision,
fitness, RMSE, motion, and keyframe count. It writes accepted poses and metrics
to the scan session so the later fusion phase can replay the same data.

## Failure Handling

- Missing color/depth, sparse depth, or invalid timestamps reject the frame.
- Excessive camera motion rejects the frame without corrupting the last pose.
- A tracking loss preserves the last accepted pose and keyframes.
- The benchmark exits safely on camera disconnect and retains completed output.
- Live tuning begins only after replay tests pass.

## Acceptance

- Unit tests cover IMU calibration, pose composition, quality limits, state
  transitions, and keyframe policy without hardware.
- A recorded or live slow 360-degree pass has no unrecovered loss.
- Live tracking reaches at least 15 accepted updates per second on the target
  workstation.
- Deliberately fast motion is rejected and does not change accepted pose.

