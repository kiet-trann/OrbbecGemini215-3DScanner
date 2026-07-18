import json
from pathlib import Path
import struct

import cv2
import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.glb_bundle import create_3d_viewer_glb


def write_textured_obj(directory: Path, *, texture_size: tuple[int, int]) -> Path:
    directory.mkdir()
    width, height = texture_size
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 2] = 220
    assert cv2.imwrite(str(directory / "texture.jpg"), image)
    (directory / "mesh.mtl").write_text("newmtl material\nmap_Kd texture.jpg\n", encoding="utf-8")
    obj = directory / "mesh.obj"
    obj.write_text(
        "\n".join(
            (
                "mtllib mesh.mtl",
                "v 0 0 0",
                "v 1 0 0",
                "v 0 1 0",
                "vt 0 0",
                "vt 1 0",
                "vt 0 1",
                "vn 0 0 1",
                "usemtl material",
                "f 1/1/1 2/2/1 3/3/1",
                "",
            )
        ),
        encoding="utf-8",
    )
    return obj


def read_glb(path: Path) -> tuple[dict[str, object], bytes]:
    data = path.read_bytes()
    magic, version, total_length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF"
    assert version == 2
    assert total_length == len(data)
    json_length, json_kind = struct.unpack_from("<I4s", data, 12)
    assert json_kind == b"JSON"
    json_start = 20
    document = json.loads(data[json_start:json_start + json_length].decode("utf-8"))
    binary_start = json_start + json_length
    binary_length, binary_kind = struct.unpack_from("<I4s", data, binary_start)
    assert binary_kind == b"BIN\x00"
    return document, data[binary_start + 8:binary_start + 8 + binary_length]


def embedded_image(document: dict[str, object], binary: bytes) -> np.ndarray:
    images = document["images"]
    buffer_views = document["bufferViews"]
    image = images[0]
    view = buffer_views[image["bufferView"]]
    offset = view.get("byteOffset", 0)
    encoded = np.frombuffer(binary[offset:offset + view["byteLength"]], dtype=np.uint8)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    assert decoded is not None
    return decoded


def test_create_3d_viewer_glb_embeds_capped_texture_without_changing_source(tmp_path: Path) -> None:
    source = write_textured_obj(tmp_path / "raw", texture_size=(8192, 4096))
    output = tmp_path / "raw" / "viewer" / "mesh.glb"

    glb = create_3d_viewer_glb(source, output)

    document, binary = read_glb(glb)
    image = embedded_image(document, binary)
    assert glb == output
    assert image.shape[:2] == (2048, 4096)
    assert document["asset"]["version"] == "2.0"
    assert document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] == {"index": 0}
    assert document["images"][0]["mimeType"] == "image/jpeg"
    source_image = cv2.imread(str(tmp_path / "raw" / "texture.jpg"), cv2.IMREAD_UNCHANGED)
    assert source_image is not None and source_image.shape[:2] == (4096, 8192)
