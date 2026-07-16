# Background-Assisted Markerless Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep a handheld Gemini 215 scan tracked through object depth holes by using raw RGB and valid office-background depth correspondences, while fusing only accepted object-depth keyframes.

**Architecture:** The background-assisted capture adapter aligns depth to the native color stream, so RGB remains visible while depth shares its pixels and color intrinsics. A new OpenCV backend matches native BGR features, lifts only valid aligned-depth matches to 3D, and produces a guarded rigid transform. The existing tracker, ROI, and TSDF path remain the sole owners of accepted poses and object geometry.

**Tech Stack:** Python 3.10, NumPy, OpenCV ORB/RANSAC, Open3D, pytest, pyorbbecsdk2.

## Global Constraints

- Preserve the existing `opencv` and `open3d` markerless modes.
- No fiducials, turntable, special tracking surface, bottom scan, or watertight-mesh guarantee.
- Background-assisted tracking aligns depth to RGB; it never aligns RGB to depth or masks RGB with depth.
- A pose without enough valid 3D depth correspondences is rejected and never reaches TSDF fusion.
- Hardware validation uses a stationary object and ordinary stationary office background.

---

### Task 1: Align depth to native RGB and add a capture diagnostic

**Files:**
- Modify: `src/scanner_app/camera/orbbec_capture.py`
- Create: `src/scanner_app/camera/diagnostics.py`
- Create: `scripts/16_capture_diagnostic.py`
- Modify: `tests/test_orbbec_capture.py`
- Create: `tests/test_capture_diagnostic.py`

**Interfaces:**
- Produces `AlignmentTarget.NONE`, `AlignmentTarget.COLOR`, and `AlignmentTarget.DEPTH`.
- Produces `CaptureDiagnostic(color_visible: bool, alignment_target: str, depth_valid_ratio: float)`.
- `summarize_capture_visibility(color_bgr, alignment_target, depth_raw, depth_scale_mm, min_depth_m, max_depth_m)` returns that diagnostic.

- [ ] **Step 1: Write failing tests**

```python
def test_depth_to_color_capture_constructs_a_color_align_filter_and_uses_color_intrinsics():
    sdk = FakeSdk()
    capture = OrbbecCapture(sdk_module=sdk, alignment_target="color")
    capture.start()
    assert sdk.align_filter.align_to_stream == "color-stream"
    assert capture.intrinsics().width == FakeColorIntrinsic.width

def test_diagnostic_records_visible_color_and_d2c_target():
    color = np.full((4, 4, 3), 80, dtype=np.uint8)
    depth = np.full((4, 4), 250, dtype=np.uint16)
    result = summarize_capture_visibility(color, "color", depth, 1.0, 0.2, 0.3)
    assert result.color_visible is True
    assert result.alignment_target == "color"
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_orbbec_capture.py tests/test_capture_diagnostic.py -q`

Expected: FAIL because `AlignmentTarget`, the diagnostic module, and script do not exist.

- [ ] **Step 3: Implement the smallest capture metadata and diagnostic API**

```python
class AlignmentTarget(Enum):
    NONE = "none"
    COLOR = "color"
    DEPTH = "depth"

def summarize_capture_visibility(...):
    return CaptureDiagnostic(
        color_visible=mean_luminance(color_bgr) > 5.0,
        alignment_target=alignment_target,
        depth_valid_ratio=valid_depth_ratio(...),
    )
```

Preserve `align_to_depth` as a backward-compatible legacy alias. The diagnostic script defaults to D2C and its headless JSON output includes color visibility, alignment target, color/depth dimensions, and valid depth ratio.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_orbbec_capture.py tests/test_capture_diagnostic.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scanner_app/camera/orbbec_capture.py src/scanner_app/camera/diagnostics.py scripts/16_capture_diagnostic.py tests/test_orbbec_capture.py tests/test_capture_diagnostic.py
git commit -m "feat: add raw RGB capture diagnostics"
```

### Task 2: Add guarded background-assisted visual RGB-D odometry

**Files:**
- Modify: `src/scanner_app/tracking/rgbd_odometry.py`
- Modify: `tests/test_rgbd_odometry.py`

**Interfaces:**
- Produces `BackgroundAssistedRgbdOdometryBackend` implementing `RgbdOdometryBackend`.
- Constructor parameters: `max_features: int = 1600`, `min_matches: int = 24`, `min_inliers: int = 16`, `ransac_threshold_m: float = 0.008`.
- `estimate(...) -> OdometryEstimate` returns zero fitness and infinite RMSE when valid 3D evidence is insufficient.

- [ ] **Step 1: Write failing tests**

```python
def test_background_backend_recovers_translation_despite_invalid_object_depth():
    source_color, target_color, source_depth, target_depth, intrinsics = synthetic_scene_with_depth_hole()
    result = BackgroundAssistedRgbdOdometryBackend().estimate(
        source_color, source_depth, target_color, target_depth, intrinsics, np.eye(4)
    )
    assert result.fitness >= 0.5
    assert result.rmse_m < 0.002
    np.testing.assert_allclose(result.relative_transform[:3, 3], [0.01, 0.0, 0.0], atol=0.002)

