# Markerless Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce stable markerless camera poses from replayed or live Gemini 215 RGB-D and IMU packets, including quality rejection, keyframes, relocalization, and optimized pose graphs.

**Architecture:** Use a two-second stationary IMU calibration and gyro rotation prediction to initialize coarse-to-fine Open3D RGB-D odometry, then refine with multi-scale point-to-plane ICP. A separate quality gate controls the state machine and keyframe store. ORB/depth PnP plus ICP performs relocalization and verifies non-sequential pose-graph edges.

**Tech Stack:** Python 3.10+, NumPy, SciPy Rotation, OpenCV ORB/PnP, Open3D 0.18+, pytest/unittest.

## Global Constraints

- Phase 1 hardware qualification must PASS before live tuning.
- Tracking operates on 640x400 RGB-D pyramids.
- Pose tracking target: at least 15 FPS.
- Live quality limits: ICP fitness >= 0.35 and RMSE <= 4 mm.
- Per-frame motion limits: translation <= 50 mm and rotation <= 15 degrees.
- Keyframe thresholds: 5 mm, 3 degrees, or 200 ms.
- Optimized 360-degree loop-end position error target: <= 3 mm.
- Preserve marker-based tracking as a separate diagnostic path.
- No RTAB-Map dependency in this plan.
- `rtk` is unavailable; use the direct commands below.

## File Map

- Create `src/scanner_app/tracking/models.py`: tracking states and result contracts.
- Create `src/scanner_app/tracking/imu.py`: bias calibration and rotation prediction.
- Create `src/scanner_app/tracking/rgbd_odometry.py`: Open3D odometry and ICP adapter.
- Create `src/scanner_app/tracking/quality.py`: acceptance gate and state transitions.
- Create `src/scanner_app/tracking/keyframes.py`: keyframe policy and storage.
- Create `src/scanner_app/tracking/markerless.py`: tracker orchestration.
- Create `src/scanner_app/tracking/relocalization.py`: ORB/depth PnP and ICP recovery.
- Create `src/scanner_app/tracking/pose_graph.py`: graph edges and optimization.
- Create `scripts/13_markerless_tracking.py`: replay/live tracking benchmark.
- Create matching focused test files under `tests/`.

---

### Task 1: Tracking Contracts and IMU Rotation Prediction

**Files:**
- Create: `src/scanner_app/tracking/models.py`
- Create: `src/scanner_app/tracking/imu.py`
- Test: `tests/test_imu_tracking.py`

**Interfaces:**
- Consumes: `tuple[ImuSample, ...]` from Phase 1.
- Produces: `TrackingState`, `TrackingMetrics`, `TrackingResult`, `PoseTracker` protocol, and `ImuEstimator.predict_rotation(samples)`.

- [ ] **Step 1: Write failing bias and prediction tests**

```python
import numpy as np

from scanner_app.camera.models import ImuSample
from scanner_app.tracking.imu import ImuEstimator


def test_stationary_calibration_removes_constant_gyro_bias() -> None:
    estimator = ImuEstimator()
    samples = tuple(
        ImuSample("gyro", index * 5_000, np.array([0.0, 0.0, 0.01]))
        for index in range(400)
    ) + tuple(
        ImuSample("accel", index * 5_000, np.array([0.0, -9.81, 0.0]))
        for index in range(400)
    )
    estimator.calibrate(samples)

    rotation = estimator.predict_rotation(
        (
            ImuSample("gyro", 2_000_000, np.array([0.0, 0.0, 0.01])),
            ImuSample("gyro", 2_005_000, np.array([0.0, 0.0, 0.01])),
        )
    )

    np.testing.assert_allclose(rotation, np.eye(3), atol=1e-6)


def test_stationary_calibration_estimates_gravity_direction() -> None:
    estimator = ImuEstimator()
    samples = tuple(
        ImuSample("accel", index * 5_000, np.array([0.0, -9.81, 0.0]))
        for index in range(400)
    ) + tuple(
        ImuSample("gyro", index * 5_000, np.zeros(3))
        for index in range(400)
    )
    estimator.calibrate(samples)
    np.testing.assert_allclose(estimator.gravity_direction, [0.0, -1.0, 0.0])
```

