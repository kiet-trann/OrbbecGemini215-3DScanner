"""Guarded Windows-only Pause/Resume input for a visible RTAB-Map window."""

from collections.abc import Callable
import ctypes
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeResult:
    sent: bool
    message: str


WindowFinder = Callable[[], list[tuple[int, str]]]
SpaceSender = Callable[[int], None]


class WindowsRtabmapBridge:
    """Send Space only when exactly one RTAB-Map window can be identified."""

    def __init__(
        self,
        *,
        find_windows: WindowFinder | None = None,
        send_space: SpaceSender | None = None,
    ) -> None:
        self._find_windows = find_windows or _find_visible_windows
        self._send_space = send_space or _send_space_to_window

    def find_window(self) -> int | None:
        matches = [hwnd for hwnd, title in self._find_windows() if _is_rtabmap_title(title)]
        return matches[0] if len(matches) == 1 else None

    def pause(self) -> BridgeResult:
        return self._send_toggle("Pause")

    def resume(self) -> BridgeResult:
        return self._send_toggle("Resume")

    def _send_toggle(self, action: str) -> BridgeResult:
        matches = [hwnd for hwnd, title in self._find_windows() if _is_rtabmap_title(title)]
        if not matches:
            return BridgeResult(False, "RTAB-Map window was not found")
        if len(matches) != 1:
            return BridgeResult(False, "RTAB-Map window is ambiguous")
        self._send_space(matches[0])
        return BridgeResult(True, f"{action} sent")


def _is_rtabmap_title(title: str) -> bool:
    return title == "RTAB-Map" or title.startswith("RTAB-Map*")


def _find_visible_windows() -> list[tuple[int, str]]:
    user32 = ctypes.windll.user32
    windows: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        windows.append((int(hwnd), buffer.value))
        return True

    if not user32.EnumWindows(collect, 0):
        raise ctypes.WinError()
    return windows


def _send_space_to_window(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    if not user32.SetForegroundWindow(hwnd):
        raise OSError("Could not bring RTAB-Map to the foreground")

    keybdinput = _KEYBDINPUT(wVk=0x20, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    keyup = _KEYBDINPUT(wVk=0x20, wScan=0, dwFlags=0x0002, time=0, dwExtraInfo=0)
    inputs = (_INPUT * 2)(
        _INPUT(type=1, ki=keybdinput),
        _INPUT(type=1, ki=keyup),
    )
    if user32.SendInput(len(inputs), ctypes.byref(inputs), ctypes.sizeof(_INPUT)) != len(inputs):
        raise ctypes.WinError()


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _INPUT_UNION)]
