import os
from pathlib import Path

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.visualization.crop_catalog import CroppedObjCatalog


def test_refresh_lists_only_cropped_objs_newest_first_without_writing_them(tmp_path: Path) -> None:
    old = tmp_path / "cropped_old" / "old_cropped.obj"
    new = tmp_path / "nested" / "cropped_new" / "new_cropped.obj"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    raw = tmp_path / "raw" / "scan_mesh.obj"
    raw.parent.mkdir()
    raw.write_text("raw", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))
    original_mtime = new.stat().st_mtime_ns

    outputs = CroppedObjCatalog(tmp_path).refresh()

    assert [output.path.name for output in outputs] == ["new_cropped.obj", "old_cropped.obj"]
    assert new.stat().st_mtime_ns == original_mtime


def test_refresh_ignores_missing_root(tmp_path: Path) -> None:
    assert CroppedObjCatalog(tmp_path / "missing").refresh() == []
