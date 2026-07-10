# Capture and Hardware Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver explicit 30 FPS synchronized RGB-D capture, 200 Hz IMU packets, objective depth quality metrics, deterministic replay, and a controlled Gemini 215 hardware qualification command.

**Architecture:** Keep the existing `OrbbecCapture` compatibility API while moving shared frame types into a focused models module. RGB-D remains on the pipeline with full-frame aggregation; gyro and accelerometer use sensor callbacks feeding a timestamped buffer. Processing and recording consume immutable synchronized packets and never block capture.

**Tech Stack:** Python 3.10+, NumPy, OpenCV, pyorbbecsdk2 2.x, pytest/unittest, standard-library threading and queues.

## Global Constraints

- Object size: 5-30 cm.
- Normal camera distance: 0.20-0.40 m; hard depth gate: 0.15-0.50 m.
- Camera mode: Close_Up Precision Mode.
- Depth: 1280x800 Y16 at 30 FPS.
- Color: 1280x720 RGB at 30 FPS.
- IMU: gyroscope and accelerometer at 200 Hz.
- Windows and Python 3.10 or newer.
- Preserve all existing marker-based scripts and tests.
- Do not add a new runtime dependency in this phase.
- `rtk` is not installed on the current machine; use the direct commands below.

## File Map

- Create `src/scanner_app/camera/models.py`: immutable capture data contracts.
- Modify `src/scanner_app/camera/orbbec_capture.py`: explicit profiles, sync, IMU callbacks, packet API.
- Create `src/scanner_app/camera/imu_buffer.py`: thread-safe IMU timestamp buffer.
- Create `src/scanner_app/processing/depth_pipeline.py`: metric conversion, range filter, and quality metrics.
- Create `src/scanner_app/processing/object_roi.py`: central-depth object center and bounded world ROI.
- Create `src/scanner_app/recording/__init__.py`: recording package marker.
- Create `src/scanner_app/recording/session.py`: asynchronous packet/keyframe recorder and replay reader.
- Create `scripts/12_hardware_qualification.py`: controlled live benchmark CLI.
- Modify `tests/test_orbbec_capture.py`: explicit profile and sync contract tests.
- Create `tests/test_camera_models.py`, `tests/test_imu_buffer.py`, `tests/test_depth_pipeline.py`, `tests/test_session_recording.py`, and `tests/test_hardware_qualification_script.py`.

---

### Task 1: Stable Capture Data Contracts

**Files:**
- Create: `src/scanner_app/camera/models.py`
- Modify: `src/scanner_app/camera/orbbec_capture.py`
- Test: `tests/test_camera_models.py`

**Interfaces:**
- Consumes: NumPy arrays from the SDK adapter.
- Produces: `CameraIntrinsics`, `RgbdFrame`, `ImuSample`, `SynchronizedFramePacket`, and `CaptureConfig` used by every later plan.

- [ ] **Step 1: Write the failing model test**

```python
import numpy as np

from scanner_app.camera.models import (
    CameraIntrinsics,
    CaptureConfig,
    ImuSample,
    SynchronizedFramePacket,
)


def test_packet_exposes_metric_depth_and_immutable_imu_tuple() -> None:
    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.array([[100, 0], [250, 300]], dtype=np.uint16),
        depth_scale_mm=0.5,
        depth_timestamp_us=20_000,
        color_timestamp_us=19_990,
        imu_samples=(ImuSample("gyro", 19_995, np.array([1.0, 2.0, 3.0])),),
        sequence=7,
    )

    np.testing.assert_array_equal(
        packet.depth_m,
        np.array([[0.05, 0.0], [0.125, 0.15]], dtype=np.float32),
    )
    assert packet.sequence == 7
    assert CaptureConfig().depth_fps == 30
    assert CameraIntrinsics(1, 1, 0, 0, 2, 2).width == 2
```

