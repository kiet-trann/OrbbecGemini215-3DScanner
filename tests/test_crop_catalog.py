import os
import json
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


def test_refresh_prefers_compatible_child_and_does_not_duplicate_the_raw_crop(tmp_path: Path) -> None:
    raw = tmp_path / "cropped" / "model_cropped.obj"
    viewer = tmp_path / "cropped" / "viewer" / "model_cropped.obj"
    raw.parent.mkdir(parents=True)
    viewer.parent.mkdir(parents=True)
    raw.write_text("raw", encoding="utf-8")
    viewer.write_text("viewer", encoding="utf-8")

    outputs = CroppedObjCatalog(tmp_path).refresh()

    assert [output.path for output in outputs] == [viewer.resolve()]
    assert outputs[0].output_dir == viewer.parent.resolve()


def test_refresh_includes_crops_from_sibling_roots_with_session_catalogs(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    current_root = outputs / "scanner_3d"
    prior_root = outputs / "prior_scanner"
    unrelated_root = outputs / "obj"
    current_crop = current_root / "current" / "current_cropped.obj"
    prior_crop = prior_root / "previous" / "previous_cropped.obj"
    unrelated_crop = unrelated_root / "not_a_session_cropped.obj"
    for crop in (current_crop, prior_crop, unrelated_crop):
        crop.parent.mkdir(parents=True)
        crop.write_text(crop.stem, encoding="utf-8")
    (prior_root / "catalog.json").write_text(json.dumps({"sessions": []}), encoding="utf-8")

    discovered = CroppedObjCatalog(current_root).refresh()

    assert {output.path for output in discovered} == {current_crop.resolve(), prior_crop.resolve()}
