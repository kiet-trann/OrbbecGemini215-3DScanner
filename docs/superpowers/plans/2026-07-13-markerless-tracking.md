# Markerless Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce accepted metric camera poses and RGB-D keyframes from Gemini 215 packets without markers.

**Architecture:** IMU predicts rotation only. Open3D RGB-D odometry refines with point-to-plane ICP; a quality gate controls pose composition and keyframes. The benchmark accepts replay packets or live capture.

**Tech Stack:** Python 3.10+, NumPy, SciPy, OpenCV, Open3D 0.18+, pytest.

## Global Constraints

- Use Close-Up Precision Mode at 0.20-0.30 m during one scan pass.
- Use existing `SynchronizedFramePacket`, `ProcessedDepth`, and `CameraIntrinsics` contracts.
- Track at 640x400; retain original packets as keyframes.
- Require fitness >= 0.35, RMSE <= 0.004 m, translation <= 0.050 m, rotation <= 15 degrees, and timestamp gap <= 200 ms.
- Create a keyframe at first acceptance, 0.005 m translation, 3 degrees rotation, or 200 ms elapsed.

---

### Task 1: Tracking Contracts and IMU Prior

**Files:**
- Create: `src/scanner_app/tracking/models.py`
- Create: `src/scanner_app/tracking/imu.py`
- Test: `tests/test_imu_tracking.py`

**Interfaces:** Consumes `tuple[ImuSample, ...]`. Produces `TrackingState`, `TrackingMetrics`, `TrackingResult`, and `ImuEstimator`.

- [ ] **Step 1: Write failing tests**

```python
def test_calibration_removes_constant_gyro_bias() -> None:
    estimator = ImuEstimator()
    estimator.calibrate(tuple(ImuSample("gyro", i * 5_000, np.array([0, 0, .01])) for i in range(400)))
    rotation = estimator.predict_rotation((ImuSample("gyro", 2_000_000, np.array([0, 0, .01])), ImuSample("gyro", 2_005_000, np.array([0, 0, .01]))))
    np.testing.assert_allclose(rotation, np.eye(3), atol=1e-6)
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_imu_tracking.py -q`

Expected: missing `scanner_app.tracking.imu`.

- [ ] **Step 3: Implement contracts and integration**

```python
class TrackingState(Enum):
    INITIALIZING = "initializing"; TRACKING = "tracking"; DEGRADED = "degraded"; LOST = "lost"

@dataclass(frozen=True)
class TrackingMetrics:
    fitness: float; rmse_m: float; translation_m: float; rotation_deg: float; depth_valid_ratio: float
```

`ImuEstimator` stores mean stationary gyro bias, returns identity for fewer than two gyro samples, and composes bias-corrected `Rotation.from_rotvec(omega * dt)` in timestamp order.

- [ ] **Step 4: Verify GREEN and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_imu_tracking.py -q`

Expected: PASS.

Commit: `git add src/scanner_app/tracking/models.py src/scanner_app/tracking/imu.py tests/test_imu_tracking.py; git commit -m "feat: add markerless tracking contracts and IMU prior"`

---

### Task 2: Quality Gate and Keyframes

**Files:**
- Create: `src/scanner_app/tracking/quality.py`
- Create: `src/scanner_app/tracking/keyframes.py`
- Test: `tests/test_tracking_quality.py`
- Test: `tests/test_keyframes.py`

**Interfaces:** Consumes candidate transforms, metrics, timestamps, and packets. Produces `TrackingQualityGate.evaluate()` and `KeyframeStore.consider()`.

- [ ] **Step 1: Write failing tests**

```python
def test_quality_gate_rejects_large_rotation() -> None:
    gate = TrackingQualityGate()
    result = gate.evaluate(np.eye(4), TrackingMetrics(.8, .001, .001, 16.0, .9), 1_000)
    assert not result.accepted
    assert result.reason == "rotation exceeds 15.0 deg"

def test_keyframe_store_accepts_translation_threshold() -> None:
    store = KeyframeStore()
    assert store.consider(packet(0), np.eye(4), metrics()) is not None
    moved = np.eye(4); moved[0, 3] = .005
    assert store.consider(packet(1), moved, metrics()) is not None
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_tracking_quality.py tests\test_keyframes.py -q`

Expected: missing modules.

- [ ] **Step 3: Implement gate and immutable keyframes**

```python
@dataclass(frozen=True)
class Keyframe:
    packet: SynchronizedFramePacket
    camera_to_world: np.ndarray
    metrics: TrackingMetrics
