from pathlib import Path

import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.open_actions import OpenActionResult, OpenActionService


def test_open_obj_launches_existing_obj(tmp_path: Path) -> None:
    launched: list[str] = []
    obj = tmp_path / "part_cropped.obj"
    obj.touch()

    result = OpenActionService(launcher=launched.append).open_obj(obj)

    assert result == OpenActionResult(True, f"Opened: {obj}")
    assert launched == [str(obj)]


def test_open_folder_rejects_missing_crop_output(tmp_path: Path) -> None:
    result = OpenActionService(launcher=lambda target: pytest.fail(target)).open_folder(tmp_path / "missing.obj")

    assert result == OpenActionResult(False, "Cropped OBJ is no longer available")


def test_open_obj_reports_shell_failure(tmp_path: Path) -> None:
    obj = tmp_path / "part_cropped.obj"
    obj.touch()

    result = OpenActionService(launcher=lambda target: (_ for _ in ()).throw(OSError("no association"))).open_obj(obj)

    assert result == OpenActionResult(False, f"Could not open: {obj}")
