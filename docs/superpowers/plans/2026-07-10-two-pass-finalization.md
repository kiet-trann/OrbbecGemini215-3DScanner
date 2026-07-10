# Two-Pass Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the object's real bottom surface in a second orientation, register both optimized passes without markers, rebuild one metric TSDF, and export a cleaned complete PLY/OBJ/STL model within the 2 mm target.

**Architecture:** Each pass remains an independent optimized keyframe set. Support planes are removed before FPFH/RANSAC coarse registration and multi-scale ICP refinement. Low-confidence automatic alignment is rejected and replaced by a three-correspondence rigid transform. Pass B camera poses are transformed into Pass A coordinates before one final TSDF rebuild.

**Tech Stack:** Python 3.10+, NumPy/SciPy, Open3D registration and mesh APIs, existing session/fusion/export modules, pytest/unittest.

## Global Constraints

- Phases 1-3 must PASS before two-pass integration.
- Automatic pass alignment RMSE: <= 2 mm.
- Verified automatic inlier overlap: >= 30 percent.
- Final dimensional error: <= 2 mm on calibrated references.
- Never silently accept low-confidence or ambiguous registration.
- The second pass must measure the real bottom; hole filling is limited to small residual holes.
- Export PLY, OBJ, and STL from one optimized final mesh.
- Preserve both original pass recordings and optimized pose files.
- `rtk` is unavailable; use the direct commands below.

## File Map

- Create `src/scanner_app/registration/__init__.py`: registration package marker.
- Create `src/scanner_app/registration/support_plane.py`: table-plane removal.
- Create `src/scanner_app/registration/two_pass.py`: automatic FPFH/RANSAC/ICP registration.
- Create `src/scanner_app/registration/manual.py`: three-point rigid alignment.
- Create `src/scanner_app/fusion/finalize.py`: pose transformation, final TSDF rebuild, cleanup, and export.
- Modify `src/scanner_app/session/models.py` and `controller.py`: two-pass state flow.
- Modify `src/scanner_app/visualization/scanner_window.py`: second-pass and manual-alignment UI.
- Modify `scripts/14_markerless_scanner.py`: complete two-pass composition.
- Create `scripts/15_acceptance_scan.py`: dimensional and registration acceptance report.
- Create focused tests for every new module and workflow.

---

### Task 1: Support-Plane Removal and Pass Data Contract

**Files:**
- Create: `src/scanner_app/registration/__init__.py`
- Create: `src/scanner_app/registration/support_plane.py`
- Create: `src/scanner_app/registration/two_pass.py`
- Test: `tests/test_support_plane.py`
- Test: `tests/test_two_pass_models.py`

**Interfaces:**
- Consumes: optimized pass keyframes and extracted pass cloud.
- Produces: `OptimizedPass(name, keyframes, cloud)` and `remove_support_plane(cloud)`.

- [ ] **Step 1: Write failing pass-model and plane-removal tests**

```python
import numpy as np
import open3d as o3d

from scanner_app.registration.support_plane import remove_support_plane
from scanner_app.registration.two_pass import OptimizedPass


def test_support_plane_removal_keeps_points_above_table() -> None:
    cloud = o3d.geometry.PointCloud()
    plane = np.array([[x, y, 0.0] for x in (-0.1, 0.0, 0.1) for y in (-0.1, 0.0, 0.1)])
    object_points = np.array([[0.0, 0.0, 0.03], [0.01, 0.0, 0.04], [0.0, 0.01, 0.05]])
    cloud.points = o3d.utility.Vector3dVector(np.vstack([plane, object_points]))

    result = remove_support_plane(cloud, distance_threshold_m=0.002)

    assert len(result.points) == 3


def test_optimized_pass_rejects_empty_keyframes() -> None:
    with pytest.raises(ValueError, match="keyframe"):
        OptimizedPass("A", tuple(), o3d.geometry.PointCloud())
```

- [ ] **Step 2: Verify registration modules are missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_support_plane.py tests/test_two_pass_models.py -q`

Expected: FAIL with missing `scanner_app.registration`.

- [ ] **Step 3: Implement the pass contract and robust plane removal**

```python
# src/scanner_app/registration/two_pass.py
@dataclass(frozen=True)
class OptimizedPass:
    name: str
    keyframes: tuple[Keyframe, ...]
    cloud: o3d.geometry.PointCloud

    def __post_init__(self) -> None:
        if not self.keyframes:
            raise ValueError("Optimized pass requires at least one keyframe.")
```

```python
# src/scanner_app/registration/support_plane.py
def remove_support_plane(cloud, distance_threshold_m=0.002):
    if len(cloud.points) < 3:
        return cloud
    _, inliers = cloud.segment_plane(
        distance_threshold=float(distance_threshold_m),
        ransac_n=3,
        num_iterations=1000,
    )
    return cloud.select_by_index(inliers, invert=True)
