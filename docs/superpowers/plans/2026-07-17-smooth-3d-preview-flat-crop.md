# Smooth 3D Preview and Flat Crop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make crop-dialog rotation smooth while providing a static 2D crop image from the final 3D angle.

**Architecture:** Add pure geometry helpers for capped mesh sampling and projected point samples. The Tk dialog uses a scheduled low-detail render while dragging, a settled render on mouse release, and a separate static 2D crop-plane renderer; the crop rectangle always receives the settled `CameraProjection`.

**Tech Stack:** Python 3.11, NumPy, tkinter, pytest.

## Global Constraints

- Crop geometry uses the final 3D camera projection unchanged.
- The crop surface is flat 2D and does not render while the 3D view is rotating.
- Interactive 3D renders are capped and scheduled at most once per 33 ms.
- Raw OBJ and crop service behavior remain unchanged.

---

### Task 1: Pure capped projection helpers

**Files:**
- Modify: `src/scanner_app/rtabmap/obj_crop.py`
- Modify: `tests/test_rtabmap_obj_crop.py`

**Interfaces:**
- Produces `preview_stride(item_count: int, maximum_items: int) -> int`.
- Produces `sample_projected_vertices(vertices: list[tuple[float, float, float]], projection: CameraProjection, maximum_items: int) -> list[tuple[float, float]]`.

- [ ] **Step 1: Write failing helper tests**

```python
def test_preview_stride_caps_an_interactive_mesh() -> None:
    assert preview_stride(2_800, 700) == 4
    assert preview_stride(1_401, 700) == 3
    assert preview_stride(50, 700) == 1


def test_sample_projected_vertices_uses_the_crop_projection() -> None:
    projection = CameraProjection(np.eye(4), viewport_width=800, viewport_height=600)

    points = sample_projected_vertices([(-1, -1, 0), (1, 1, 0)], projection, maximum_items=10)

    assert points == [(0.0, 600.0), (800.0, 0.0)]
```

- [ ] **Step 2: Verify the tests fail**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_rtabmap_obj_crop.py -v`

Expected: FAIL because both helper functions are absent.

- [ ] **Step 3: Implement the helpers**

```python
def preview_stride(item_count: int, maximum_items: int) -> int:
    limit = max(1, maximum_items)
    return max(1, (item_count + limit - 1) // limit)


def sample_projected_vertices(vertices, projection, maximum_items):
    stride = preview_stride(len(vertices), maximum_items)
    return [point for vertex in vertices[::stride] if (point := projection.project((*vertex, 1.0))) is not None]
```

- [ ] **Step 4: Verify focused tests pass**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_rtabmap_obj_crop.py -v`

Expected: PASS.

### Task 2: Scheduled 3D preview and settled 2D crop plane

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py`
- Modify: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes `preview_stride()` and `sample_projected_vertices()`.
- Produces `crop_preview_limits() -> tuple[int, int]` for interactive and settled face caps.

- [ ] **Step 1: Write the failing limit-contract test**

```python
def test_crop_preview_uses_less_detail_while_rotating() -> None:
    moving, settled = crop_preview_limits()

    assert moving < settled
    assert moving == 700
```

- [ ] **Step 2: Verify the UI test fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_scanner_3d_window.py -v`

Expected: FAIL because `crop_preview_limits` is absent.

- [ ] **Step 3: Implement scheduled rendering and static crop plane**

```python
def crop_preview_limits() -> tuple[int, int]:
    return 700, 2_800
```

Replace the crop dialog's one renderer with: `render_3d(maximum_faces)`,
`render_crop_plane()` that draws `sample_projected_vertices()` only on the
right canvas, and `schedule_moving_render()` that uses `dialog.after(33, ...)`
to coalesce pointer events. Call `render_3d(moving_limit)` only from scheduled
right-drag updates. Bind `<ButtonRelease-3>` to render settled 3D and refresh
the 2D crop plane. Keep the crop canvas left-drag only; on release it computes
the highlighted kept faces once for the left canvas.

- [ ] **Step 4: Run focused tests and full suite**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_rtabmap_obj_crop.py tests\\test_scanner_3d_window.py -v; ..\\..\\.venv\\Scripts\\python.exe -m pytest -q; git diff --check`

Expected: all tests pass and `git diff --check` has no output.

- [ ] **Step 5: Manual Windows acceptance**

Run: `..\\..\\.venv\\Scripts\\python.exe scripts\\17_3d_scanner.py`

Expected: right-dragging left 3D canvas remains responsive; releasing updates a flat dotted 2D crop plane at right; crop rectangle creates the expected cropped OBJ.

- [ ] **Step 6: Commit the feature**

```powershell
git add src/scanner_app/rtabmap/obj_crop.py src/scanner_app/visualization/scanner_3d_window.py tests/test_rtabmap_obj_crop.py tests/test_scanner_3d_window.py
git commit -m "feat: smooth crop preview rendering"
```
