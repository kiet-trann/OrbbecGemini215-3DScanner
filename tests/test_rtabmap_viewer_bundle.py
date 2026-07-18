from pathlib import Path

import cv2
import numpy as np
import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.viewer_bundle import create_3d_viewer_bundle


def write_textured_bundle(directory: Path, *, size: tuple[int, int]) -> Path:
    directory.mkdir()
    width, height = size
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 1] = 160
    texture = directory / "texture.jpg"
    assert cv2.imwrite(str(texture), image)
    (directory / "mesh.mtl").write_text("newmtl material\nmap_Kd texture.jpg\n", encoding="utf-8")
    obj = directory / "mesh.obj"
    obj.write_text(
        "mtllib mesh.mtl\nusemtl material\nv 0 0 0\nvt 0 0\nvn 0 0 1\nf 1/1/1 1/1/1 1/1/1\n",
        encoding="utf-8",
    )
    return obj


def image_size(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert image is not None
    height, width = image.shape[:2]
    return width, height


def test_create_3d_viewer_bundle_caps_texture_and_preserves_source(tmp_path: Path) -> None:
    raw = write_textured_bundle(tmp_path / "raw", size=(8192, 4096))

    bundle = create_3d_viewer_bundle(raw, tmp_path / "raw" / "viewer")

    assert bundle.obj == tmp_path / "raw" / "viewer" / "mesh.obj"
    assert image_size(tmp_path / "raw" / "texture.jpg") == (8192, 4096)
    assert image_size(bundle.textures[0]) == (4096, 2048)
    assert "map_Kd texture_viewer.jpg" in bundle.mtl[0].read_text(encoding="utf-8")
    assert "mtllib mesh.mtl" in bundle.obj.read_text(encoding="utf-8")


def test_create_3d_viewer_bundle_rejects_unreadable_texture_without_publishing_output(tmp_path: Path) -> None:
    raw = write_textured_bundle(tmp_path / "raw", size=(64, 64))
    (tmp_path / "raw" / "texture.jpg").write_bytes(b"not an image")

    with pytest.raises(ValueError, match="Unable to decode texture"):
        create_3d_viewer_bundle(raw, tmp_path / "raw" / "viewer")

    assert not (tmp_path / "raw" / "viewer").exists()