```

Evaluate limits in deterministic order. A failed gate is `DEGRADED`; three consecutive failures are `LOST`; accepted estimates reset the count. Keep original packet references only for accepted threshold-crossing frames.

- [ ] **Step 4: Verify GREEN and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_tracking_quality.py tests\test_keyframes.py -q`

Expected: PASS.

Commit: `git add src/scanner_app/tracking/quality.py src/scanner_app/tracking/keyframes.py tests/test_tracking_quality.py tests/test_keyframes.py; git commit -m "feat: gate markerless poses and retain keyframes"`

---

### Task 3: RGB-D Odometry Adapter

**Files:**
- Create: `src/scanner_app/tracking/rgbd_odometry.py`
- Test: `tests/test_rgbd_odometry.py`

**Interfaces:** Consumes two packets, their `ProcessedDepth`, intrinsics, and a 3x3 IMU rotation. Produces `OdometryEstimate(relative_transform, fitness, rmse_m, depth_valid_ratio)`.

- [ ] **Step 1: Write failing tests**

```python
def test_scale_tracking_intrinsics_preserves_projection_center() -> None:
    source = CameraIntrinsics(800, 600, 640, 400, 1280, 800)
    assert scale_tracking_intrinsics(source, 640, 400) == CameraIntrinsics(400, 300, 320, 200, 640, 400)

def test_adapter_passes_imu_rotation_as_initial_transform() -> None:
    backend = FakeBackend()
    RgbdOdometryAdapter(intrinsics(), backend).estimate(previous(), previous_depth(), current(), current_depth(), rotation_z_90())
    np.testing.assert_allclose(backend.initial_transform[:3, :3], rotation_z_90())
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_rgbd_odometry.py -q`

Expected: missing module.

- [ ] **Step 3: Implement injected Open3D backend**

Resize BGR-to-RGB and metric depth with OpenCV to 640x400. Build a 4x4 initial transform from IMU rotation, run RGB-D odometry then three point-to-plane ICP scales. Keep Open3D behind a backend so tests use `FakeBackend` without hardware.

- [ ] **Step 4: Verify GREEN and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_rgbd_odometry.py -q`

Expected: PASS.

Commit: `git add src/scanner_app/tracking/rgbd_odometry.py tests/test_rgbd_odometry.py; git commit -m "feat: estimate markerless RGB-D motion"`

---

### Task 4: Tracker Orchestration and Benchmark

**Files:**
- Create: `src/scanner_app/tracking/markerless.py`
- Create: `scripts/13_markerless_tracking.py`
- Create: `tests/test_markerless_tracker.py`
- Create: `tests/test_markerless_tracking_script.py`
- Modify: `README.md`

**Interfaces:** Consumes Tasks 1-3, `DepthProcessor`, `SessionReplay`, and `OrbbecCapture`. Produces `MarkerlessTracker.process(packet)` and a live/replay CLI.

- [ ] **Step 1: Write failing integration tests**

```python
def test_tracker_composes_only_accepted_relative_motion() -> None:
    tracker = MarkerlessTracker(intrinsics(), odometry=FakeOdometry(translation=.01))
    assert tracker.process(packet(0)).accepted
    second = tracker.process(packet(1))
    assert second.accepted
    assert second.camera_to_world[0, 3] == pytest.approx(.01)
```

- [ ] **Step 2: Verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_markerless_tracker.py tests\test_markerless_tracking_script.py -q`

Expected: missing tracker and script.

- [ ] **Step 3: Implement composition and cleanup**

The first valid packet becomes identity. Later packets follow `DepthProcessor -> ImuEstimator -> RgbdOdometryAdapter -> TrackingQualityGate`; compose accepted motion with `camera_to_world @ inverse(relative_transform)` and invoke `KeyframeStore` after acceptance. The script accepts either `--replay SESSION_DIR` or live capture, prints compact JSON per result, and stops capture in `finally`.

- [ ] **Step 4: Verify integration, regression, and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_markerless_tracker.py tests\test_markerless_tracking_script.py -q`

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests PASS.

Commit: `git add src/scanner_app/tracking/markerless.py scripts/13_markerless_tracking.py tests/test_markerless_tracker.py tests/test_markerless_tracking_script.py README.md; git commit -m "feat: run markerless tracking benchmark"`

## Phase Verification

Run `.\.venv\Scripts\python.exe scripts\13_markerless_tracking.py` while moving slowly around the milk carton at 0.20-0.30 m. Accept this phase only at >=15 accepted updates/second without an unrecovered loss; preserve the session for TSDF fusion.
