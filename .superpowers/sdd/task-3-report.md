# Task 3 Report: Thread-Safe IMU Buffer and Packet Assembly

## Summary

Implemented `ImuBuffer` and wired live Orbbec IMU callbacks into `OrbbecCapture.read_packet()`.

## Files Changed

- Created `src/scanner_app/camera/imu_buffer.py`
- Modified `src/scanner_app/camera/orbbec_capture.py`
- Created `tests/test_imu_buffer.py`
- Modified `tests/test_orbbec_capture.py`

## TDD Evidence

### RED: Buffer import missing

Command:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe -m pytest tests\test_imu_buffer.py tests\test_orbbec_capture.py -q
```

Result:

```text
ERROR tests/test_imu_buffer.py
ModuleNotFoundError: No module named 'scanner_app.camera.imu_buffer'
1 error
```

### RED: Capture packet and IMU behavior missing

Command:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe -m pytest tests\test_orbbec_capture.py -q
```

Result:

```text
4 failed, 17 passed
AttributeError: 'OrbbecCapture' object has no attribute 'read_packet'
AssertionError: OrbbecCameraError not raised
AssertionError: None != 200
TypeError: 'NoneType' object is not callable
```

## Implementation Notes

- `ImuBuffer.push(sample)` and `pop_through(timestamp_us)` are guarded by a `threading.Lock`.
- Samples are kept sorted by `timestamp_us`; `pop_through()` returns samples at or before the cutoff and retains future samples.
- `OrbbecCapture.start()` now requires SDK IMU sensor types, gets gyro and accelerometer sensors, and starts both at `CaptureConfig.imu_hz`.
- IMU callbacks convert SDK frame/event methods `get_x()`, `get_y()`, `get_z()`, and `get_timestamp_us()` into real `ImuSample` instances.
- `OrbbecCapture.stop()` stops tracked IMU sensors and clears sensor state.
- `read()` remains compatible and still returns `RgbdFrame`; it now also records the latest color timestamp when available.
- `read_packet()` calls `read()`, requires color, uses the depth timestamp in microseconds, attaches actual color timestamp and popped IMU samples, and increments a per-capture sequence counter.
- No fake IMU packet content was added to production code.
- No runtime dependencies were added.

## Verification

Focused required check:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe -m pytest tests\test_imu_buffer.py tests\test_orbbec_capture.py -q
```

Result:

```text
23 passed in 0.27s
```

Broader focused check:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe -m pytest tests\test_camera_models.py tests\test_imu_buffer.py tests\test_orbbec_capture.py tests\test_pointcloud_generation.py -q
```

Result:

```text
28 passed in 0.31s
```

## Concerns

- The test fake models the IMU sensor start API as `start(callback, sample_rate_hz)`. The implementation also falls back to `set_sample_rate(sample_rate_hz)` plus `start(callback)` when the SDK exposes that shape.