- [ ] **Step 2: Run the test and verify the missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_camera_models.py -q`

Expected: FAIL with `ModuleNotFoundError: scanner_app.camera.models`.

- [ ] **Step 3: Add the contracts and compatibility imports**

```python
# src/scanner_app/camera/models.py
from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


@dataclass(frozen=True)
class RgbdFrame:
    color: np.ndarray | None
    depth: np.ndarray
    depth_scale: float
    timestamp_ms: float

    @property
    def depth_mm(self) -> np.ndarray:
        return self.depth.astype(np.float32) * float(self.depth_scale)


@dataclass(frozen=True)
class ImuSample:
    sensor: Literal["gyro", "accel"]
    timestamp_us: int
    xyz: np.ndarray


@dataclass(frozen=True)
class SynchronizedFramePacket:
    color_bgr: np.ndarray
    depth_raw: np.ndarray
    depth_scale_mm: float
    depth_timestamp_us: int
    color_timestamp_us: int
    imu_samples: tuple[ImuSample, ...]
    sequence: int

    @property
    def depth_m(self) -> np.ndarray:
        return self.depth_raw.astype(np.float32) * float(self.depth_scale_mm) * 0.001


@dataclass(frozen=True)
class CaptureConfig:
    depth_width: int = 1280
    depth_height: int = 800
    depth_fps: int = 30
    color_width: int = 1280
    color_height: int = 720
    color_fps: int = 30
    imu_hz: int = 200
```

Delete the duplicate dataclasses from `orbbec_capture.py` and import them there:

```python
from scanner_app.camera.models import (
    CameraIntrinsics,
    CaptureConfig,
    RgbdFrame,
    SynchronizedFramePacket,
)
```

- [ ] **Step 4: Run focused and legacy tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_camera_models.py tests/test_orbbec_capture.py tests/test_pointcloud_generation.py -q`

Expected: PASS with no import regressions.

- [ ] **Step 5: Commit the contracts**

```powershell
git add src/scanner_app/camera/models.py src/scanner_app/camera/orbbec_capture.py tests/test_camera_models.py
git commit -m "refactor: define synchronized capture models"
```

---

### Task 2: Explicit RGB-D Profiles and Frame Synchronization

**Files:**
- Modify: `src/scanner_app/camera/orbbec_capture.py`
- Modify: `tests/test_orbbec_capture.py`

**Interfaces:**
- Consumes: `CaptureConfig` from Task 1.
- Produces: a pipeline configured for exact 30 FPS profiles and `enable_frame_sync()`.

- [ ] **Step 1: Add a failing explicit-profile test**

```python
def test_start_uses_explicit_30_fps_rgbd_profiles_and_enables_sync() -> None:
    sdk = FakeSdk()
    capture = OrbbecCapture(sdk_module=sdk, capture_config=CaptureConfig())

    capture.start()

    assert sdk.pipeline.frame_sync_enabled
    assert (1280, 800, "y16", 30) in sdk.depth_profiles.requests
    assert (1280, 720, "rgb", 30) in sdk.color_profiles.requests
    assert sdk.device.selected_depth_mode == "Close_Up Precision Mode"
    assert capture.enabled_depth_filter_names == ("TemporalFilter",)
```

Extend the test fakes with separate profile lists, request recording, `OBFormat.Y16`,
and `FakePipeline.enable_frame_sync()`.

- [ ] **Step 2: Run the test and verify constructor/profile failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_orbbec_capture.py::OrbbecCaptureTests::test_start_uses_explicit_30_fps_rgbd_profiles_and_enables_sync -q`

Expected: FAIL because `capture_config` or `enable_frame_sync` is missing.

- [ ] **Step 3: Implement exact profile selection**

```python
# Add to OrbbecCapture.__init__
self._capture_config = capture_config or CaptureConfig()