```

Add a normal-direction check that accepts the largest plane whose normal is
within 20 degrees of the pass gravity direction from the calibrated IMU. If no
candidate satisfies that condition, return the original cloud and mark the pass
with `support_plane_removed=False` instead of deleting object surfaces.

- [ ] **Step 4: Run synthetic geometry tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_support_plane.py tests/test_two_pass_models.py -q`

Expected: PASS for horizontal table removal, tilted-table removal, and no-plane fallback.

- [ ] **Step 5: Commit pass preprocessing**

```powershell
git add src/scanner_app/registration tests/test_support_plane.py tests/test_two_pass_models.py
git commit -m "feat: define optimized passes and remove support planes"
```

---

### Task 2: Automatic FPFH, RANSAC, and ICP Pass Registration

**Files:**
- Modify: `src/scanner_app/registration/two_pass.py`
- Test: `tests/test_two_pass_registration.py`

**Interfaces:**
- Consumes: support-plane-free `OptimizedPass` A and B.
- Produces: `PassRegistration(transform_b_to_a, fitness, rmse_m, overlap, accepted, reason)`.

- [ ] **Step 1: Write failing acceptance-boundary tests**

```python
from scanner_app.registration.two_pass import registration_decision


def test_registration_requires_rmse_and_overlap_together() -> None:
    assert registration_decision(fitness=0.5, rmse_m=0.0019, overlap=0.31).accepted
    assert not registration_decision(fitness=0.5, rmse_m=0.0021, overlap=0.31).accepted
    assert not registration_decision(fitness=0.5, rmse_m=0.0019, overlap=0.29).accepted
```

- [ ] **Step 2: Run the test and verify the missing decision function**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_two_pass_registration.py -q`

Expected: FAIL with missing `registration_decision`.

- [ ] **Step 3: Implement automatic registration and explicit rejection**

```python
@dataclass(frozen=True)
class PassRegistration:
    transform_b_to_a: np.ndarray
    fitness: float
    rmse_m: float
    overlap: float
    accepted: bool
    reason: str | None


def registration_decision(fitness, rmse_m, overlap, transform=None):
    accepted = rmse_m <= 0.002 and overlap >= 0.30 and fitness >= 0.30
    reason = None if accepted else "automatic_alignment_low_confidence"
    return PassRegistration(
        np.eye(4) if transform is None else transform,
        float(fitness),
        float(rmse_m),
        float(overlap),
        accepted,
        reason,
    )
```

`register_passes(pass_a, pass_b)` performs:

```python
voxel = 0.003
source = pass_b.cloud.voxel_down_sample(voxel)
target = pass_a.cloud.voxel_down_sample(voxel)
for cloud in (source, target):
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.006, max_nn=30))
source_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
    source, o3d.geometry.KDTreeSearchParamHybrid(radius=0.015, max_nn=100)
)
target_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
    target, o3d.geometry.KDTreeSearchParamHybrid(radius=0.015, max_nn=100)
)
coarse = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
    source, target, source_fpfh, target_fpfh, True, 0.006,
    o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
    4,
    [
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
        o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(0.006),
    ],
    o3d.pipelines.registration.RANSACConvergenceCriteria(100000, 0.999),
)
fine = o3d.pipelines.registration.registration_icp(
    pass_b.cloud, pass_a.cloud, 0.004, coarse.transformation,
    o3d.pipelines.registration.TransformationEstimationPointToPlane(),
)
```

Compute overlap as bidirectional inlier coverage within 2 mm and pass all metrics
to `registration_decision`. Try the four best RANSAC candidates for symmetric
geometry; never choose by RMSE alone.

- [ ] **Step 4: Run transformed-shape registration tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_two_pass_registration.py -q`

Expected: PASS for a known rigid transform within 1 mm/0.5 degrees and rejection
of low-overlap symmetric false matches.

- [ ] **Step 5: Commit automatic pass registration**

```powershell
git add src/scanner_app/registration/two_pass.py tests/test_two_pass_registration.py
git commit -m "feat: register two optimized scan passes"
```

---

### Task 3: Manual Three-Point Registration Fallback

**Files:**
- Create: `src/scanner_app/registration/manual.py`
- Test: `tests/test_manual_registration.py`
- Modify: `src/scanner_app/visualization/scanner_window.py`

**Interfaces:**
- Consumes: three corresponding 3D points in Pass B and Pass A.
- Produces: rigid `transform_b_to_a`, followed by normal ICP verification.

- [ ] **Step 1: Write a failing exact-rigid-transform test**