- [ ] **Step 2: Verify missing IMU tracker failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_imu_tracking.py -q`

Expected: FAIL with missing `scanner_app.tracking.imu`.

- [ ] **Step 3: Implement contracts and midpoint gyro integration**

```python
# src/scanner_app/tracking/models.py
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np


class TrackingState(Enum):
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    DEGRADED = "degraded"
    LOST = "lost"


@dataclass(frozen=True)
class TrackingMetrics:
    fitness: float
    rmse_m: float
    translation_m: float
    rotation_deg: float
    processing_ms: float


@dataclass(frozen=True)
class TrackingResult:
    state: TrackingState
    camera_to_world: np.ndarray
    metrics: TrackingMetrics
    accepted: bool
    keyframe: bool
    reason: str | None = None


class PoseTracker(Protocol):
    def initialize(self, packet, processed_depth) -> TrackingResult: ...
    def track(self, packet, processed_depth) -> TrackingResult: ...
```

```python
# src/scanner_app/tracking/imu.py
import numpy as np
from scipy.spatial.transform import Rotation

from scanner_app.camera.models import ImuSample


class ImuEstimator:
    def __init__(self) -> None:
        self.gyro_bias = np.zeros(3, dtype=np.float64)
        self.gravity_direction = np.array([0.0, -1.0, 0.0], dtype=np.float64)

    def calibrate(self, samples: tuple[ImuSample, ...]) -> None:
        gyro = [sample.xyz for sample in samples if sample.sensor == "gyro"]
        accel = [sample.xyz for sample in samples if sample.sensor == "accel"]
        if len(gyro) < 100:
            raise ValueError("At least 100 stationary gyro samples are required.")
        if len(accel) < 100:
            raise ValueError("At least 100 stationary accelerometer samples are required.")
        self.gyro_bias = np.mean(np.asarray(gyro, dtype=np.float64), axis=0)
        gravity = np.mean(np.asarray(accel, dtype=np.float64), axis=0)
        self.gravity_direction = gravity / np.linalg.norm(gravity)

    def predict_rotation(self, samples: tuple[ImuSample, ...]) -> np.ndarray:
        gyro = [sample for sample in samples if sample.sensor == "gyro"]
        rotation = Rotation.identity()
        for first, second in zip(gyro, gyro[1:]):
            dt = (second.timestamp_us - first.timestamp_us) * 1e-6
            omega = 0.5 * (first.xyz + second.xyz) - self.gyro_bias
            rotation = rotation * Rotation.from_rotvec(omega * dt)
        return rotation.as_matrix()
```

- [ ] **Step 4: Run the IMU tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_imu_tracking.py -q`

Expected: PASS, including a negative test for fewer than 100 calibration samples.

- [ ] **Step 5: Commit IMU prediction**

```powershell
git add src/scanner_app/tracking/models.py src/scanner_app/tracking/imu.py tests/test_imu_tracking.py
git commit -m "feat: add calibrated IMU rotation prediction"
```

---

### Task 2: RGB-D Odometry and Multi-Scale ICP Adapter

**Files:**
- Create: `src/scanner_app/tracking/rgbd_odometry.py`
- Test: `tests/test_rgbd_odometry.py`

**Interfaces:**
- Consumes: consecutive BGR/depth frames, depth intrinsics, and an IMU initial transform.
- Produces: `OdometryEstimate(relative_transform, fitness, rmse_m, success)`.

- [ ] **Step 1: Write a failing transform-seed test with an injectable backend**

```python
import numpy as np

from scanner_app.tracking.rgbd_odometry import RgbdOdometry


class FakeBackend:
    def estimate(self, source, target, intrinsics, initial):
        return True, initial.copy(), 0.8, 0.001


def test_odometry_passes_imu_seed_to_backend() -> None:
    seed = np.eye(4)
    seed[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    tracker = RgbdOdometry(backend=FakeBackend())

    estimate = tracker.estimate(object(), object(), object(), seed)

    assert estimate.success
    np.testing.assert_allclose(estimate.relative_transform, seed)
    assert estimate.fitness == 0.8
```