# Replace default/wildcard selection in _build_stream_config
depth_profile = depth_profiles.get_video_stream_profile(
    self._capture_config.depth_width,
    self._capture_config.depth_height,
    sdk.OBFormat.Y16,
    self._capture_config.depth_fps,
)
color_profile = color_profiles.get_video_stream_profile(
    self._capture_config.color_width,
    self._capture_config.color_height,
    sdk.OBFormat.RGB,
    self._capture_config.color_fps,
)
config.enable_stream(depth_profile)
config.enable_stream(color_profile)
config.set_frame_aggregate_output_mode(sdk.OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)

# Immediately before pipeline.start(config)
device = self._pipeline.get_device()
modes = device.get_depth_work_mode_list()
close_up = next(
    modes.get_depth_work_mode_by_index(index)
    for index in range(modes.get_count())
    if modes.get_depth_work_mode_by_index(index).name == "Close_Up Precision Mode"
)
if device.get_depth_work_mode().name != close_up.name:
    device.set_depth_work_mode(close_up)

depth_sensor = device.get_sensor(sdk.OBSensorType.DEPTH_SENSOR)
self._depth_filters = tuple(
    depth_filter
    for depth_filter in depth_sensor.get_recommended_filters()
    if depth_filter.is_enabled()
)
self.enabled_depth_filter_names = tuple(
    depth_filter.get_name() for depth_filter in self._depth_filters
)

enable_sync = getattr(self._pipeline, "enable_frame_sync", None)
if enable_sync is not None:
    enable_sync()
```

Make `_build_stream_config` an instance method so it can use the immutable
configuration. Raise `OrbbecCameraError` instead of silently falling back when an
exact required profile or Close-Up mode is unavailable. In `read()`, apply every
enabled recommended filter before reading the depth data:

```python
for depth_filter in self._depth_filters:
    filtered = depth_filter.process(depth_frame)
    if filtered is None:
        raise OrbbecFrameError(f"Depth filter failed: {depth_filter.get_name()}")
    depth_frame = filtered.as_depth_frame()
```

- [ ] **Step 4: Run capture tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_orbbec_capture.py -q`

Expected: all capture tests PASS.

- [ ] **Step 5: Commit explicit synchronized capture**

```powershell
git add src/scanner_app/camera/orbbec_capture.py tests/test_orbbec_capture.py
git commit -m "feat: configure synchronized 30 fps RGB-D capture"
```

---

### Task 3: Thread-Safe IMU Buffer and Packet Assembly

**Files:**
- Create: `src/scanner_app/camera/imu_buffer.py`
- Modify: `src/scanner_app/camera/orbbec_capture.py`
- Test: `tests/test_imu_buffer.py`
- Modify: `tests/test_orbbec_capture.py`

**Interfaces:**
- Consumes: `ImuSample` and SDK gyro/accelerometer callbacks.
- Produces: `ImuBuffer.push(sample)`, `ImuBuffer.pop_through(timestamp_us)`, and `OrbbecCapture.read_packet()`.

- [ ] **Step 1: Write failing ordered-buffer tests**

```python
import numpy as np

from scanner_app.camera.imu_buffer import ImuBuffer
from scanner_app.camera.models import ImuSample


def test_pop_through_returns_ordered_samples_and_retains_future_samples() -> None:
    buffer = ImuBuffer()
    buffer.push(ImuSample("gyro", 30, np.ones(3)))
    buffer.push(ImuSample("accel", 10, np.zeros(3)))
    buffer.push(ImuSample("gyro", 20, np.full(3, 2.0)))

    assert [sample.timestamp_us for sample in buffer.pop_through(20)] == [10, 20]
    assert [sample.timestamp_us for sample in buffer.pop_through(40)] == [30]
```

- [ ] **Step 2: Verify the missing buffer failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_imu_buffer.py -q`

Expected: FAIL with missing `scanner_app.camera.imu_buffer`.

- [ ] **Step 3: Implement the buffer and packet API**

```python
# src/scanner_app/camera/imu_buffer.py
from threading import Lock