```python
import numpy as np

from scanner_app.registration.manual import rigid_transform_from_points


def test_three_points_recover_known_rigid_transform() -> None:
    source = np.array([[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]], dtype=float)
    expected = np.eye(4)
    expected[:3, 3] = [0.02, -0.03, 0.04]
    target = source + expected[:3, 3]

    actual = rigid_transform_from_points(source, target)

    np.testing.assert_allclose(actual, expected, atol=1e-9)
```

- [ ] **Step 2: Verify the manual module is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_manual_registration.py -q`

Expected: FAIL with missing `manual`.

- [ ] **Step 3: Implement Kabsch alignment and degeneracy rejection**

```python
def rigid_transform_from_points(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if source.shape != (3, 3) or target.shape != (3, 3):
        raise ValueError("Exactly three source and target 3D points are required.")
    if np.linalg.matrix_rank(source[1:] - source[0]) < 2:
        raise ValueError("Selected points must not be collinear.")
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    covariance = (source - source_center).T @ (target - target_center)
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1] *= -1
        rotation = vt.T @ u.T
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = target_center - rotation @ source_center
    return transform
```

The GUI enters a modal alignment view showing Pass A and Pass B with distinct
colors. It alternates picks A1/B1, A2/B2, A3/B3, supports undo, rejects collinear
points, then runs Task 2 fine ICP and the same 2 mm/30 percent quality gate.

- [ ] **Step 4: Run math and presentation-model tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_manual_registration.py tests/test_scanner_window_model.py -q`

Expected: PASS for translation, rotation, noisy points, collinearity rejection,
pick ordering, and undo.

- [ ] **Step 5: Commit manual fallback**

```powershell
git add src/scanner_app/registration/manual.py src/scanner_app/visualization/scanner_window.py tests/test_manual_registration.py tests/test_scanner_window_model.py
git commit -m "feat: add manual three-point pass alignment"
```

---

### Task 4: Final TSDF Rebuild, Cleanup, and Multi-Format Export

**Files:**
- Create: `src/scanner_app/fusion/finalize.py`
- Test: `tests/test_final_fusion.py`
- Modify: `src/scanner_app/processing/mesh_reconstruction.py`

**Interfaces:**
- Consumes: Pass A keyframes, Pass B keyframes, and accepted `transform_b_to_a`.
- Produces: one cleaned mesh and verified PLY/OBJ/STL paths.

- [ ] **Step 1: Write failing Pass B pose-composition and export tests**

```python
import numpy as np
from dataclasses import dataclass

from scanner_app.fusion.finalize import transform_pass_keyframes


@dataclass(frozen=True)
class FakeKeyframe:
    camera_to_world: np.ndarray


def test_pass_b_camera_poses_are_composed_into_pass_a_world() -> None:
    keyframe = FakeKeyframe(np.eye(4))
    transform = np.eye(4)
    transform[0, 3] = 0.1
    transformed = transform_pass_keyframes((keyframe,), transform)
    np.testing.assert_allclose(
        transformed[0].camera_to_world,
        transform @ keyframe.camera_to_world,
    )
```

- [ ] **Step 2: Verify the finalizer is missing**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_final_fusion.py -q`

Expected: FAIL with missing `scanner_app.fusion.finalize`.

- [ ] **Step 3: Implement pose composition, rebuild, and verified writes**

```python
from dataclasses import replace


def transform_pass_keyframes(keyframes, transform_b_to_a):
    return tuple(
        replace(
            keyframe,
            camera_to_world=transform_b_to_a @ keyframe.camera_to_world,
        )
        for keyframe in keyframes
    )


def finalize_two_pass(pass_a, pass_b, registration, fusion, output_stem):
    if not registration.accepted:
        raise ValueError("Two-pass registration must be accepted before final fusion.")
    combined = pass_a.keyframes + transform_pass_keyframes(
        pass_b.keyframes, registration.transform_b_to_a
    )
    mesh = fusion.rebuild(combined)
    cleanup_mesh(mesh)
    paths = {
        ".ply": output_stem.with_suffix(".ply"),
        ".obj": output_stem.with_suffix(".obj"),
        ".stl": output_stem.with_suffix(".stl"),
    }
    for path in paths.values():
        if not o3d.io.write_triangle_mesh(str(path), mesh):
            raise OSError(f"Failed to write mesh: {path}")
        if not path.is_file() or path.stat().st_size == 0:
            raise OSError(f"Mesh output is empty: {path}")
    return mesh, paths
```

Cleanup keeps the largest object component, removes degenerate/duplicated
triangles and vertices, fills only holes with boundary diameter <=5 mm, computes
vertex normals, and checks manifold/watertight status. Never fabricate a large
missing surface after a failed second pass.

- [ ] **Step 4: Run final fusion and existing export tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_final_fusion.py tests/test_mesh_reconstruction.py tests/test_convert_mesh_script.py -q`

