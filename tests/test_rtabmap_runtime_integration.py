# ruff: noqa: E402

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import subprocess
import time

import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.exporter import ExportRequest, ExportService
from scanner_app.rtabmap.runtime import RtabmapRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_selected_runtime_exports_textured_obj_without_mutating_database(
    tmp_path: Path,
) -> None:
    database_env = os.environ.get("RTABMAP_INTEGRATION_DB")
    if not database_env:
        pytest.skip("set RTABMAP_INTEGRATION_DB to a saved RTAB-Map database")
    database = Path(database_env)
    before = (database.stat().st_size, hashlib.sha256(database.read_bytes()).hexdigest())
    paths = RtabmapRuntime.resolve(PROJECT_ROOT)
    result = ExportService(exporter=paths.exporter).export(
        ExportRequest(database=database, output_root=tmp_path),
    )
    after = (database.stat().st_size, hashlib.sha256(database.read_bytes()).hexdigest())
    assert result.error is None
    assert result.obj is not None and result.obj.stat().st_size > 0
    assert result.mtl is not None and result.mtl.stat().st_size > 0
    assert result.textures and all(path.stat().st_size > 0 for path in result.textures)
    assert result.viewer_model is not None
    assert result.viewer_model.read_bytes()[:4] == b"glTF"
    assert after == before


@pytest.mark.integration
def test_selected_runtime_launches_a_visible_rtabmap_window() -> None:
    if os.environ.get("RTABMAP_GUI_SMOKE") != "1":
        pytest.skip("set RTABMAP_GUI_SMOKE=1 to launch the selected RTAB-Map GUI")

    paths = RtabmapRuntime.resolve(PROJECT_ROOT)
    process = subprocess.Popen([str(paths.executable)], cwd=paths.executable.parent)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"RTAB-Map exited before showing a window ({process.returncode})")
            if _has_visible_rtabmap_window(process.pid):
                break
            time.sleep(0.25)
        else:
            visible_titles = _visible_window_titles(process.pid)
            pytest.fail(
                "RTAB-Map did not show a visible window within 20 seconds; "
                f"visible titles for PID {process.pid}: {visible_titles!r}"
            )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _has_visible_rtabmap_window(process_id: int) -> bool:
    return any(
        title in {"RTAB-Map", "RTABMap"}
        or title.startswith("RTAB-Map*")
        or title.startswith("RTABMap*")
        for title in _visible_window_titles(process_id)
    )


def _visible_window_titles(process_id: int) -> list[str]:
    user32 = ctypes.windll.user32
    titles: list[str] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    @callback_type
    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        owner_process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_process_id))
        if owner_process_id.value != process_id:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        titles.append(buffer.value)
        return True

    user32.EnumWindows(collect, 0)
    return titles