from scanner_app.camera.models import ImuSample


class ImuBuffer:
    def __init__(self) -> None:
        self._samples: list[ImuSample] = []
        self._lock = Lock()

    def push(self, sample: ImuSample) -> None:
        with self._lock:
            self._samples.append(sample)
            self._samples.sort(key=lambda item: item.timestamp_us)

    def pop_through(self, timestamp_us: int) -> tuple[ImuSample, ...]:
        with self._lock:
            split = 0
            while split < len(self._samples) and self._samples[split].timestamp_us <= timestamp_us:
                split += 1
            ready = tuple(self._samples[:split])
            del self._samples[:split]
            return ready
```

In `OrbbecCapture.start()`, start gyro and accelerometer sensors at 200 Hz with
callbacks that convert `get_x/get_y/get_z/get_timestamp_us` into `ImuSample`.
Stop those sensors in `stop()`. Add packet assembly:

```python
def read_packet(self) -> SynchronizedFramePacket:
    frame = self.read()
    depth_timestamp_us = int(round(frame.timestamp_ms * 1000.0))
    packet = SynchronizedFramePacket(
        color_bgr=frame.color,
        depth_raw=frame.depth,
        depth_scale_mm=frame.depth_scale,
        depth_timestamp_us=depth_timestamp_us,
        color_timestamp_us=self._last_color_timestamp_us,
        imu_samples=self._imu_buffer.pop_through(depth_timestamp_us),
        sequence=self._sequence,
    )
    self._sequence += 1
    return packet
```

Require color for `read_packet()` and raise `OrbbecFrameError` if it is absent.

- [ ] **Step 4: Run IMU and capture tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_imu_buffer.py tests/test_orbbec_capture.py -q`

Expected: PASS; fake sensor callbacks are stopped when capture stops.

- [ ] **Step 5: Commit IMU packet capture**

```powershell
git add src/scanner_app/camera/imu_buffer.py src/scanner_app/camera/orbbec_capture.py tests/test_imu_buffer.py tests/test_orbbec_capture.py
git commit -m "feat: attach synchronized IMU samples to RGB-D packets"
```

---

### Task 4: Depth Processing, Quality Metrics, and Object ROI

**Files:**
- Create: `src/scanner_app/processing/depth_pipeline.py`
- Create: `src/scanner_app/processing/object_roi.py`
- Test: `tests/test_depth_pipeline.py`
- Test: `tests/test_object_roi.py`

**Interfaces:**
- Consumes: `SynchronizedFramePacket`.
- Produces: `ProcessedDepth`, `DepthProcessor.process(packet)`, and `estimate_object_roi(processed_depth, intrinsics)`.

- [ ] **Step 1: Write failing range/coverage tests**

```python
import numpy as np

from scanner_app.camera.models import ImuSample, SynchronizedFramePacket
from scanner_app.processing.depth_pipeline import DepthProcessor


def test_depth_processor_applies_metric_range_and_reports_coverage() -> None:
    packet = SynchronizedFramePacket(
        color_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        depth_raw=np.array([[100, 200], [400, 600]], dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=1,
        color_timestamp_us=1,
        imu_samples=tuple(),
        sequence=0,
    )

    result = DepthProcessor(min_depth_m=0.15, max_depth_m=0.50).process(packet)

    np.testing.assert_array_equal(
        result.depth_m,
        np.array([[0.0, 0.2], [0.4, 0.0]], dtype=np.float32),
    )
    assert result.valid_ratio == 0.5
    assert result.median_depth_m == 0.3
```

