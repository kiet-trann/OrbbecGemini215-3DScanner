"""Filter a textured OBJ bundle without modifying its raw export."""

from dataclasses import dataclass
from pathlib import Path
import shutil

import numpy as np


@dataclass(frozen=True)
class CropRectangle:
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass(frozen=True)
class CameraProjection:
    world_to_clip: np.ndarray
    viewport_width: int
    viewport_height: int

    def project(self, vertex: tuple[float, float, float, float]) -> tuple[float, float] | None:
        clip = self.world_to_clip @ np.asarray(vertex, dtype=np.float64)
        if clip[3] <= 0:
            return None
        ndc = clip[:3] / clip[3]
        if not (-1.0 <= ndc[0] <= 1.0 and -1.0 <= ndc[1] <= 1.0 and -1.0 <= ndc[2] <= 1.0):
            return None
        return ((ndc[0] + 1.0) * self.viewport_width / 2.0, (1.0 - ndc[1]) * self.viewport_height / 2.0)


@dataclass(frozen=True)
class CropResult:
    output_dir: Path
    obj: Path


def projection_for_bounds(
    vertices: list[tuple[float, float, float]], *, viewport_width: int, viewport_height: int
) -> CameraProjection:
    points = np.asarray(vertices, dtype=np.float64)
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    extent = np.maximum(maximum - minimum, 1e-9)
    scale = 2.0 / extent
    translate = -(maximum + minimum) / extent
    matrix = np.eye(4, dtype=np.float64)
    matrix[0, 0], matrix[1, 1], matrix[2, 2] = scale
    matrix[:3, 3] = translate
    return CameraProjection(matrix, viewport_width=viewport_width, viewport_height=viewport_height)


def crop_obj_bundle(source_obj: Path, rectangle: CropRectangle, projection: CameraProjection, output_dir: Path) -> CropResult:
    lines = source_obj.read_text(encoding="utf-8", errors="replace").splitlines()
    vertices: list[tuple[float, float, float, float]] = []
    kept: list[str] = []
    faces = 0
    for line in lines:
        if line.startswith("v "):
            values = [float(value) for value in line.split()[1:]]
            vertices.append(tuple((values + [1.0])[:4]))
            kept.append(line)
        elif line.startswith("f "):
            indices = [int(token.split("/")[0]) for token in line.split()[1:]]
            points = [projection.project(vertices[index - 1]) for index in indices]
            if all(point is not None and rectangle.contains(*point) for point in points):
                kept.append(line)
                faces += 1
        else:
            kept.append(line)
    if faces == 0:
        raise ValueError("Crop selected no faces; enlarge or reposition the rectangle")
    temporary = output_dir.with_name(output_dir.name + ".tmp")
    temporary.mkdir(parents=True)
    obj = temporary / f"{source_obj.stem}_cropped.obj"
    obj.write_text("\n".join(kept) + "\n", encoding="utf-8")
    for material in source_obj.parent.glob("*.mtl"):
        shutil.copy2(material, temporary / material.name)
        for line in material.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("map_kd "):
                texture = source_obj.parent / line.split(maxsplit=1)[1]
                if texture.is_file():
                    shutil.copy2(texture, temporary / texture.name)
    temporary.replace(output_dir)
    return CropResult(output_dir=output_dir, obj=output_dir / obj.name)
