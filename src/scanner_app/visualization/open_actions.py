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
            return OpenActionResult(False, "Không tìm thấy mô hình để mở")
        return self._launch(path, "Đã mở mô hình 3D", "Không thể mở mô hình 3D")

    def open_folder(self, path: Path) -> OpenActionResult:
        if not path.is_file():
            return OpenActionResult(False, "Không tìm thấy mô hình để mở")
        return self._launch(path.parent, "Đã mở thư mục kết quả", "Không thể mở thư mục kết quả")

    def _launch(self, target: Path, message: str, failure_message: str) -> OpenActionResult:
        try:
            self._launcher(str(target))
        except OSError:
            return OpenActionResult(False, failure_message)
        return OpenActionResult(True, message)