```python
from scanner_app.camera.models import CameraIntrinsics
from scanner_app.processing.object_roi import estimate_object_roi


def test_object_roi_centers_on_median_central_depth() -> None:
    depth = np.zeros((10, 10), dtype=np.float32)
    depth[4:6, 4:6] = 0.30
    processed = ProcessedDepth(depth, depth > 0, 0.04, 0.30)
    intrinsics = CameraIntrinsics(100.0, 100.0, 5.0, 5.0, 10, 10)

    roi = estimate_object_roi(processed, intrinsics, extent_m=0.35)

    np.testing.assert_allclose(roi.center_camera_m, [0.0, 0.0, 0.30], atol=0.002)
    np.testing.assert_allclose(roi.max_bound - roi.min_bound, [0.35] * 3)
```

- [ ] **Step 2: Verify the missing processor failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_depth_pipeline.py -q`

Expected: FAIL with missing `depth_pipeline`.

- [ ] **Step 3: Implement deterministic metric processing**

```python
from dataclasses import dataclass

import numpy as np

from scanner_app.camera.models import SynchronizedFramePacket


@dataclass(frozen=True)
class ProcessedDepth:
    depth_m: np.ndarray
    valid_mask: np.ndarray
    valid_ratio: float
    median_depth_m: float | None


class DepthProcessor:
    def __init__(self, min_depth_m: float = 0.15, max_depth_m: float = 0.50) -> None:
        if min_depth_m <= 0 or min_depth_m >= max_depth_m:
            raise ValueError("Depth range must satisfy 0 < min < max.")
        self.min_depth_m = float(min_depth_m)
        self.max_depth_m = float(max_depth_m)

    def process(self, packet: SynchronizedFramePacket) -> ProcessedDepth:
        depth_m = packet.depth_m
        valid = (depth_m >= self.min_depth_m) & (depth_m <= self.max_depth_m)
        filtered = np.where(valid, depth_m, 0.0).astype(np.float32)
        median = float(np.median(filtered[valid])) if np.any(valid) else None
        return ProcessedDepth(filtered, valid, float(np.mean(valid)), median)
```

```python
# src/scanner_app/processing/object_roi.py
@dataclass(frozen=True)
class ObjectRoi:
    center_camera_m: np.ndarray
    min_bound: np.ndarray
    max_bound: np.ndarray


def estimate_object_roi(processed, intrinsics, extent_m=0.35):
    height, width = processed.depth_m.shape
    y0, y1 = int(height * 0.4), int(height * 0.6)
    x0, x1 = int(width * 0.4), int(width * 0.6)
    central = processed.depth_m[y0:y1, x0:x1]
    valid = central[central > 0]
    if valid.size < 20:
        raise ValueError("At least 20 valid central depth pixels are required.")
    z = float(np.median(valid))
    u, v = 0.5 * (x0 + x1 - 1), 0.5 * (y0 + y1 - 1)
    center = np.array([
        (u - intrinsics.cx) * z / intrinsics.fx,
        (v - intrinsics.cy) * z / intrinsics.fy,
        z,
    ])
    half = 0.5 * float(extent_m)
    return ObjectRoi(center, center - half, center + half)
```

SDK recommended filters are applied in the capture adapter before NumPy
conversion; expose their enabled names in capture metadata and keep this class
deterministic for replay.

- [ ] **Step 4: Run processing and legacy depth tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_depth_pipeline.py tests/test_object_roi.py tests/test_depth_processing.py -q`

Expected: PASS.

- [ ] **Step 5: Commit depth metrics**

```powershell
git add src/scanner_app/processing/depth_pipeline.py src/scanner_app/processing/object_roi.py tests/test_depth_pipeline.py tests/test_object_roi.py
git commit -m "feat: add depth quality and object ROI processing"
```

---

### Task 5: Deterministic Session Recording and Replay

**Files:**
- Create: `src/scanner_app/recording/__init__.py`
- Create: `src/scanner_app/recording/session.py`
- Test: `tests/test_session_recording.py`

**Interfaces:**
- Consumes: `SynchronizedFramePacket`, calibration/config metadata, and full-resolution keyframes.
- Produces: `SessionRecorder.submit(packet)`, `SessionRecorder.close()`, and `SessionReplay.packets()`.

