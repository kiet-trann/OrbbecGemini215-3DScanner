from pathlib import Path

import numpy as np
import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.obj_crop import CameraProjection, CropRectangle, crop_obj_bundle


def write_bundle(directory: Path) -> Path:
    directory.mkdir()
    (directory / "texture.jpg").write_bytes(b"texture")
    (directory / "mesh.mtl").write_text("newmtl material\nmap_Kd texture.jpg\n", encoding="utf-8")
    obj = directory / "mesh.obj"
    obj.write_text(
        "mtllib mesh.mtl\nusemtl material\nv -0.5 -0.5 0 1\nv 0.5 -0.5 0 1\nv 0 0.5 0 1\nv 2 2 0 1\nf 1 2 3\nf 2 3 4\n",
        encoding="utf-8",
    )
    return obj


def test_crop_preserves_textures_and_only_keeps_faces_inside_screen_rectangle(tmp_path: Path) -> None:
    source = write_bundle(tmp_path / "raw")
    result = crop_obj_bundle(
        source,
        CropRectangle(0, 0, 800, 600),
        CameraProjection(np.eye(4), viewport_width=800, viewport_height=600),
        tmp_path / "cropped",
    )

    assert result.obj.name == "mesh_cropped.obj"
    assert result.obj.read_text(encoding="utf-8").count("\nf ") == 1
    assert (result.output_dir / "mesh.mtl").is_file()
    assert (result.output_dir / "texture.jpg").read_bytes() == b"texture"


def test_crop_rejects_an_empty_selection_without_creating_output(tmp_path: Path) -> None:
    source = write_bundle(tmp_path / "raw")

    with pytest.raises(ValueError, match="Crop selected no faces"):
        crop_obj_bundle(
            source,
            CropRectangle(900, 700, 1000, 800),
            CameraProjection(np.eye(4), viewport_width=800, viewport_height=600),
            tmp_path / "cropped",
        )

    assert not (tmp_path / "cropped").exists()