def test_background_backend_rejects_matches_without_depth_on_both_frames():
    result = BackgroundAssistedRgbdOdometryBackend(min_inliers=4).estimate(...zero_depth..., np.eye(4))
    assert result.fitness == 0.0
    assert np.isinf(result.rmse_m)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_rgbd_odometry.py -q`

Expected: FAIL because `BackgroundAssistedRgbdOdometryBackend` does not exist.

- [ ] **Step 3: Implement only the guarded backend**

```python
matches = ratio_test_orb_matches(source_color, target_color)
source_points, target_points = depth_backprojected_matches(matches, ...)
if len(source_points) < self.min_matches:
    return _failed_estimate(initial_transform, target_depth)
transform, inlier_mask = estimate_ransac_rigid_transform(source_points, target_points, ...)
if inlier_mask.sum() < self.min_inliers:
    return _failed_estimate(initial_transform, target_depth)
return OdometryEstimate(transform, inlier_mask.mean(), rmse, valid_ratio)
```

Use native RGB plus depth aligned to the color camera; do not broaden the fusion ROI or weaken `QualityGate` thresholds.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_rgbd_odometry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scanner_app/tracking/rgbd_odometry.py tests/test_rgbd_odometry.py
git commit -m "feat: add background-assisted RGB-D odometry"
```

### Task 3: Expose the backend in live tracking and guard TSDF integration

**Files:**
- Modify: `scripts/13_markerless_tracking.py`
- Modify: `scripts/14_markerless_scanner.py`
- Modify: `tests/test_markerless_tracking_script.py`
- Modify: `tests/test_markerless_scanner_script.py`

**Interfaces:**
- Both scripts accept `--backend background-assisted`.
- The live scanner starts `OrbbecCapture(..., alignment_target="color")` for that backend.
- `build_tracker()` creates `BackgroundAssistedRgbdOdometryBackend` only for that explicit choice.

- [ ] **Step 1: Write failing parser and factory tests**

```python
def test_live_parser_accepts_background_assisted_backend():
    args = module.build_argument_parser().parse_args(["--backend", "background-assisted"])
    assert args.backend == "background-assisted"

def test_live_scan_aligns_depth_to_color_for_background_assisted_backend():
    args = parser.parse_args(["--backend", "background-assisted", "--headless", "--no-export"])
    module.run_live_scan(args, capture_factory=RecordingCapture, ...)
    assert recordings["alignment_target"] == "color"
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest tests/test_markerless_tracking_script.py tests/test_markerless_scanner_script.py -q`

Expected: FAIL because the parser rejects `background-assisted`.

- [ ] **Step 3: Implement explicit backend selection and raw capture mode**

```python
if args.backend == "background-assisted":
    backend = BackgroundAssistedRgbdOdometryBackend(...)
    alignment_target = "color"
else:
    backend = OpenCvRgbdOdometryBackend(...) if args.backend == "opencv" else None
    alignment_target = "depth"
```

Leave the existing keyframe-only integration condition unchanged; add an assertion test that rejected results do not increment integrated keyframes.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/test_markerless_tracking_script.py tests/test_markerless_scanner_script.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/13_markerless_tracking.py scripts/14_markerless_scanner.py tests/test_markerless_tracking_script.py tests/test_markerless_scanner_script.py
git commit -m "feat: run live scans with raw RGB background tracking"
```

### Task 4: Verify regression coverage and publish a hardware trial command

**Files:**
- Modify: `README.md`
- Modify: `docs/scan-workflow.md`
- Test: `tests/`

**Interfaces:**
- Documents the diagnostic command before live scanning.
- Documents `scripts/14_markerless_scanner.py --backend background-assisted` as experimental and open-surface only.

- [ ] **Step 1: Add failing command-contract tests where scripts expose defaults**

```python
def test_background_assisted_defaults_require_more_correspondences():
    tracker = module.build_tracker(intrinsics, parser.parse_args(["--backend", "background-assisted"]))
    assert tracker.odometry._backend.min_matches == 24
```

- [ ] **Step 2: Run its test and verify RED**

Run: `python -m pytest tests/test_markerless_scanner_script.py -q`

Expected: FAIL until the configured backend is connected.

- [ ] **Step 3: Document the exact hardware trial and failure record**

```powershell
.\.venv\Scripts\python.exe scripts\16_capture_diagnostic.py --alignment-target color --capture-seconds 10
.\.venv\Scripts\python.exe scripts\14_markerless_scanner.py --backend background-assisted --min-depth-m 0.20 --max-depth-m 0.40 --tracking-max-depth-m 0.60
```

The instructions require a box corner pass, record color visibility with `alignment_target=color`, and state that an inconclusive/LOST result is evidence to move to the visual-only calibrated-PnP fallback.

- [ ] **Step 4: Run full verification**

Run: `python -m pytest -q -p no:cacheprovider`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/scan-workflow.md tests/test_markerless_scanner_script.py
git commit -m "docs: add background-assisted scan trial"
```