- [ ] **Step 2: Verify missing odometry module failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_rgbd_odometry.py -q`

Expected: FAIL with missing `rgbd_odometry`.

- [ ] **Step 3: Implement the adapter and Open3D backend**

```python
from dataclasses import dataclass

import numpy as np
import open3d as o3d


@dataclass(frozen=True)
class OdometryEstimate:
    relative_transform: np.ndarray
    fitness: float
    rmse_m: float
    success: bool


class RgbdOdometry:
    def __init__(self, backend=None) -> None:
        self.backend = backend or Open3dOdometryBackend()

    def estimate(self, source, target, intrinsics, initial) -> OdometryEstimate:
        success, transform, fitness, rmse = self.backend.estimate(
            source, target, intrinsics, initial
        )
        return OdometryEstimate(transform, float(fitness), float(rmse), bool(success))


class Open3dOdometryBackend:
    def estimate(self, source, target, intrinsics, initial):
        success, transform, _ = o3d.pipelines.odometry.compute_rgbd_odometry(
            source,
            target,
            intrinsics,
            initial,
            o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm(),
            o3d.pipelines.odometry.OdometryOption(depth_diff_max=0.03),
        )
        if not success:
            return False, initial, 0.0, float("inf")
        source_cloud = o3d.geometry.PointCloud.create_from_rgbd_image(source, intrinsics)
        target_cloud = o3d.geometry.PointCloud.create_from_rgbd_image(target, intrinsics)
        for cloud in (source_cloud, target_cloud):
            cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.01, max_nn=30))
        result = o3d.pipelines.registration.registration_icp(
            source_cloud,
            target_cloud,
            0.01,
            transform,
            o3d.pipelines.registration.TransformationEstimationPointToPlane(),
        )
        return True, result.transformation, result.fitness, result.inlier_rmse


def make_tracking_rgbd(packet, processed_depth):
    color_rgb = cv2.cvtColor(packet.color_bgr, cv2.COLOR_BGR2RGB)
    color_rgb = cv2.resize(color_rgb, (640, 400), interpolation=cv2.INTER_AREA)
    depth_m = cv2.resize(
        processed_depth.depth_m, (640, 400), interpolation=cv2.INTER_NEAREST
    ).astype(np.float32)
    return o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(np.ascontiguousarray(color_rgb)),
        o3d.geometry.Image(np.ascontiguousarray(depth_m)),
        depth_scale=1.0,
        depth_trunc=0.50,
        convert_rgb_to_intensity=False,
    )


def scale_tracking_intrinsics(intrinsics):
    sx = 640.0 / intrinsics.width
    sy = 400.0 / intrinsics.height
    return o3d.camera.PinholeCameraIntrinsic(
        640,
        400,
        intrinsics.fx * sx,
        intrinsics.fy * sy,
        intrinsics.cx * sx,
        intrinsics.cy * sy,
    )
```

Test both helpers with synthetic arrays and intrinsics. Run ICP at 4 mm and 2 mm
voxel levels with 10 mm and 5 mm correspondence distances respectively.

- [ ] **Step 4: Run synthetic odometry tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_rgbd_odometry.py -q`

Expected: PASS for backend injection, metric depth conversion, and a synthetic
point-cloud translation within 0.5 mm.

- [ ] **Step 5: Commit odometry and ICP**

```powershell
git add src/scanner_app/tracking/rgbd_odometry.py tests/test_rgbd_odometry.py
git commit -m "feat: add RGB-D odometry and ICP refinement"
```

---

### Task 3: Quality Gate, State Transitions, and Keyframes

**Files:**
- Create: `src/scanner_app/tracking/quality.py`
- Create: `src/scanner_app/tracking/keyframes.py`
- Test: `tests/test_tracking_quality.py`
- Test: `tests/test_keyframes.py`

**Interfaces:**
- Consumes: `OdometryEstimate`, previous state, pose delta, and timestamps.
- Produces: `QualityDecision` and `KeyframePolicy.should_add(...)`.

- [ ] **Step 1: Write failing boundary tests**

