from pathlib import Path

import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.runtime import RtabmapRuntime


class FakeProcess:
    def __init__(self) -> None:
        self.return_code: int | None = None

    def poll(self) -> int | None:
        return self.return_code


def make_paths(root: Path) -> tuple[Path, Path]:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "RTABMap.exe"
    exporter = bin_dir / "rtabmap-export.exe"
    executable.touch()
    exporter.touch()
    return executable, exporter


def test_discover_requires_rtabmap_and_exporter(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="RTABMap.exe"):
        RtabmapRuntime.discover(tmp_path)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "RTABMap.exe").touch()
    with pytest.raises(FileNotFoundError, match="rtabmap-export.exe"):
        RtabmapRuntime.discover(tmp_path)


def test_launch_starts_only_when_not_running(tmp_path: Path) -> None:
    executable, exporter = make_paths(tmp_path)
    spawned: list[tuple[list[str], Path]] = []

    def process_factory(args: list[str], cwd: Path) -> FakeProcess:
        spawned.append((args, cwd))
        return FakeProcess()

    runtime = RtabmapRuntime.from_paths(executable, exporter, process_factory=process_factory)

    assert runtime.launch().running
    assert spawned == [([str(executable)], executable.parent)]
    assert runtime.launch().message == "RTAB-Map is already running"
