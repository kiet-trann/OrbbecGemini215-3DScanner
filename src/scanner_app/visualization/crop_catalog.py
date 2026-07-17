"""Read-only discovery of cropped OBJ bundles."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
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
        outputs: list[CroppedObjOutput] = []
        for root in self._discovery_roots():
            for path in root.rglob("*_cropped.obj"):
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

    def _discovery_roots(self) -> list[Path]:
        roots = [self._output_root] if self._output_root.is_dir() else []
        try:
            siblings = self._output_root.parent.iterdir()
        except OSError:
            return roots
        for sibling in siblings:
            if sibling == self._output_root or not sibling.is_dir():
                continue
            if self._has_session_catalog(sibling):
                roots.append(sibling)
        return roots

    @staticmethod
    def _has_session_catalog(root: Path) -> bool:
        try:
            payload = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict) and isinstance(payload.get("sessions"), list)
