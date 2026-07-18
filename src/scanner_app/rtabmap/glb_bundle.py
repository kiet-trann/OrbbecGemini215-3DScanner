"""Write self-contained textured GLB files from RTAB-Map OBJ bundles."""

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import struct

import cv2
import numpy as np


MAX_TEXTURE_DIMENSION = 4096
_GLB_MAGIC = b"glTF"
_GLB_VERSION = 2
_JSON_CHUNK = b"JSON"
_BIN_CHUNK = b"BIN\x00"


@dataclass(frozen=True)
class _FaceVertex:
    position: int
    texcoord: int
    normal: int


def create_3d_viewer_glb(
    source_obj: Path,
    output_path: Path,
    max_texture_dimension: int = MAX_TEXTURE_DIMENSION,
) -> Path:
    """Create an atomic GLB containing an OBJ mesh and its one diffuse texture."""
    source_obj = source_obj.resolve()
    output_path = output_path.resolve()
    if max_texture_dimension <= 0:
        raise ValueError("max_texture_dimension must be positive")
    if not source_obj.is_file():
        raise FileNotFoundError(f"OBJ does not exist: {source_obj}")
    if output_path.exists():
        raise FileExistsError(f"3D Viewer model already exists: {output_path}")

    positions, texcoords, normals, faces, material, material_files = _read_textured_obj(source_obj)
    texture = _find_single_diffuse_texture(material, material_files)
    vertices, indices = _build_vertices(positions, texcoords, normals, faces)
    jpeg = _encode_capped_jpeg(texture, max_texture_dimension)
    payload = _encode_glb(vertices, indices, jpeg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"3D Viewer temporary model already exists: {temporary}")
    try:
        temporary.write_bytes(payload)
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return output_path


def _read_textured_obj(source_obj: Path) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float]],
    list[tuple[float, float, float]],
    list[tuple[_FaceVertex, _FaceVertex, _FaceVertex]],
    str,
    list[Path],
]:
    positions: list[tuple[float, float, float]] = []
    texcoords: list[tuple[float, float]] = []
    normals: list[tuple[float, float, float]] = []
    faces: list[tuple[_FaceVertex, _FaceVertex, _FaceVertex]] = []
    material_files: list[Path] = []
    used_materials: set[str] = set()
    active_material: str | None = None

    for line in source_obj.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v" and len(fields) >= 4:
            positions.append((float(fields[1]), float(fields[2]), float(fields[3])))
        elif fields[0] == "vt" and len(fields) >= 3:
            texcoords.append((float(fields[1]), float(fields[2])))
        elif fields[0] == "vn" and len(fields) >= 4:
            normals.append((float(fields[1]), float(fields[2]), float(fields[3])))
        elif fields[0] == "mtllib" and len(fields) == 2:
            material_files.append((source_obj.parent / fields[1]).resolve())
        elif fields[0] == "usemtl" and len(fields) == 2:
            active_material = fields[1]
        elif fields[0] == "f" and len(fields) >= 4:
            if active_material is None:
                raise ValueError(f"OBJ face has no material: {source_obj}")
            corners = [_parse_face_vertex(token, len(positions), len(texcoords), len(normals)) for token in fields[1:]]
            for index in range(1, len(corners) - 1):
                faces.append((corners[0], corners[index], corners[index + 1]))
                used_materials.add(active_material)

    if not positions or not texcoords or not normals or not faces:
        raise ValueError(f"OBJ must contain positions, UVs, normals, and faces: {source_obj}")
    if len(material_files) != 1 or not material_files[0].is_file():
        raise ValueError(f"OBJ must reference one existing MTL file: {source_obj}")
    if len(used_materials) != 1:
        raise ValueError(f"OBJ must use exactly one textured material: {source_obj}")
    return positions, texcoords, normals, faces, used_materials.pop(), material_files


def _parse_face_vertex(token: str, positions: int, texcoords: int, normals: int) -> _FaceVertex:
    values = token.split("/")
    if len(values) != 3 or not all(values):
        raise ValueError(f"OBJ face must include position, UV, and normal: {token}")
    return _FaceVertex(
        _resolve_index(values[0], positions),
        _resolve_index(values[1], texcoords),
        _resolve_index(values[2], normals),
    )


