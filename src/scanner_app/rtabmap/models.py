"""Value objects shared by RTAB-Map integration services."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RtabmapPaths:
    executable: Path
    exporter: Path


@dataclass(frozen=True)
class RuntimeStatus:
    running: bool
    message: str


@dataclass(frozen=True)
class SavedSession:
    path: Path
    size_bytes: int
    modified_at: datetime

    def to_json(self) -> dict[str, str | int]:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at.isoformat(),
        }
