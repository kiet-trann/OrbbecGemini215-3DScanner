"""Validated Windows shell actions for completed cropped OBJ bundles."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class OpenActionResult:
    opened: bool
    message: str


class OpenActionService:
    def __init__(self, launcher: Callable[[str], None] | None = None) -> None:
        self._launcher = launcher or os.startfile

    def open_obj(self, path: Path) -> OpenActionResult:
        if not path.is_file():
            return OpenActionResult(False, "Cropped OBJ is no longer available")
        return self._launch(path, f"Opened: {path}")

    def open_folder(self, path: Path) -> OpenActionResult:
        if not path.is_file():
            return OpenActionResult(False, "Cropped OBJ is no longer available")
        return self._launch(path.parent, f"Opened folder: {path.parent}")

    def _launch(self, target: Path, message: str) -> OpenActionResult:
        try:
            self._launcher(str(target))
        except OSError:
            return OpenActionResult(False, f"Could not open: {target}")
        return OpenActionResult(True, message)