```python
from scanner_app.tracking.quality import TrackingQualityGate


def test_quality_gate_rejects_good_fit_with_excessive_motion() -> None:
    decision = TrackingQualityGate().evaluate(
        success=True,
        fitness=0.8,
        rmse_m=0.001,
        translation_m=0.051,
        rotation_deg=2.0,
        timestamp_gap_ms=33.0,
    )
    assert not decision.accepted
    assert decision.reason == "translation_limit"
```

```python
from scanner_app.tracking.keyframes import KeyframePolicy


def test_keyframe_policy_accepts_rotation_threshold() -> None:
    assert KeyframePolicy().should_add(0.001, 3.1, 20.0, depth_valid_ratio=0.8)
    assert not KeyframePolicy().should_add(0.001, 1.0, 20.0, depth_valid_ratio=0.8)
```

- [ ] **Step 2: Verify both modules are missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_tracking_quality.py tests/test_keyframes.py -q`

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement explicit gates and keyframe policy**

```python
# src/scanner_app/tracking/quality.py
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    reason: str | None


class TrackingQualityGate:
    def evaluate(self, success, fitness, rmse_m, translation_m, rotation_deg, timestamp_gap_ms):
        checks = (
            (success, "odometry_failed"),
            (fitness >= 0.35, "fitness"),
            (rmse_m <= 0.004, "rmse"),
            (translation_m <= 0.050, "translation_limit"),
            (rotation_deg <= 15.0, "rotation_limit"),
            (0.0 <= timestamp_gap_ms <= 200.0, "timestamp_gap"),
        )
        for passed, reason in checks:
            if not passed:
                return QualityDecision(False, reason)
        return QualityDecision(True, None)
```

```python
# src/scanner_app/tracking/keyframes.py
class KeyframePolicy:
    def should_add(self, translation_m, rotation_deg, elapsed_ms, depth_valid_ratio):
        if depth_valid_ratio < 0.70:
            return False
        return translation_m >= 0.005 or rotation_deg >= 3.0 or elapsed_ms >= 200.0


@dataclass(frozen=True)
class Keyframe:
    packet: SynchronizedFramePacket
    processed_depth: ProcessedDepth
    camera_to_world: np.ndarray
    timestamp_us: int


class KeyframeStore:
    def __init__(self) -> None:
        self._items: list[Keyframe] = []

    def add(self, keyframe: Keyframe) -> None:
        self._items.append(keyframe)

    def all(self) -> tuple[Keyframe, ...]:
        return tuple(self._items)
```

Add exact boundary coverage:

```python
@pytest.mark.parametrize(
    ("field", "value", "accepted"),
    [
        ("fitness", 0.35, True),
        ("fitness", 0.349, False),
        ("rmse_m", 0.004, True),
        ("rmse_m", 0.0041, False),
        ("translation_m", 0.050, True),
        ("translation_m", 0.0501, False),
        ("rotation_deg", 15.0, True),
        ("rotation_deg", 15.1, False),
    ],
)
def test_quality_boundaries(field, value, accepted) -> None:
    values = dict(
        success=True,
        fitness=0.8,
        rmse_m=0.001,
        translation_m=0.001,
        rotation_deg=1.0,
        timestamp_gap_ms=33.0,
    )
    values[field] = value
    assert TrackingQualityGate().evaluate(**values).accepted is accepted
```

- [ ] **Step 4: Run the boundary suites**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_tracking_quality.py tests/test_keyframes.py -q`

Expected: PASS for all exact threshold boundaries.

- [ ] **Step 5: Commit gates and keyframes**

```powershell
git add src/scanner_app/tracking/quality.py src/scanner_app/tracking/keyframes.py tests/test_tracking_quality.py tests/test_keyframes.py
git commit -m "feat: gate markerless poses and select keyframes"
```

---

### Task 4: Markerless Tracker Orchestration

**Files:**
- Create: `src/scanner_app/tracking/markerless.py`
- Test: `tests/test_markerless_tracker.py`