Expected: PASS; all three files are nonempty and reloadable by Open3D.

- [ ] **Step 5: Commit finalization/export**

```powershell
git add src/scanner_app/fusion/finalize.py src/scanner_app/processing/mesh_reconstruction.py tests/test_final_fusion.py
git commit -m "feat: rebuild and export complete two-pass meshes"
```

---

### Task 5: Complete Two-Pass Workflow and Acceptance Report

**Files:**
- Modify: `src/scanner_app/session/models.py`
- Modify: `src/scanner_app/session/controller.py`
- Modify: `src/scanner_app/visualization/scanner_window.py`
- Modify: `scripts/14_markerless_scanner.py`
- Create: `scripts/15_acceptance_scan.py`
- Create: `tests/test_two_pass_session.py`
- Create: `tests/test_acceptance_scan_script.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior phases.
- Produces: guided Pass A/flip/Pass B/register/finalize workflow and machine-readable dimensional acceptance JSON.

- [ ] **Step 1: Write failing state-flow and dimension-error tests**

```python
def test_session_requires_flip_confirmation_before_pass_b(two_pass_session) -> None:
    two_pass_session.finish_pass()
    assert two_pass_session.state is ScanSessionState.WAITING_FOR_FLIP
    with pytest.raises(RuntimeError, match="confirm"):
        two_pass_session.start_second_pass()
```

```python
def test_dimension_report_passes_at_two_millimeter_boundary() -> None:
    result = evaluate_dimensions(
        reference_mm=(100.0, 80.0, 50.0),
        measured_mm=(102.0, 79.0, 51.5),
        registration_rmse_mm=2.0,
    )
    assert result.passed
    assert not evaluate_dimensions((100, 80, 50), (102.1, 80, 50), 1.0).passed
```

- [ ] **Step 2: Verify missing states and acceptance script**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_two_pass_session.py tests/test_acceptance_scan_script.py -q`

Expected: FAIL with missing `WAITING_FOR_FLIP` and script.

- [ ] **Step 3: Implement complete workflow and fixed acceptance**

Add `WAITING_FOR_FLIP`, `REGISTERING`, and `ALIGNMENT_REQUIRED` to
`ScanSessionState`. `finish_pass()` stores optimized Pass A and enters
WAITING_FOR_FLIP. A distinct confirmation command starts a fresh calibration,
tracker, pose graph, ROI, and TSDF for Pass B. Finishing Pass B runs automatic
registration in a worker, opens manual alignment only on explicit rejection,
then finalizes and enters COMPLETE.

```python
def evaluate_dimensions(reference_mm, measured_mm, registration_rmse_mm):
    errors = tuple(abs(float(actual) - float(reference)) for reference, actual in zip(
        reference_mm, measured_mm
    ))
    failures = []
    if max(errors) > 2.0:
        failures.append("dimensional_error_mm")
    if registration_rmse_mm > 2.0:
        failures.append("registration_rmse_mm")
    return AcceptanceResult(not failures, errors, tuple(failures))
```

`scripts/15_acceptance_scan.py` loads the final mesh, asks for three reference
dimensions measured by caliper, computes oriented bounding-box dimensions,
records registration metrics and output topology, and writes
`data/sessions/<session>/acceptance.json`. It exits 1 when any 2 mm requirement
fails. README documents the exact two-pass operator sequence and supported
materials.

- [ ] **Step 4: Run full software and physical acceptance**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Run scanner: `.\.venv\Scripts\python.exe scripts\14_markerless_scanner.py`

Run report: `.\.venv\Scripts\python.exe scripts\15_acceptance_scan.py --session data\sessions\two_pass_reference`

Expected: all tests PASS; automatic or manual alignment is explicitly accepted;
final PLY/OBJ/STL include side/top/real-bottom surfaces; the acceptance JSON
reports maximum dimensional error <=2 mm and registration RMSE <=2 mm.

- [ ] **Step 5: Commit the complete workflow**

```powershell
git add src/scanner_app/session src/scanner_app/visualization/scanner_window.py scripts/14_markerless_scanner.py scripts/15_acceptance_scan.py tests/test_two_pass_session.py tests/test_acceptance_scan_script.py README.md
git commit -m "feat: complete two-pass markerless object scanning"
```

## Final Completion Check

Run the entire unit suite, one deterministic replay scan, a 10-minute live soak,
and physical scans of calibrated box and cylinder references spanning the 5-30 cm
range. Completion requires the hardware, tracking, performance, two-pass
registration, dimensional, topology, and export gates from the approved design.
Only after those pass is the markerless scanner considered complete.
