import math
from pathlib import Path

import cv2
import numpy as np
import pytest

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.obj_crop import (
    CameraProjection,
    CropRectangle,
    crop_obj_bundle,
    perspective_projection_for_bounds,
    preview_stride,
    projection_for_bounds,
    sample_projected_vertices,
    sample_visible_projected_vertices,
)


def write_bundle(directory: Path, texture_size: tuple[int, int] = (64, 64)) -> Path:
    directory.mkdir()
    width, height = texture_size
    assert cv2.imwrite(str(directory / "texture.jpg"), np.zeros((height, width, 3), dtype=np.uint8))
    (directory / "mesh.mtl").write_text("newmtl material\nmap_Kd texture.jpg\n", encoding="utf-8")
    obj = directory / "mesh.obj"
    obj.write_text(
        "\n".join((
            "mtllib mesh.mtl", "usemtl material", "v -0.5 -0.5 0", "v 0.5 -0.5 0",
            "v 0 0.5 0", "v 2 2 0", "vt 0 0", "vt 1 0", "vt 0 1", "vt 1 1",
            "vn 0 0 1", "f 1/1/1 2/2/1 3/3/1", "f 2/2/1 3/3/1 4/4/1", "",
        )),
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
    assert (result.output_dir / "texture.jpg").is_file()


def test_crop_creates_compatible_child_without_changing_raw_crop_texture(tmp_path: Path) -> None:
    source = write_bundle(tmp_path / "raw", texture_size=(4097, 2049))

    result = crop_obj_bundle(
        source,
        CropRectangle(0, 0, 800, 600),
        CameraProjection(np.eye(4), viewport_width=800, viewport_height=600),
        tmp_path / "cropped",
    )

    raw_image = cv2.imread(str(result.output_dir / "texture.jpg"), cv2.IMREAD_UNCHANGED)
    assert raw_image is not None and raw_image.shape[:2] == (2049, 4097)
    assert result.viewer_model.is_file()
    assert result.viewer_model.suffix == ".glb"
    assert result.viewer_model.read_bytes()[:4] == b"glTF"


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


def test_projection_for_bounds_maps_the_mesh_extent_to_the_preview() -> None:
    projection = projection_for_bounds(
        [(-2.0, -1.0, 0.0), (2.0, 3.0, 4.0)],
        viewport_width=800,
        viewport_height=600,
    )

    assert projection.project((-2.0, -1.0, 0.0, 1.0)) == (0.0, 600.0)
    assert projection.project((2.0, 3.0, 4.0, 1.0)) == (800.0, 0.0)


def test_perspective_projection_keeps_mesh_vertices_visible_after_rotation() -> None:
    projection = perspective_projection_for_bounds(
        [(-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)],
        viewport_width=800,
        viewport_height=600,
        yaw=0.6,
        pitch=-0.25,
        distance=3.5,
    )

    first = projection.project((-1.0, -1.0, -1.0, 1.0))
    second = projection.project((1.0, 1.0, 1.0, 1.0))

    assert first is not None and second is not None
    assert first != second


def test_perspective_projection_uses_rtabmap_axes_for_named_views() -> None:
    vertices = [(-1.0, -1.0, -1.0), (1.0, 1.0, 1.0)]

    def clip_distance(yaw: float, pitch: float, point: tuple[float, float, float]) -> float:
        projection = perspective_projection_for_bounds(
            vertices, viewport_width=800, viewport_height=600,
            yaw=yaw, pitch=pitch, distance=3.5,
        )
        return float((projection.world_to_clip @ np.array((*point, 1.0)))[3])

    assert clip_distance(-math.pi / 2.0, 0.0, (1.0, 0.0, 0.0)) < clip_distance(-math.pi / 2.0, 0.0, (-1.0, 0.0, 0.0))
    assert clip_distance(math.pi / 2.0, 0.0, (-1.0, 0.0, 0.0)) < clip_distance(math.pi / 2.0, 0.0, (1.0, 0.0, 0.0))
    assert clip_distance(0.0, math.pi / 2.0, (0.0, 0.0, 1.0)) < clip_distance(0.0, math.pi / 2.0, (0.0, 0.0, -1.0))
    assert clip_distance(0.0, -math.pi / 2.0, (0.0, 0.0, -1.0)) < clip_distance(0.0, -math.pi / 2.0, (0.0, 0.0, 1.0))


def test_preview_stride_caps_an_interactive_mesh() -> None:
    assert preview_stride(2_800, 700) == 4
    assert preview_stride(1_401, 700) == 3
    assert preview_stride(50, 700) == 1


def test_sample_projected_vertices_uses_the_crop_projection() -> None:
    projection = CameraProjection(np.eye(4), viewport_width=800, viewport_height=600)

    points = sample_projected_vertices([(-1, -1, 0), (1, 1, 0)], projection, maximum_items=10)

    assert points == [(0.0, 600.0), (800.0, 0.0)]


def test_visible_projection_keeps_only_the_nearest_overlapping_point() -> None:
    projection = CameraProjection(np.eye(4), viewport_width=800, viewport_height=600)

    points = sample_visible_projected_vertices([(0, 0, 0.8), (0, 0, -0.8)], projection, maximum_items=10)

    assert points == [(400.0, 300.0)]