**Interfaces:**
- Consumes: `SynchronizedFramePacket`, `ProcessedDepth`, `ImuEstimator`, `RgbdOdometry`, `TrackingQualityGate`, and `KeyframePolicy`.
- Produces: `MarkerlessPoseTracker.track(packet, processed_depth) -> TrackingResult`.

- [ ] **Step 1: Write a failing accepted-pose composition test**

```python
import numpy as np

from scanner_app.tracking.markerless import MarkerlessPoseTracker
from scanner_app.tracking.models import TrackingState


def test_tracker_composes_accepted_relative_pose_into_world_pose():
    relative = np.eye(4)
    relative[0, 3] = 0.01

    class FakeImu:
        def predict_rotation(self, samples):
            return np.eye(3)

    class FakeOdometry:
        def estimate(self, source, target, intrinsics, seed):
            return OdometryEstimate(relative, 0.8, 0.001, True)

    tracker = MarkerlessPoseTracker(
        FakeImu(),
        FakeOdometry(),
        TrackingQualityGate(),
        KeyframePolicy(),
        intrinsics=object(),
        rgbd_factory=lambda packet, depth: object(),
    )
    first = SimpleNamespace(imu_samples=tuple(), depth_timestamp_us=1_000_000)
    second = SimpleNamespace(imu_samples=tuple(), depth_timestamp_us=1_033_000)
    depth = SimpleNamespace(valid_ratio=0.8)
    tracker.initialize(first, depth)

    result = tracker.track(second, depth)

    assert result.accepted
    assert result.state is TrackingState.TRACKING
    np.testing.assert_allclose(result.camera_to_world[0, 3], -0.01)
```

- [ ] **Step 2: Verify missing orchestrator failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_markerless_tracker.py -q`

Expected: FAIL with missing `markerless`.

- [ ] **Step 3: Implement initialization, composition, and rejection**

```python
class MarkerlessPoseTracker:
    def __init__(
        self,
        imu,
        odometry,
        quality,
        keyframe_policy,
        intrinsics,
        rgbd_factory=make_tracking_rgbd,
    ) -> None:
        self.imu = imu
        self.odometry = odometry
        self.quality = quality
        self.keyframe_policy = keyframe_policy
        self.intrinsics = intrinsics
        self.rgbd_factory = rgbd_factory
        self.state = TrackingState.INITIALIZING
        self.camera_to_world = np.eye(4)
        self.previous_rgbd = None
        self.previous_timestamp_us = None
        self.last_keyframe_timestamp_us = None
        self.reject_count = 0

    def initialize(self, packet, processed_depth) -> TrackingResult:
        self.previous_rgbd = self.rgbd_factory(packet, processed_depth)
        self.previous_timestamp_us = packet.depth_timestamp_us
        self.last_keyframe_timestamp_us = packet.depth_timestamp_us
        self.state = TrackingState.TRACKING
        metrics = TrackingMetrics(1.0, 0.0, 0.0, 0.0, 0.0)
        return TrackingResult(
            self.state, self.camera_to_world.copy(), metrics, True, True, None
        )

    def track(self, packet, processed_depth) -> TrackingResult:
        seed = np.eye(4)
        seed[:3, :3] = self.imu.predict_rotation(packet.imu_samples)
        current_rgbd = self.rgbd_factory(packet, processed_depth)
        estimate = self.odometry.estimate(
            self.previous_rgbd, current_rgbd, self.intrinsics, seed
        )
        translation, rotation = motion_magnitude(estimate.relative_transform)
        decision = self.quality.evaluate(
            estimate.success, estimate.fitness, estimate.rmse_m, translation, rotation,
            timestamp_gap_ms=(packet.depth_timestamp_us - self.previous_timestamp_us) / 1000,
        )
        metrics = TrackingMetrics(
            estimate.fitness, estimate.rmse_m, translation, rotation, 0.0
        )
        if not decision.accepted:
            self.reject_count += 1
            self.state = TrackingState.LOST if self.reject_count >= 5 else TrackingState.DEGRADED
            return TrackingResult(
                self.state,
                self.camera_to_world.copy(),
                metrics,
                False,
                False,
                decision.reason,
            )
        self.camera_to_world = self.camera_to_world @ np.linalg.inv(estimate.relative_transform)
        self.previous_rgbd = current_rgbd
        self.previous_timestamp_us = packet.depth_timestamp_us
        self.reject_count = 0
        self.state = TrackingState.TRACKING
        elapsed_ms = (packet.depth_timestamp_us - self.last_keyframe_timestamp_us) / 1000
        keyframe = self.keyframe_policy.should_add(
            translation, rotation, elapsed_ms, processed_depth.valid_ratio
        )
        if keyframe:
            self.last_keyframe_timestamp_us = packet.depth_timestamp_us
        return TrackingResult(
            self.state,
            self.camera_to_world.copy(),
            metrics,
            True,
            keyframe,
            None,
        )
