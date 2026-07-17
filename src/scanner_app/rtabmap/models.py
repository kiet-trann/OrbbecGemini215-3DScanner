"""Value objects shared by RTAB-Map integration services."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RtabmapPaths:
    executable: Path
    exporter: Path


@dataclass(frozen=True)
class RuntimeStatus:
    running: bool
    message: str

