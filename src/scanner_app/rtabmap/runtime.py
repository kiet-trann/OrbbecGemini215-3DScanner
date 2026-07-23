"""Locate and launch RTAB-Map without opening an RGB-D camera stream."""

from collections.abc import Callable, Mapping
import os
from pathlib import Path
import subprocess
from typing import Protocol

from scanner_app.rtabmap.models import RtabmapPaths, RuntimeStatus


class Process(Protocol):
    def poll(self) -> int | None:
        """Return the process exit code, or ``None`` while it is running."""


ProcessFactory = Callable[[list[str], Path], Process]

DEFAULT_RTABMAP_VERSION = "0.23.8"
FALLBACK_RTABMAP_VERSION = "0.23.1"
RTABMAP_VERSION_ENV = "SCANNER_RTABMAP_VERSION"
SUPPORTED_RTABMAP_VERSIONS = (DEFAULT_RTABMAP_VERSION, FALLBACK_RTABMAP_VERSION)


def _runtime_root(project_root: Path, version: str) -> Path:
    return project_root / "third_party" / "rtabmap" / f"RTABMap-{version}-win64"


def _start_process(args: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(args, cwd=cwd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


class RtabmapRuntime:
    def __init__(self, paths: RtabmapPaths, *, process_factory: ProcessFactory = _start_process) -> None:
        self._paths = paths
        self._process_factory = process_factory
        self._process: Process | None = None

    @classmethod
    def discover(cls, root: Path) -> RtabmapPaths:
        bin_dir = root / "bin"
        executable = bin_dir / "RTABMap.exe"
        exporter = bin_dir / "rtabmap-export.exe"
        for path in (executable, exporter):
            if not path.is_file():
                raise FileNotFoundError(f"Required RTAB-Map file is missing: {path}")
        return RtabmapPaths(executable=executable, exporter=exporter)

    @classmethod
    def resolve(
        cls,
        project_root: Path,
        *,
        environ: Mapping[str, str] = os.environ,
    ) -> RtabmapPaths:
        requested = environ.get(RTABMAP_VERSION_ENV)
        if requested is not None:
            if requested not in SUPPORTED_RTABMAP_VERSIONS:
                supported = ", ".join(SUPPORTED_RTABMAP_VERSIONS)
                raise ValueError(f"Unsupported RTAB-Map version {requested!r}; expected {supported}")
            return cls.discover(_runtime_root(project_root, requested))
        try:
            return cls.discover(_runtime_root(project_root, DEFAULT_RTABMAP_VERSION))
        except FileNotFoundError as primary_error:
            try:
                return cls.discover(_runtime_root(project_root, FALLBACK_RTABMAP_VERSION))
            except FileNotFoundError:
                raise primary_error

    @classmethod
    def from_paths(
        cls,
        executable: Path,
        exporter: Path,
        *,
        process_factory: ProcessFactory = _start_process,
    ) -> "RtabmapRuntime":
        return cls(RtabmapPaths(executable=executable, exporter=exporter), process_factory=process_factory)

    def status(self) -> RuntimeStatus:
        running = self._process is not None and self._process.poll() is None
        return RuntimeStatus(running=running, message="RTAB-Map is running" if running else "RTAB-Map is not running")

    def launch(self) -> RuntimeStatus:
        if self._process is not None and self._process.poll() is None:
            return RuntimeStatus(running=True, message="RTAB-Map is already running")
        self._process = self._process_factory([str(self._paths.executable)], self._paths.executable.parent)
        return RuntimeStatus(running=True, message="RTAB-Map started")