```

Implement `motion_magnitude(transform)` in the same file using translation norm
and `scipy.spatial.transform.Rotation.from_matrix(...).magnitude()`. Implement
`make_tracking_rgbd(packet, processed_depth)` with the Task 2 RGB-D image helper.
Tests cover initialization, accepted composition, degraded freeze, and LOST after
five rejects.

- [ ] **Step 4: Run markerless tracker tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_markerless_tracker.py -q`

Expected: PASS; rejected frames leave `camera_to_world` unchanged.

- [ ] **Step 5: Commit tracker orchestration**

```powershell
git add src/scanner_app/tracking/markerless.py tests/test_markerless_tracker.py
git commit -m "feat: orchestrate markerless RGB-D tracking"
```

---

### Task 5: Relocalization and Pose Graph Optimization

**Files:**
- Create: `src/scanner_app/tracking/relocalization.py`
- Create: `src/scanner_app/tracking/pose_graph.py`
- Test: `tests/test_relocalization.py`
- Test: `tests/test_markerless_pose_graph.py`

**Interfaces:**
- Consumes: current RGB-D, stored keyframes, intrinsics, and verified relative transforms.
- Produces: `RelocalizationResult`, sequential/loop graph edges, and optimized keyframe poses.

- [ ] **Step 1: Write failing geometric verification tests**

```python
import numpy as np

from scanner_app.tracking.relocalization import verify_pnp_candidate


def test_pnp_candidate_requires_inliers_and_icp_quality() -> None:
    accepted = verify_pnp_candidate(inlier_count=40, fitness=0.6, rmse_m=0.0015)
    rejected = verify_pnp_candidate(inlier_count=10, fitness=0.6, rmse_m=0.0015)
    assert accepted
    assert not rejected
```

```python
from scanner_app.tracking.pose_graph import MarkerlessPoseGraph


def test_pose_graph_marks_loop_edges_uncertain() -> None:
    graph = MarkerlessPoseGraph()
    graph.add_pose(np.eye(4))
    graph.add_pose(np.eye(4))
    graph.add_loop_edge(0, 1, np.eye(4), np.eye(6))
    assert graph.graph.edges[-1].uncertain
```

- [ ] **Step 2: Verify missing modules**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_relocalization.py tests/test_markerless_pose_graph.py -q`

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement verification and graph wrapper**

```python
def verify_pnp_candidate(inlier_count: int, fitness: float, rmse_m: float) -> bool:
    return inlier_count >= 30 and fitness >= 0.35 and rmse_m <= 0.004
```

`Relocalizer.relocalize()` must use `cv2.ORB_create(1500)`, Hamming KNN matching
with Lowe ratio 0.75, keyframe depth to construct metric 3D points,
`cv2.solvePnPRansac` with 3 px reprojection error and 1000 iterations, then the
Task 2 ICP backend. Return no pose unless `verify_pnp_candidate` passes.

```python
class MarkerlessPoseGraph:
    def __init__(self) -> None:
        self.graph = o3d.pipelines.registration.PoseGraph()

    def add_pose(self, camera_to_world: np.ndarray) -> None:
        self.graph.nodes.append(o3d.pipelines.registration.PoseGraphNode(camera_to_world))

    def add_sequential_edge(self, source, target, transform, information) -> None:
        self.graph.edges.append(o3d.pipelines.registration.PoseGraphEdge(
            source, target, transform, information, uncertain=False
        ))

    def add_loop_edge(self, source, target, transform, information) -> None:
        self.graph.edges.append(o3d.pipelines.registration.PoseGraphEdge(
            source, target, transform, information, uncertain=True
        ))

    def optimize(self) -> list[np.ndarray]:
        option = o3d.pipelines.registration.GlobalOptimizationOption(
            max_correspondence_distance=0.005,
            edge_prune_threshold=0.25,
            reference_node=0,
        )
        o3d.pipelines.registration.global_optimization(
            self.graph,
            o3d.pipelines.registration.GlobalOptimizationLevenbergMarquardt(),
            o3d.pipelines.registration.GlobalOptimizationConvergenceCriteria(),
            option,
        )
        return [node.pose.copy() for node in self.graph.nodes]
