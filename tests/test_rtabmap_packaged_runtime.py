# ruff: noqa: E402

from pathlib import Path
import subprocess

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.runtime import RtabmapRuntime


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_both_supported_runtime_bundles_are_packaged() -> None:
    for version in ("0.23.8", "0.23.1"):
        paths = RtabmapRuntime.resolve(
            PROJECT_ROOT,
            environ={"SCANNER_RTABMAP_VERSION": version},
        )
        assert paths.executable.is_file()
        assert paths.exporter.is_file()


def test_default_exporter_reports_0238() -> None:
    paths = RtabmapRuntime.resolve(PROJECT_ROOT, environ={})
    completed = subprocess.run(
        [str(paths.exporter), "--version"],
        cwd=paths.exporter.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0
    assert "RTAB-Map:               0.23.8" in completed.stdout