def _resolve_index(value: str, count: int) -> int:
    index = int(value)
    resolved = index - 1 if index > 0 else count + index
    if not 0 <= resolved < count:
        raise ValueError(f"OBJ index is outside its declared data: {value}")
    return resolved


def _find_single_diffuse_texture(material: str, material_files: list[Path]) -> Path:
    active: str | None = None
    texture: Path | None = None
    for material_file in material_files:
        for line in material_file.read_text(encoding="utf-8", errors="replace").splitlines():
            fields = line.split(maxsplit=1)
            if len(fields) != 2:
                continue
            if fields[0] == "newmtl":
                active = fields[1]
            elif active == material and fields[0].lower() == "map_kd":
                candidate = (material_file.parent / fields[1]).resolve()
                if texture is not None:
                    raise ValueError(f"Material has more than one diffuse texture: {material_file}")
                texture = candidate
    if texture is None or not texture.is_file():
        raise ValueError(f"Material has no usable diffuse texture: {material}")
    return texture


def _build_vertices(
    positions: list[tuple[float, float, float]],
    texcoords: list[tuple[float, float]],
    normals: list[tuple[float, float, float]],
    faces: list[tuple[_FaceVertex, _FaceVertex, _FaceVertex]],
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    lookup: dict[_FaceVertex, int] = {}
    output_positions: list[tuple[float, float, float]] = []
    output_texcoords: list[tuple[float, float]] = []
    output_normals: list[tuple[float, float, float]] = []
    indices: list[int] = []
    for face in faces:
        for corner in face:
            index = lookup.get(corner)
            if index is None:
                index = len(output_positions)
                lookup[corner] = index
                output_positions.append(positions[corner.position])
                u, v = texcoords[corner.texcoord]
                output_texcoords.append((u, 1.0 - v))
                output_normals.append(normals[corner.normal])
            indices.append(index)
    return {
        "positions": np.asarray(output_positions, dtype=np.float32),
        "normals": np.asarray(output_normals, dtype=np.float32),
        "texcoords": np.asarray(output_texcoords, dtype=np.float32),
    }, np.asarray(indices, dtype=np.uint32)


def _encode_capped_jpeg(texture: Path, max_texture_dimension: int) -> bytes:
    image = cv2.imread(str(texture), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Unable to decode texture: {texture}")
    height, width = image.shape[:2]
    scale = min(1.0, max_texture_dimension / max(width, height))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (round(width * scale), round(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    if image.ndim == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise OSError(f"Unable to encode compatible texture: {texture}")
    return encoded.tobytes()


def _encode_glb(vertices: dict[str, np.ndarray], indices: np.ndarray, jpeg: bytes) -> bytes:
    binary = bytearray()
    views: list[dict[str, int]] = []
    for values, target in (
        (vertices["positions"].tobytes(), 34962),
        (vertices["normals"].tobytes(), 34962),
        (vertices["texcoords"].tobytes(), 34962),
        (indices.tobytes(), 34963),
        (jpeg, None),
    ):
        offset = len(binary)
        binary.extend(values)
        while len(binary) % 4:
            binary.append(0)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(values)}
        if target is not None:
            view["target"] = target
        views.append(view)

    positions = vertices["positions"]
    document = {
        "asset": {"version": "2.0", "generator": "3D Scanner"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
            "indices": 3,
            "material": 0,
            "mode": 4,
        }]}],
        "materials": [{"pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 1.0,
        }, "doubleSided": True}],
        "textures": [{"sampler": 0, "source": 0}],
        "samplers": [{}],
        "images": [{"bufferView": 4, "mimeType": "image/jpeg"}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
             "min": positions.min(axis=0).tolist(), "max": positions.max(axis=0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(vertices["normals"]), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(vertices["texcoords"]), "type": "VEC2"},
            {"bufferView": 3, "componentType": 5125, "count": len(indices), "type": "SCALAR"},
        ],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    binary_chunk = bytes(binary)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    return b"".join((
        struct.pack("<4sII", _GLB_MAGIC, _GLB_VERSION, total_length),
        struct.pack("<I4s", len(json_chunk), _JSON_CHUNK),
        json_chunk,
        struct.pack("<I4s", len(binary_chunk), _BIN_CHUNK),
        binary_chunk,
    ))
