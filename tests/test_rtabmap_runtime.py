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
    bin_dir.mkdir(parents=True)
    executable = bin_dir / "RTABMap.exe"
    exporter = bin_dir / "rtabmap-export.exe"
    executable.touch()
    exporter.touch()
    return executable, exporter


def make_versioned_paths(project_root: Path, version: str) -> tuple[Path, Path]:
    runtime_root = project_root / "third_party" / "rtabmap" / f"RTABMap-{version}-win64"
    return make_paths(runtime_root)


def test_discover_requires_rtabmap_and_exporter(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="RTABMap.exe"):
        RtabmapRuntime.discover(tmp_path)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "RTABMap.exe").touch()
    with pytest.raises(FileNotFoundError, match="rtabmap-export.exe"):
        RtabmapRuntime.discover(tmp_path)


def test_resolve_selects_0238_by_default(tmp_path: Path) -> None:
    make_versioned_paths(tmp_path, "0.23.8")
    make_versioned_paths(tmp_path, "0.23.1")

    paths = RtabmapRuntime.resolve(tmp_path, environ={})

    assert paths.executable.parts[-3] == "RTABMap-0.23.8-win64"


def test_resolve_honors_explicit_rollback(tmp_path: Path) -> None:
    make_versioned_paths(tmp_path, "0.23.8")
    make_versioned_paths(tmp_path, "0.23.1")

    paths = RtabmapRuntime.resolve(
        tmp_path,
        environ={"SCANNER_RTABMAP_VERSION": "0.23.1"},
    )

    assert paths.executable.parts[-3] == "RTABMap-0.23.1-win64"


def test_resolve_falls_back_only_when_default_bundle_is_missing(tmp_path: Path) -> None:
    fallback = make_versioned_paths(tmp_path, "0.23.1")

    assert RtabmapRuntime.resolve(tmp_path, environ={}).executable == fallback[0]
    with pytest.raises(FileNotFoundError, match="0.23.8"):
        RtabmapRuntime.resolve(
            tmp_path,
            environ={"SCANNER_RTABMAP_VERSION": "0.23.8"},
        )


def test_resolve_rejects_unknown_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="0.23.8, 0.23.1"):
        RtabmapRuntime.resolve(
            tmp_path,
            environ={"SCANNER_RTABMAP_VERSION": "0.24.0"},
        )


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
