# ruff: noqa: E402

import ctypes
from ctypes import wintypes
from pathlib import Path
import re
import subprocess

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.runtime import RtabmapRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def _windows_product_version(path: Path) -> str:
    version = ctypes.windll.version
    unused_handle = wintypes.DWORD()
    size = version.GetFileVersionInfoSizeW(str(path), ctypes.byref(unused_handle))
    assert size, f"No Windows version resource found in {path}"

    version_info = ctypes.create_string_buffer(size)
    assert version.GetFileVersionInfoW(str(path), 0, size, version_info)

    fixed_info_pointer = ctypes.c_void_p()
    fixed_info_size = wintypes.UINT()
    assert version.VerQueryValueW(
        version_info,
        "\\",
        ctypes.byref(fixed_info_pointer),
        ctypes.byref(fixed_info_size),
    )
    assert fixed_info_size.value >= ctypes.sizeof(_VS_FIXEDFILEINFO)

    fixed_info = ctypes.cast(
        fixed_info_pointer,
        ctypes.POINTER(_VS_FIXEDFILEINFO),
    ).contents
    assert fixed_info.dwSignature == 0xFEEF04BD
    components = [
        fixed_info.dwProductVersionMS >> 16,
        fixed_info.dwProductVersionMS & 0xFFFF,
        fixed_info.dwProductVersionLS >> 16,
        fixed_info.dwProductVersionLS & 0xFFFF,
    ]
    while len(components) > 3 and components[-1] == 0:
        components.pop()
    return ".".join(str(component) for component in components)


def test_both_supported_runtime_bundles_are_packaged() -> None:
    for version in ("0.23.8", "0.23.1"):
        paths = RtabmapRuntime.resolve(
            PROJECT_ROOT,
            environ={"SCANNER_RTABMAP_VERSION": version},
        )
        assert paths.executable.is_file()
        assert paths.exporter.is_file()


def test_default_exporter_reports_packaged_versions() -> None:
    paths = RtabmapRuntime.resolve(PROJECT_ROOT, environ={})
    completed = subprocess.run(
        [str(paths.exporter), "--version"],
        cwd=paths.exporter.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0
    expected_versions = {
        "RTAB-Map:": "0.23.8",
        "PCL:": "1.15.1",
        "With VTK:": "9.3.20231030",
        "OpenCV:": "4.12.0",
    }
    for label, expected in expected_versions.items():
        assert re.search(
            rf"^{re.escape(label)}\s+{re.escape(expected)}\s*$",
            completed.stdout,
            flags=re.MULTILINE,
        )

    orbbec_sdk = paths.exporter.with_name("OrbbecSDK.dll")
    assert orbbec_sdk.is_file()
    assert _windows_product_version(orbbec_sdk) == "2.8.7"
