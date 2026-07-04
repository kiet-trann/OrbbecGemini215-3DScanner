import numpy as np

from scanner_app.processing.depth import depth_to_meters, filter_depth_range


def test_depth_to_meters_applies_scale() -> None:
    raw = np.array([[100, 200]], dtype=np.uint16)

    result = depth_to_meters(raw, 0.001)

    np.testing.assert_allclose(result, np.array([[0.1, 0.2]], dtype=np.float32))


def test_filter_depth_range_sets_invalid_depth_to_zero() -> None:
    depth = np.array([[0.1, 0.2, 0.8]], dtype=np.float32)

    result = filter_depth_range(depth, min_depth_m=0.15, max_depth_m=0.70)

    np.testing.assert_allclose(result, np.array([[0.0, 0.2, 0.0]], dtype=np.float32))