```

- [ ] **Step 4: Run relocalization and graph tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_relocalization.py tests/test_markerless_pose_graph.py -q`

Expected: PASS, including a synthetic loop whose optimized endpoint moves closer
to the reference endpoint.

- [ ] **Step 5: Commit recovery and loop closure**

```powershell
git add src/scanner_app/tracking/relocalization.py src/scanner_app/tracking/pose_graph.py tests/test_relocalization.py tests/test_markerless_pose_graph.py
git commit -m "feat: relocalize tracking and optimize pose graphs"
```

---

### Task 6: Replayable Tracking Benchmark

**Files:**
- Create: `scripts/13_markerless_tracking.py`
- Create: `tests/test_markerless_tracking_script.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Phase 1 `SessionReplay`, `DepthProcessor`, and `MarkerlessPoseTracker`.
- Produces: pose JSONL, tracking summary JSON, and nonzero exit on acceptance failure.

- [ ] **Step 1: Write failing summary evaluation tests**

```python
def test_summary_passes_only_when_rate_and_recovery_targets_hold() -> None:
    summary = evaluate_tracking(
        tracking_fps=18.0,
        accepted_ratio=0.92,
        unrecovered_losses=0,
        loop_error_m=0.0025,
    )
    assert summary.passed
    assert not evaluate_tracking(12.0, 0.92, 0, 0.0025).passed
```

- [ ] **Step 2: Verify the benchmark script is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_markerless_tracking_script.py -q`

Expected: FAIL because the numbered script is absent.

- [ ] **Step 3: Implement live/replay modes and fixed acceptance**

```python
def evaluate_tracking(tracking_fps, accepted_ratio, unrecovered_losses, loop_error_m):
    failures = []
    if tracking_fps < 15.0:
        failures.append("tracking_fps")
    if accepted_ratio < 0.85:
        failures.append("accepted_ratio")
    if unrecovered_losses != 0:
        failures.append("unrecovered_losses")
    if loop_error_m > 0.003:
        failures.append("loop_error_m")
    return TrackingBenchmarkResult(not failures, tuple(failures))
```

Support `--session PATH` for deterministic replay and `--live --record PATH` for
camera capture. Write one pose record per packet with state, acceptance, metrics,
and reason. Print transitions immediately and a final rate/loss/loop summary.

- [ ] **Step 4: Run unit, replay, and live benchmarks**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_markerless_tracking_script.py tests/test_markerless_tracker.py -q`

Replay: `.\.venv\Scripts\python.exe scripts\13_markerless_tracking.py --session data\sessions\tracking_360`

Live: `.\.venv\Scripts\python.exe scripts\13_markerless_tracking.py --live --record data\sessions\tracking_360`

Expected: unit tests PASS; benchmark JSON reports >=15 FPS and no unrecovered
loss for the controlled 360-degree sequence.

- [ ] **Step 5: Commit the tracking benchmark**

```powershell
git add scripts/13_markerless_tracking.py tests/test_markerless_tracking_script.py README.md
git commit -m "feat: benchmark markerless tracking on recorded scans"
```

## Phase Completion Check

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests PASS. Review the recorded 360-degree benchmark before Phase
3. If tracking misses the gate, tune capture/filter/quality values from replay;
do not attribute a replay algorithm failure to camera hardware.