- [ ] **Step 1: Write a failing round-trip test**

```python
import numpy as np

from scanner_app.camera.models import SynchronizedFramePacket
from scanner_app.recording.session import SessionRecorder, SessionReplay


def test_recorded_packet_replays_without_numeric_loss(tmp_path) -> None:
    packet = SynchronizedFramePacket(
        color_bgr=np.arange(12, dtype=np.uint8).reshape(2, 2, 3),
        depth_raw=np.array([[1, 2], [3, 4]], dtype=np.uint16),
        depth_scale_mm=1.0,
        depth_timestamp_us=100,
        color_timestamp_us=95,
        imu_samples=tuple(),
        sequence=3,
    )
    recorder = SessionRecorder(tmp_path)
    recorder.submit(packet)
    recorder.close()

    replayed = list(SessionReplay(tmp_path).packets())

    assert len(replayed) == 1
    np.testing.assert_array_equal(replayed[0].depth_raw, packet.depth_raw)
    np.testing.assert_array_equal(replayed[0].color_bgr, packet.color_bgr)
```

- [ ] **Step 2: Verify the missing recording package failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_session_recording.py -q`

Expected: FAIL with missing `scanner_app.recording`.

- [ ] **Step 3: Implement bounded asynchronous recording**

```python
# Core of src/scanner_app/recording/session.py
from pathlib import Path
from queue import Queue
from threading import Thread

import numpy as np

from scanner_app.camera.models import SynchronizedFramePacket


class SessionRecorder:
    def __init__(self, root: Path, queue_size: int = 64) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._queue: Queue[SynchronizedFramePacket | None] = Queue(queue_size)
        self._worker = Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, packet: SynchronizedFramePacket) -> None:
        self._queue.put(packet, timeout=1.0)

    def close(self) -> None:
        self._queue.put(None)
        self._worker.join()

    def _run(self) -> None:
        while True:
            packet = self._queue.get()
            if packet is None:
                return
            np.savez_compressed(
                self.root / f"packet_{packet.sequence:08d}.npz",
                color_bgr=packet.color_bgr,
                depth_raw=packet.depth_raw,
                depth_scale_mm=packet.depth_scale_mm,
                depth_timestamp_us=packet.depth_timestamp_us,
                color_timestamp_us=packet.color_timestamp_us,
                imu_sensor=np.asarray([sample.sensor for sample in packet.imu_samples]),
                imu_timestamp_us=np.asarray(
                    [sample.timestamp_us for sample in packet.imu_samples], dtype=np.int64
                ),
                imu_xyz=np.asarray(
                    [sample.xyz for sample in packet.imu_samples], dtype=np.float64
                ).reshape(-1, 3),
            )


class SessionReplay:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def packets(self):
        for path in sorted(self.root.glob("packet_*.npz")):
            with np.load(path) as payload:
                imu_samples = tuple(
                    ImuSample(str(sensor), int(timestamp), xyz.copy())
                    for sensor, timestamp, xyz in zip(
                        payload["imu_sensor"],
                        payload["imu_timestamp_us"],
                        payload["imu_xyz"],
                    )
                )
                yield SynchronizedFramePacket(
                    color_bgr=payload["color_bgr"],
                    depth_raw=payload["depth_raw"],
                    depth_scale_mm=float(payload["depth_scale_mm"]),
                    depth_timestamp_us=int(payload["depth_timestamp_us"]),
                    color_timestamp_us=int(payload["color_timestamp_us"]),
                    imu_samples=imu_samples,
                    sequence=int(path.stem.split("_")[-1]),
                )
