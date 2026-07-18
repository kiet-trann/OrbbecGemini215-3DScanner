"""Create Wavefront OBJ bundles compatible with Windows 3D Viewer."""

from dataclasses import dataclass
from pathlib import Path
import shutil

import cv2


MAX_TEXTURE_DIMENSION = 4096


@dataclass(frozen=True)
class CompatibleObjBundle:
    output_dir: Path
    obj: Path
    mtl: tuple[Path, ...]
    textures: tuple[Path, ...]


def create_3d_viewer_bundle(
    source_obj: Path,
    output_dir: Path,
    max_texture_dimension: int = MAX_TEXTURE_DIMENSION,
) -> CompatibleObjBundle:
    """Copy a textured OBJ bundle with diffuse textures capped for 3D Viewer."""
    source_obj = source_obj.resolve()
    output_dir = output_dir.resolve()
    if max_texture_dimension <= 0:
        raise ValueError("max_texture_dimension must be positive")
    if not source_obj.is_file():
        raise FileNotFoundError(f"OBJ does not exist: {source_obj}")
    if output_dir.exists():
        raise FileExistsError(f"Compatible output already exists: {output_dir}")

    temporary = output_dir.with_name(output_dir.name + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"Compatible temporary output already exists: {temporary}")
    temporary.mkdir(parents=True)
    try:
        target_obj = temporary / source_obj.name
        shutil.copy2(source_obj, target_obj)
        materials, textures = _copy_rewritten_materials(
            source_obj,
            temporary,
            max_texture_dimension,
        )
        temporary.replace(output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return CompatibleObjBundle(
        output_dir=output_dir,
        obj=output_dir / target_obj.name,
        mtl=tuple(output_dir / material.name for material in materials),
        textures=tuple(output_dir / texture.name for texture in textures),
    )


def _copy_rewritten_materials(
    source_obj: Path,
    destination_dir: Path,
    max_texture_dimension: int,
) -> tuple[list[Path], list[Path]]:
    source_materials = _referenced_materials(source_obj)
    materials: list[Path] = []
    textures: list[Path] = []
    for source_mtl in source_materials:
        rewritten: list[str] = []
        found_texture = False
        for line in source_mtl.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.lower().startswith("map_kd "):
                rewritten.append(line)
                continue
            source_texture = (source_mtl.parent / line.split(maxsplit=1)[1]).resolve()
            target_texture = destination_dir / f"{source_texture.stem}_viewer.jpg"
            _write_capped_jpeg(source_texture, target_texture, max_texture_dimension)
            rewritten.append(f"map_Kd {target_texture.name}")
            textures.append(target_texture)
            found_texture = True
        if not found_texture:
            raise ValueError(f"No usable diffuse texture found in material: {source_mtl}")
        target_mtl = destination_dir / source_mtl.name
        target_mtl.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
        materials.append(target_mtl)
    return materials, textures


def _referenced_materials(source_obj: Path) -> list[Path]:
    materials: list[Path] = []
    for line in source_obj.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.lower().startswith("mtllib "):
            continue
        material = (source_obj.parent / line.split(maxsplit=1)[1]).resolve()
        if not material.is_file():
            raise FileNotFoundError(f"Material file does not exist: {material}")
        materials.append(material)
    if not materials:
        raise ValueError(f"OBJ does not reference a material file: {source_obj}")
    return materials


def _write_capped_jpeg(source_texture: Path, target_texture: Path, max_texture_dimension: int) -> None:
    image = cv2.imread(str(source_texture), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Unable to decode texture: {source_texture}")
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
    if not cv2.imwrite(str(target_texture), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(f"Unable to write compatible texture: {target_texture}")
