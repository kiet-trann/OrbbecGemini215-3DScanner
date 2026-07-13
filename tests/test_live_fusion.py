from dataclasses import dataclass

import numpy as np

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.fusion.live import LiveFusionEngine


@dataclass(frozen=True)
class FakeKeyframe:
    camera_to_world: np.ndarray


class FakeVolume:
    def __init__(self) -> None:
        self.integrated: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    def integrate_keyframe(
        self,
        keyframe: FakeKeyframe,
        roi_min: np.ndarray,
        roi_max: np.ndarray,
    ) -> int:
        self.integrated.append(
            (
                keyframe.camera_to_world.copy(),
                roi_min.copy(),
                roi_max.copy(),
            )
        )
        return 42

    def extract_triangle_mesh(self) -> dict[str, int]:
        return {"count": len(self.integrated)}


def test_rebuild_discards_live_volume_and_integrates_optimized_keyframes() -> None:
    keyframes = (FakeKeyframe(np.eye(4)), FakeKeyframe(np.eye(4)))
    volumes: list[FakeVolume] = []

    def factory() -> FakeVolume:
        volume = FakeVolume()
        volumes.append(volume)
        return volume

    engine = LiveFusionEngine(volume_factory=factory)
    engine.integrate(keyframes[0])

    mesh = engine.rebuild(keyframes)

    assert len(volumes) == 2
    assert mesh == {"count": len(keyframes)}
    assert len(volumes[0].integrated) == 1
    assert len(volumes[1].integrated) == len(keyframes)


def test_integrate_returns_valid_pixel_count_and_forwards_roi() -> None:
    volume = FakeVolume()
    keyframe = FakeKeyframe(np.eye(4))
    roi_min = np.array([-0.1, -0.1, -0.1])
    roi_max = np.array([0.1, 0.1, 0.1])
    engine = LiveFusionEngine(
        volume_factory=lambda: volume,
        roi_min=roi_min,
        roi_max=roi_max,
    )

    valid_pixels = engine.integrate(keyframe)

    assert valid_pixels == 42
    np.testing.assert_allclose(volume.integrated[0][1], roi_min)
    np.testing.assert_allclose(volume.integrated[0][2], roi_max)


def test_live_fusion_rejects_roi_larger_than_small_object_envelope() -> None:
    with np.testing.assert_raises(ValueError):
        LiveFusionEngine(
            volume_factory=FakeVolume,
            roi_min=np.array([-0.3, -0.1, -0.1]),
            roi_max=np.array([0.3, 0.1, 0.1]),
        )
