# Auto-pause polling recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the scanner UI responsive and make the auto-pause failure explicit when Windows cannot inject RTAB-Map's Pause shortcut.

**Architecture:** The Windows bridge remains the only component that interacts with RTAB-Map. It converts a failed foreground/input operation into an unsent `BridgeResult`; the existing monitor converts that result to `UNCERTAIN`, and the existing UI displays that state without breaking its scheduled polling loop.

**Tech Stack:** Python 3, Tkinter, `ctypes` Win32 input, pytest.

## Global Constraints

- RTAB-Map remains the sole camera and scan-session owner.
- Auto-pause may send only RTAB-Map's guarded Pause shortcut; it must never Stop, Save, or Close Database.
- Do not change the read-only SQLite `Node` activity signal, its three-second inactivity threshold, or the existing one-second countdown.
- Preserve successful manual Pause and Resume behavior.

---

### Task 1: Return a failure result when Windows input injection fails

**Files:**
- Modify: `src/scanner_app/rtabmap/windows_bridge.py:41-51`
- Test: `tests/test_rtabmap_windows_bridge.py`

**Interfaces:**
- Consumes: `SpaceSender`, a callable with signature `(int) -> None`.
- Produces: `WindowsRtabmapBridge.pause() -> BridgeResult`, where a raised `OSError` becomes `BridgeResult(False, "Pause failed: <reason>")`.

- [ ] **Step 1: Write the failing test**

```python
def test_pause_reports_windows_input_failure_without_raising() -> None:
    bridge = WindowsRtabmapBridge(
        find_windows=lambda: [(42, "RTAB-Map")],
        send_space=lambda _hwnd: (_ for _ in ()).throw(OSError("access denied")),
    )

    assert bridge.pause() == BridgeResult(False, "Pause failed: access denied")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `rtk proxy .\\.venv\\Scripts\\python.exe -m pytest tests/test_rtabmap_windows_bridge.py::test_pause_reports_windows_input_failure_without_raising -v`

Expected: FAIL because `pause()` propagates `OSError: access denied`.

- [ ] **Step 3: Write minimal implementation**

```python
try:
    self._send_space(matches[0])
except OSError as error:
    return BridgeResult(False, f"{action} failed: {error}")
return BridgeResult(True, f"{action} sent")
```

Place this in `WindowsRtabmapBridge._send_toggle()` after the no-window and ambiguous-window guards. Leave the successful result unchanged.

- [ ] **Step 4: Run bridge tests to verify they pass**

Run: `rtk proxy .\\.venv\\Scripts\\python.exe -m pytest tests/test_rtabmap_windows_bridge.py -v`

Expected: PASS, including the new failure-result regression test.

- [ ] **Step 5: Commit**

```bash
rtk git add src/scanner_app/rtabmap/windows_bridge.py tests/test_rtabmap_windows_bridge.py
rtk git commit -m "fix: recover from auto-pause input failures"
```

### Task 2: Prove a failed Pause becomes an explicit auto-pause failure

**Files:**
- Modify: `tests/test_rtabmap_activity.py`

**Interfaces:**
- Consumes: `ActivityMonitor(pause: Callable[[], BridgeResult], inactivity_seconds, countdown_seconds)`.
- Produces: `AutoPauseState.UNCERTAIN` when `pause()` returns `BridgeResult(sent=False, ...)` at countdown expiry.

- [ ] **Step 1: Write the failing test**

```python
def test_monitor_becomes_uncertain_when_pause_command_is_not_sent() -> None:
    monitor = ActivityMonitor(
        pause=lambda: BridgeResult(False, "Pause failed: access denied"),
        inactivity_seconds=3.0,
        countdown_seconds=1.0,
    )

    monitor.observe(ActivityObservation(1, 0.0, None))
    monitor.observe(ActivityObservation(2, 1.0, None))
    assert monitor.observe(ActivityObservation(2, 4.0, None)) is AutoPauseState.COUNTDOWN
    assert monitor.observe(ActivityObservation(2, 5.0, None)) is AutoPauseState.UNCERTAIN
```

- [ ] **Step 2: Run test to verify it captures the existing monitor contract**

Run: `rtk proxy .\\.venv\\Scripts\\python.exe -m pytest tests/test_rtabmap_activity.py::test_monitor_becomes_uncertain_when_pause_command_is_not_sent -v`

Expected: PASS because `ActivityMonitor` already maps an unsent `BridgeResult` to `UNCERTAIN`.

- [ ] **Step 3: Keep production code unchanged**

The monitor implementation already contains the required behavior:

```python
result = self._pause()
self._state = AutoPauseState.PAUSED if result.sent else AutoPauseState.UNCERTAIN
```

Do not modify `activity.py`; the new regression test connects Task 1 to the UI state transition.

- [ ] **Step 4: Run activity tests to verify they pass**

Run: `rtk proxy .\\.venv\\Scripts\\python.exe -m pytest tests/test_rtabmap_activity.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_rtabmap_activity.py
rtk git commit -m "test: cover auto-pause command failure"
```

### Task 3: Run focused end-to-end regression coverage

**Files:**
- Verify only: `tests/test_rtabmap_windows_bridge.py`, `tests/test_rtabmap_activity.py`, `tests/test_scanner_3d_window.py`

**Interfaces:**
- Consumes: the bridge failure result and the monitor `UNCERTAIN` state.
- Produces: evidence that the UI's existing unavailable-state copy remains covered.

- [ ] **Step 1: Run the focused regression suite**

Run: `rtk proxy .\\.venv\\Scripts\\python.exe -m pytest tests/test_rtabmap_windows_bridge.py tests/test_rtabmap_activity.py tests/test_scanner_3d_window.py -v`

Expected: PASS. This includes the UI test asserting `UNCERTAIN` displays `Auto-pause unavailable: activity signal is uncertain`.

- [ ] **Step 2: Manually verify on the scanner workstation**

1. Launch 3D Scanner and RTAB-Map, then enable Auto-pause after Node growth is observed.
2. Leave the mapped area until `Auto-pause countdown` appears.
3. Confirm RTAB-Map pauses or, if Windows blocks key injection, confirm the UI changes to `Auto-pause unavailable...` rather than remaining at countdown.
4. Confirm RTAB-Map was not stopped, saved, or closed.

- [ ] **Step 3: Record outcome in the handoff**

Add the manual-verification result to `docs/project-handoff-2026-07-17.md` only if the workstation test is performed in this implementation session.
