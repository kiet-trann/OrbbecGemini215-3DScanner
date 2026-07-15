# IMU Orientation Viewer Design

## Goal

Provide a standalone live viewer that proves the Gemini 215 IMU stream is available, timestamped, calibrated, and produces a coherent camera orientation in 3D. It intentionally does not claim to estimate camera position.

## Operator Experience

The operator starts the viewer, holds the camera still, and presses `C` to calibrate. The viewer collects a configurable 3-second stationary sample window, estimates gyroscope bias and gravity direction, and then renders a camera model at the world origin. Moving or rotating the real camera rotates the model and its X/Y/Z axes in real time. `R` resets the orientation to the current attitude; `Q` or Escape exits.

The status overlay shows IMU sample rate, calibration state, gyroscope bias, roll, pitch, yaw, and dropped/out-of-order sample counts. The model never translates through 3D space because raw accelerometer double integration has unbounded drift in this application.

## Architecture

```text
OrbbecCapture.read_packet()
  -> synchronized IMU samples
  -> ImuOrientationTracker
  -> OrientationState(rotation, roll, pitch, yaw, rates, diagnostics)
  -> Open3D live camera-model viewer
```

`ImuOrientationTracker` owns stationary calibration, timestamp validation, gyroscope integration, gravity correction, and reset. It consumes the existing `ImuSample` model and remains independent of the RGB-D tracker. A dedicated Open3D viewer owns geometry and display only; it receives an immutable orientation state and updates a camera body plus coordinate frame each render cycle.

## Orientation Estimation

During calibration, average at least 100 gyroscope and accelerometer samples. The gyro average is the bias. The normalized accelerometer average establishes world gravity. At runtime, integrate gyro samples in timestamp order with a midpoint rule. Apply a conservative accelerometer gravity correction only when acceleration magnitude is near gravity, so hand translation does not tilt the model aggressively. Reject non-increasing timestamps and count them; do not apply their motion.

Roll, pitch, and yaw are reported from the world-to-camera rotation using a documented XYZ convention. Yaw is gyro-relative and will drift over long periods because the Gemini 215 IMU has no magnetometer; this is normal and shown as an informational limitation in the viewer.

## Error Handling

- Show `uncalibrated` until calibration has enough stationary samples.
- Keep the last valid orientation if a packet has no gyro samples.
- Reject and count out-of-order timestamps rather than integrating them.
- Show a clear camera/SDK error and close Open3D cleanly on capture failure.
- Calibration fails with a visible reason when the camera moved too much during the sample window.

## Validation

Unit tests cover stationary calibration, gyro bias subtraction, a known 90-degree rotation, timestamp rejection, reset behavior, and roll/pitch/yaw conversion. Viewer tests use a fake renderer to verify the same transform is applied to the camera body and axes. A hardware smoke test requires 190--210 Hz IMU rate and visible orientation changes when the camera is rolled, pitched, and yawed by hand.

## Acceptance Criteria

- The viewer starts with Gemini 215 and displays a camera model at the origin.
- `C` calibrates a stationary camera and reports a stable orientation.
- A deliberate approximately 90-degree roll/pitch/yaw rotates the corresponding model axis coherently.
- No translation path or position claim is displayed.
- The viewer reports IMU rate and timestamp diagnostics throughout operation.
