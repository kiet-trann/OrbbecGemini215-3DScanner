# Cropped OBJ Open Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the operator to open the latest cropped OBJ or its output folder directly from 3D Scanner 3D Scanner.

**Architecture:** Add an injected `OpenActionService` that validates files before delegating to the Windows shell. The Tk window retains only the latest successful crop path and enables two buttons only after that path is available.

**Tech Stack:** Python 3.11, tkinter, standard-library `os.startfile`, pytest.

## Global Constraints

- Windows only; do not bundle or choose a 3D viewer.
- The raw OBJ and crop output are immutable after their respective services complete.
- The two open actions must stay disabled until a crop worker has returned a successful `CropResult`.
- A missing target or shell error must be surfaced through the existing status area.

---

### Task 1: Validated crop-output open actions

**Files:**
- Create: `src/scanner_app/visualization/open_actions.py`
- Modify: `src/scanner_app/visualization/scanner_3d_window.py`
- Modify: `tests/test_scanner_3d_window.py`
- Create: `tests/test_open_actions.py`

**Interfaces:**
- Produces `OpenActionResult(opened: bool, message: str)` and `OpenActionService(launcher: Callable[[str], None])`.
- Produces `OpenActionService.open_obj(path: Path) -> OpenActionResult` and `open_folder(path: Path) -> OpenActionResult`.
- `scanner_3dWindow` stores `latest_cropped_obj: Path | None`, enables two Tk buttons after crop success, and invokes the service from its Tk event loop.

- [ ] **Step 1: Write the failing service tests**

```python
def test_open_obj_launches_existing_obj(tmp_path: Path) -> None:
    launched: list[str] = []
    obj = tmp_path / "part_cropped.obj"
    obj.touch()

    result = OpenActionService(launcher=launched.append).open_obj(obj)

    assert result == OpenActionResult(True, f"Opened: {obj}")
    assert launched == [str(obj)]


def test_open_folder_rejects_missing_crop_output(tmp_path: Path) -> None:
    result = OpenActionService(launcher=lambda target: pytest.fail(target)).open_folder(tmp_path / "missing.obj")

    assert result == OpenActionResult(False, "Cropped OBJ is no longer available")
```

- [ ] **Step 2: Run the new test file to verify it fails**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_open_actions.py -v`

Expected: FAIL during collection because `scanner_app.visualization.open_actions` does not exist.

- [ ] **Step 3: Implement the minimal validated launcher**

```python
@dataclass(frozen=True)
class OpenActionResult:
    opened: bool
    message: str


class OpenActionService:
    def __init__(self, launcher: Callable[[str], None] | None = None) -> None:
        self._launcher = launcher or os.startfile

    def open_obj(self, path: Path) -> OpenActionResult:
        if not path.is_file():
            return OpenActionResult(False, "Cropped OBJ is no longer available")
        return self._launch(path, f"Opened: {path}")

    def open_folder(self, path: Path) -> OpenActionResult:
        if not path.is_file():
            return OpenActionResult(False, "Cropped OBJ is no longer available")
        return self._launch(path.parent, f"Opened folder: {path.parent}")
```

`_launch()` catches `OSError` and returns `OpenActionResult(False, f"Could not open: {target}")`; it must not raise through the Tk callback.

- [ ] **Step 4: Add the window state and buttons**

```python
self.latest_cropped_obj: Path | None = None
self.open_obj_button = ttk.Button(actions, text="Open cropped OBJ", command=self.open_latest_cropped_obj, state=tk.DISABLED)
self.open_folder_button = ttk.Button(actions, text="Open output folder", command=self.open_latest_output_folder, state=tk.DISABLED)

def _record_crop_result(self, result: CropResult) -> None:
    self.latest_cropped_obj = result.obj
    self.open_obj_button.configure(state=tk.NORMAL)
    self.open_folder_button.configure(state=tk.NORMAL)
    self.status.set(f"Cropped OBJ: {result.obj}")
```

The crop worker calls `_record_crop_result()` via `root.after(0, ...)` only on successful crop. Each open-button callback returns early with a clear status if `latest_cropped_obj is None`; otherwise it calls the matching `OpenActionService` method and displays its result message.

- [ ] **Step 5: Run focused tests and the complete suite**

Run: `..\\..\\.venv\\Scripts\\python.exe -m pytest tests\\test_open_actions.py tests\\test_scanner_3d_window.py -v; ..\\..\\.venv\\Scripts\\python.exe -m pytest -q; git diff --check`

Expected: all new and existing tests pass, and `git diff --check` has no output.

- [ ] **Step 6: Manual Windows acceptance**

Run: `..\\..\\.venv\\Scripts\\python.exe scripts\\17_scanner_3d.py`

Expected: both buttons are disabled at launch; crop an OBJ; both enable; `Open output folder` opens the crop bundle directory; `Open cropped OBJ` launches the Windows file association or Windows app-choice prompt.

- [ ] **Step 7: Commit the tested feature**

```powershell
git add src/scanner_app/visualization/open_actions.py src/scanner_app/visualization/scanner_3d_window.py tests/test_open_actions.py tests/test_scanner_3d_window.py
git commit -m "feat: open cropped OBJ outputs"
```
