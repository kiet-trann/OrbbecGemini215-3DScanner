from pathlib import Path

import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.open_actions import OpenActionResult, OpenActionService  # noqa: E402


def test_open_obj_launches_existing_obj(tmp_path: Path) -> None:
    launched: list[str] = []
    obj = tmp_path / "part_cropped.obj"
    obj.touch()

    result = OpenActionService(launcher=launched.append).open_obj(obj)

    assert result == OpenActionResult(True, "Đã mở mô hình 3D")
    assert launched == [str(obj)]


def test_open_folder_launches_parent_folder(tmp_path: Path) -> None:
    launched: list[str] = []
    obj = tmp_path / "part_cropped.obj"
    obj.touch()

    result = OpenActionService(launcher=launched.append).open_folder(obj)

    assert result == OpenActionResult(True, "Đã mở thư mục kết quả")
    assert launched == [str(obj.parent)]


def test_open_obj_rejects_missing_model(tmp_path: Path) -> None:
    result = OpenActionService(launcher=lambda target: pytest.fail(target)).open_obj(tmp_path / "missing.obj")

    assert result == OpenActionResult(False, "Không tìm thấy mô hình để mở")


def test_open_obj_reports_shell_failure(tmp_path: Path) -> None:
    obj = tmp_path / "part_cropped.obj"
    obj.touch()

    result = OpenActionService(launcher=lambda target: (_ for _ in ()).throw(OSError("no association"))).open_obj(obj)

    assert result == OpenActionResult(False, "Không thể mở mô hình 3D")
