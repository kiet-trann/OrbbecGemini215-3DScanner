"""Read-only discovery of cropped OBJ bundles."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class CroppedObjOutput:
    path: Path
    output_dir: Path
    size_bytes: int
    modified_at: datetime


class CroppedObjCatalog:
    def __init__(self, output_root: Path) -> None:
        self._output_root = output_root.resolve()

    def refresh(self) -> list[CroppedObjOutput]:
        if not self._output_root.is_dir():
            return []
        outputs: list[CroppedObjOutput] = []
        for path in self._output_root.rglob("*_cropped.obj"):
            try:
                stat = path.stat()
            except OSError:
                continue
            resolved = path.resolve()
            outputs.append(
                CroppedObjOutput(
                    path=resolved,
                    output_dir=resolved.parent,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
        return sorted(outputs, key=lambda output: output.modified_at, reverse=True)