```

Import `ImuSample` beside `SynchronizedFramePacket`. In `SessionRecorder.__init__`,
write `metadata.json` from a required metadata dictionary containing capture
config, calibration, device name, serial, SDK version, and firmware. Change
`submit()` to catch `queue.Full` and raise `SessionRecordingError("Recorder queue
is full")`; replay data must never be silently dropped.

- [ ] **Step 4: Run the round-trip test and full unit suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_session_recording.py -q`

Expected: PASS with the worker fully joined and all packet files readable.

- [ ] **Step 5: Commit recording/replay**

```powershell
git add src/scanner_app/recording tests/test_session_recording.py
git commit -m "feat: record and replay synchronized scan packets"
```

---

### Task 6: Hardware Qualification Command and Gate

**Files:**
- Create: `scripts/12_hardware_qualification.py`
- Test: `tests/test_hardware_qualification_script.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `OrbbecCapture.read_packet()` and `DepthProcessor`.
- Produces: `QualificationReport` JSON plus exit code 0 on pass and 1 on failure.

- [ ] **Step 1: Write failing metric-evaluation tests**

```python
from scripts_12_hardware_qualification import evaluate_metrics


def test_qualification_requires_all_hardware_thresholds() -> None:
    report = evaluate_metrics(
        rgbd_fps=25.5,
        imu_hz=199.0,
        object_valid_ratio=0.75,
        median_noise_mm=0.8,
        p90_noise_mm=1.7,
    )
    assert report.passed

    failed = evaluate_metrics(25.5, 199.0, 0.60, 0.8, 1.7)
    assert not failed.passed
    assert "object_valid_ratio" in failed.failures
```

Load the numbered script with the same `importlib.util` pattern used by existing
script tests; name the loaded module `scripts_12_hardware_qualification`.

- [ ] **Step 2: Verify the script is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_hardware_qualification_script.py -q`

Expected: FAIL because `scripts/12_hardware_qualification.py` does not exist.

- [ ] **Step 3: Implement fixed acceptance thresholds and JSON output**

```python
@dataclass(frozen=True)
class QualificationReport:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, float]


def evaluate_metrics(
    rgbd_fps: float,
    imu_hz: float,
    object_valid_ratio: float,
    median_noise_mm: float,
    p90_noise_mm: float,
) -> QualificationReport:
    metrics = locals().copy()
    limits = {
        "rgbd_fps": rgbd_fps >= 24.0,
        "imu_hz": 190.0 <= imu_hz <= 210.0,
        "object_valid_ratio": object_valid_ratio >= 0.70,
        "median_noise_mm": median_noise_mm <= 1.0,
        "p90_noise_mm": p90_noise_mm <= 2.0,
    }
    failures = tuple(name for name, passed in limits.items() if not passed)
    return QualificationReport(not failures, failures, metrics)
```

The CLI runs a 10-second warm-up, asks for static captures at 0.20/0.30/0.40 m,
uses a central object mask, writes `data/sessions/qualification_<timestamp>.json`,
prints every measured threshold, and exits nonzero on failure. Add the exact run
command and controlled matte-target instructions to `README.md`.

- [ ] **Step 4: Run software verification, then the hardware gate**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_hardware_qualification_script.py tests/test_orbbec_capture.py tests/test_depth_pipeline.py -q`

Expected: PASS.

Hardware run: `.\.venv\Scripts\python.exe scripts\12_hardware_qualification.py`

Expected: a JSON report with all five metrics and explicit PASS/FAIL. Do not
proceed to the tracking plan until PASS, or until every corrective hardware check
in the design spec has been exhausted and documented.

- [ ] **Step 5: Commit the qualification gate**

```powershell
git add scripts/12_hardware_qualification.py tests/test_hardware_qualification_script.py README.md
git commit -m "feat: add Gemini 215 hardware qualification gate"
```

## Phase Completion Check

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all unit tests PASS. Attach the hardware qualification JSON to the
implementation report. Phase 2 is authorized only when synchronized capture,
IMU rate, depth coverage, and temporal noise meet the approved thresholds.
