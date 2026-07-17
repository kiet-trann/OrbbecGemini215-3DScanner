# Cropped OBJ Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show previously created cropped OBJ bundles in 3D Scanner and open the selected one after restarting the app.

**Architecture:** A read-only `CroppedObjCatalog` discovers `*_cropped.obj` files under the configured output root and returns immutable records sorted by modified time. The Tk window owns selection state, refreshes that catalog with its normal refresh and after crop success, and passes the selected path to the existing `OpenActionService`.

**Tech Stack:** Python 3.11, pathlib, dataclasses, tkinter, pytest.

## Global Constraints

- Discover only `*_cropped.obj` below `outputs/scanner_3d`; raw OBJ exports are excluded.
- The catalog must never modify, move, rename, or create output files.
- Rows are newest first and ignored if a file disappears while discovery runs.
- Open actions require an explicit selected catalog row and retain their existing target validation.

---

### Task 1: Read-only cropped OBJ discovery

**Files:**
- Create: `src/scanner_app/visualization/crop_catalog.py`
- Create: `tests/test_crop_catalog.py`

**Interfaces:**
- Produces `CroppedObjOutput(path: Path, output_dir: Path, size_bytes: int, modified_at: datetime)`.
- Produces `CroppedObjCatalog(output_root: Path)` and `refresh() -> list[CroppedObjOutput]`.

- [ ] **Step 1: Write the failing discovery tests**

```python
def test_refresh_lists_only_cropped_objs_newest_first_without_writing_them(tmp_path: Path) -> None:
    old = tmp_path / "cropped_old" / "old_cropped.obj"
    new = tmp_path / "nested" / "cropped_new" / "new_cropped.obj"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    raw = tmp_path / "raw" / "scan_mesh.obj"
    raw.parent.mkdir()
    raw.write_text("raw", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))
    original_mtime = new.stat().st_mtime_ns

    outputs = CroppedObjCatalog(tmp_path).refresh()

    assert [output.path.name for output in outputs] == ["new_cropped.obj", "old_cropped.obj"]
    assert new.stat().st_mtime_ns == original_mtime


def test_refresh_ignores_missing_root(tmp_path: Path) -> None:
    assert CroppedObjCatalog(tmp_path / "missing").refresh() == []
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_crop_catalog.py -v`

Expected: FAIL during collection because `scanner_app.visualization.crop_catalog` does not exist.

- [ ] **Step 3: Implement the immutable catalog**

```python
@dataclass(frozen=True)
class CroppedObjOutput:
    path: Path
    output_dir: Path
    size_bytes: int
    modified_at: datetime


class CroppedObjCatalog:
    def __init__(self, output_root: Path) -> None:
        self._output_root = output_root.resolve()

    def refresh(self) -> list[CroppedObjOutput]:
        if not self._output_root.is_dir():
            return []
        outputs: list[CroppedObjOutput] = []
        for path in self._output_root.rglob("*_cropped.obj"):
            try:
                stat = path.stat()
            except OSError:
                continue
            outputs.append(CroppedObjOutput(path.resolve(), path.resolve().parent, stat.st_size, datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)))
        return sorted(outputs, key=lambda output: output.modified_at, reverse=True)
```

- [ ] **Step 4: Run focused tests to verify them passing**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_crop_catalog.py -v`

Expected: PASS with two tests.

### Task 2: Persistent crop-output list in the desktop window

**Files:**
- Modify: `src/scanner_app/visualization/scanner_3d_window.py`
- Modify: `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes `CroppedObjCatalog.refresh() -> list[CroppedObjOutput]` and `OpenActionService`.
- `Scanner3DWindow.refresh_crop_outputs(select_path: Path | None = None) -> None` populates the crop-output tree.
- `open_latest_cropped_obj()` and `open_latest_output_folder()` use the selected crop tree row, not process-local crop state.

- [ ] **Step 1: Write the failing selection helper test**

```python
def test_selected_crop_path_returns_selected_catalog_output(tmp_path: Path) -> None:
    output = CroppedObjOutput(tmp_path / "crop" / "model_cropped.obj", tmp_path / "crop", 12, datetime.now(timezone.utc))

    assert selected_crop_path([output], ("0",)) == output.path
    assert selected_crop_path([output], ()) is None
```

- [ ] **Step 2: Run the focused UI test to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_scanner_3d_window.py -v`

Expected: FAIL because `selected_crop_path` is not defined.

- [ ] **Step 3: Add selection helper, catalog tree, and action wiring**

```python
def selected_crop_path(outputs: list[CroppedObjOutput], selection: tuple[str, ...]) -> Path | None:
    if not selection:
        return None
    index = int(selection[0])
    return outputs[index].path if 0 <= index < len(outputs) else None
```

Create a `Cropped OBJ outputs` `ttk.LabelFrame` and Treeview below sessions. Its rows show OBJ name, output folder name, size in MB, and UTC modified time. Bind `<<TreeviewSelect>>` to enable both open buttons only when `selected_crop_path()` returns a path. Call `refresh_crop_outputs()` at window construction, from `refresh()`, and from `_record_crop_result(result)` using `result.obj` as `select_path`. Replace `latest_cropped_obj` checks in the two callbacks with the selected tree path and set `Crop an OBJ output first` when no row is selected.

- [ ] **Step 4: Run focused tests and full suite**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_crop_catalog.py tests\\test_scanner_3d_window.py -v; ..\\..\\.venv\\Scripts\\python.exe -m pytest -q; git diff --check`

Expected: focused tests and the complete suite pass; `git diff --check` has no output.

- [ ] **Step 5: Manual Windows acceptance**

Run: `..\\..\\.venv\\Scripts\\python.exe scripts\\17_3d_scanner.py`

Expected: a prior `*_cropped.obj` appears after app restart; selecting it enables both open buttons; the folder button opens its exact crop bundle; crop success refreshes and selects the new row.

- [ ] **Step 6: Commit the feature**

```powershell
git add src/scanner_app/visualization/crop_catalog.py src/scanner_app/visualization/scanner_3d_window.py tests/test_crop_catalog.py tests/test_scanner_3d_window.py
git commit -m "feat: list cropped OBJ outputs"
```
